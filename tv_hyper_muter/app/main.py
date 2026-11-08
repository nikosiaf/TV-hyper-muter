"""TV hyper muter add-on entry point.

`Runner` holds everything that talks to the outside world (Home Assistant, Hyperion, files);
`Decider` makes the decisions. Mute ownership lives here, apart from the decision: the add-on
owns a mute from a confirmed mute command until a confirmed unmute (or until the TV shows it
is no longer muted / is off). A failed unmute is retried with backoff, and an owned mute is
saved to disk so a restart releases it too.
"""
import datetime as dt
import json
import os
import re
import shutil
import signal
import sys
import time
import urllib.error
import urllib.request
from io import BytesIO

import numpy as np
from PIL import Image

import badge
import sports
from decider import Decider
from hyperion import Hyperion

STATUS_ENTITY = "sensor.tv_hyper_muter"
SIZE = (320, 180)  # badge positions and the bottom band are calibrated on Hyperion's 320x180 image
RETRY_MIN_S, RETRY_MAX_S = 2, 60
NO_PICTURE_AFTER = 3  # consecutive frame failures before the status says no_picture


def shapes(c):
    # main badge shape plus optional extra shapes "y,x,r;y,x,r" (e.g. Open's small talk-show badge)
    s = [(int(c["y"]), int(c["x"]), float(c["r"]))]
    for part in filter(None, (c.get("alt") or "").split(";")):
        y, x, r = part.split(",")
        s.append((int(y), int(x), float(r)))
    return s


def make_decider(o):
    chans = o["channels"]
    return Decider(miss_s=o["miss_seconds"], max_mute_s=o["max_mute_minutes"] * 60,
                   on=o["badge_on"], off=o["badge_off"], arm_sightings=o["arm_sightings"],
                   absent=o["absent_below"], absent_frac=o["absent_fraction"],
                   max_mute_by_channel={c["name"]: c["max_mute_minutes"] * 60
                                        for c in chans if c.get("max_mute_minutes")},
                   arm_on_by_channel={c["name"]: c["arm_on"] for c in chans if c.get("arm_on")},
                   absent_by_channel={c["name"]: c["absent_below"] for c in chans if c.get("absent_below")},
                   zap_in=o["zap_in"],
                   static=o["static_motion"], static_frac=o["static_fraction"],
                   news_band=o["news_band"], news_unmute=o["news_unmute"], news_hold_s=o["news_hold_s"],
                   band_now=o.get("news_band_now", 0.5),
                   unmute_hold_by_channel={c["name"]: c["unmute_hold_s"] for c in chans if c.get("unmute_hold_s")},
                   # saved add-on options keep only the keys they had: new options need a default here
                   sports=o.get("sports_pitch", 0.25), sports_memory_s=o.get("sports_memory_s", 180))


class HAClient:
    def __init__(self, url, token, ctx=None, timeout=10):
        self.url, self.token, self.ctx, self.timeout = url, token, ctx, timeout

    def __call__(self, method, path, body=None):
        req = urllib.request.Request(f"{self.url}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
            return json.loads(r.read() or b"null")


def to_gray(img):
    """Decode a frame to a 320x180 grey image; other 16:9 sizes are scaled, others refused.
    Returns (grey, original size, colour image at 320x180)."""
    im = Image.open(BytesIO(img))
    im.load()
    w, h = im.size
    if (w, h) != SIZE:
        if w < 160 or h < 90 or w > 4096 or h > 4096 or abs(w / h - 16 / 9) > 0.02:
            raise ValueError(f"unsupported frame size {w}x{h} (need 16:9)")
        im = im.resize(SIZE, Image.BILINEAR)
    return im.convert("L"), (w, h), im


class Runner:
    def __init__(self, o, ha, hyp, out, state_path, mono=time.monotonic, wall=time.time):
        self.o, self.ha, self.hyp, self.out, self.state_path = o, ha, hyp, out, state_path
        self.mono, self.wall = mono, wall
        self.channels = [(c["name"], re.compile(c["match"], re.I)) for c in o["channels"]]
        badge.CENTRES.update({c["name"]: shapes(c) for c in o["channels"]})
        self.captioned = {c["name"]: (int(c["y"]), int(c["x"])) for c in o["channels"] if c.get("caption")}
        badge.SHIFT = int(o["search_shift"])
        self.d = make_decider(o)
        self.next_poll = 0.0
        self.next_frame = 0.0
        self.tv_on = self.tv_muted = False
        self.enabled, self.enable_problem = True, None
        self.last_title = object()
        self.prev_small = (None, None)  # (channel, centre of last frame) for picture motion
        self.bands = []  # (t, channel, edge map of rows 120-180) of the last ~12 s
        self.mutes, self.today = 0, dt.date.today()
        self.frame_errors = 0
        self.size_logged = None
        self.reason = None  # last decision, for the status sensor
        self.last_frame_wall = None
        self.last_score = None
        self.status_key, self.last_pub = None, -1e9
        # ownership of a mute on the TV, apart from the decision
        self.owned = False
        self.release_pending = False
        self.retry_at, self.backoff = 0.0, RETRY_MIN_S
        self._load_state()

    # ---- files ----
    def day_dir(self):
        d = f"{self.out}/{dt.date.fromtimestamp(self.wall()).isoformat()}"
        os.makedirs(d, exist_ok=True)
        return d

    def log(self, event, **kw):
        rec = {"t": dt.datetime.fromtimestamp(self.wall()).strftime("%Y-%m-%d %H:%M:%S"),
               "event": event, **kw}
        line = json.dumps(rec, ensure_ascii=False)
        print(line, flush=True)
        try:
            with open(f"{self.day_dir()}/events.jsonl", "a") as f:
                f.write(line + "\n")
        except OSError as e:  # a full or broken share must not stop mute handling
            print("log write failed", repr(e), flush=True)

    def prune(self):
        cutoff = dt.date.today() - dt.timedelta(days=int(self.o["keep_days"]))
        for name in os.listdir(self.out):
            try:
                if dt.date.fromisoformat(name) < cutoff:
                    shutil.rmtree(f"{self.out}/{name}")
            except (ValueError, OSError):
                pass

    def _load_state(self):
        try:
            st = json.load(open(self.state_path))
        except (OSError, ValueError):
            return
        if st.get("owned"):
            # we held a mute when the last run ended without releasing it: release it once
            # the TV state is known (see poll)
            self.owned = self.release_pending = True
            self.retry_at = float("inf")  # wait for the first TV state (poll) before acting
            self.reason = "release after restart"
            self.log("owned_mute_found", since=st.get("since"), channel=st.get("channel"))

    def _save_state(self):
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"owned": self.owned, "since": self.wall(), "channel": self.d.channel}, f)
            os.replace(tmp, self.state_path)
        except OSError as e:
            print("state write failed", repr(e), flush=True)

    # ---- Home Assistant ----
    def channel_of(self, title):
        for name, rx in self.channels:
            if rx.search(title or ""):
                return name
        return None

    def read_tv(self):
        st = self.ha("GET", f"/states/{self.o['tv_entity']}")
        at = st.get("attributes", {})
        tv_on = st.get("state") == "on"
        title = at.get("media_title")
        ch = self.channel_of(title) if tv_on and at.get("source") == self.o["live_source"] else None
        return tv_on, bool(at.get("is_volume_muted")), title, at.get("source"), ch

    def set_mute(self, on):
        if self.o["dry_run"]:
            return
        self.ha("POST", "/services/media_player/volume_mute",
                {"entity_id": self.o["tv_entity"], "is_volume_muted": on})

    def publish(self, force=False):
        if os.environ.get("TVHYPERMUTER_NO_STATUS"):
            return
        t = self.mono()
        if not self.enabled:
            state = "disabled"
        elif self.release_pending:
            state = "releasing"
        elif self.d.channel and self.frame_errors >= NO_PICTURE_AFTER:
            state = "no_picture"
        elif self.d.holding and self.o["dry_run"]:
            state = "would_mute"
        else:
            state = self.d.phase
        key = (state, self.d.channel, self.mutes, self.reason, self.enable_problem, self.d.sport)
        if not force and key == self.status_key and t - self.last_pub < 30:
            return
        left = None
        if self.d.holding:
            left = max(0, int(self.d.mute_cap() - (t - self.d.muted_at)))
        attrs = {"friendly_name": "TV hyper muter", "icon": "mdi:television-off",
                 "channel": self.d.channel, "badge_score": self.last_score,
                 "mutes_today": self.mutes, "dry_run": self.o["dry_run"],
                 "reason": self.reason, "mute_left_s": left, "sport": self.d.sport,
                 "last_frame": None if self.last_frame_wall is None else
                 dt.datetime.fromtimestamp(self.last_frame_wall).isoformat(timespec="seconds"),
                 "problem": self.enable_problem}
        try:
            self.ha("POST", f"/states/{STATUS_ENTITY}", {"state": state, "attributes": attrs})
            self.status_key, self.last_pub = key, t
        except Exception as e:
            print("status publish failed", repr(e), flush=True)

    # ---- mute ownership ----
    def do_mute(self, why, sc, img):
        # the decision used TV state up to state_poll_s old: recheck before acting
        try:
            tv_on, muted, title, source, ch = self.read_tv()
        except Exception as e:
            self.d.cancel_mute()
            self.log("mute_skipped", channel=self.d.channel, reason=f"TV state unavailable: {e!r}")
            return
        if ch != self.d.channel or muted or not self.enabled:
            self.d.cancel_mute()
            self.log("mute_skipped", channel=self.d.channel, reason="context changed",
                     now_channel=ch, tv_muted=muted)
            return
        try:
            self.set_mute(True)
        except Exception as e:
            self.d.cancel_mute()
            self.log("mute_failed", channel=self.d.channel, error=repr(e))
            return
        if not self.o["dry_run"]:
            self.owned = True
            self._save_state()
        self.mutes += 1
        self.reason = why
        self.log("mute", channel=self.d.channel, score=None if sc is None else round(sc, 2),
                 reason=why, frame=self.save_frame("mute", img))

    def do_unmute(self, why, held_since, sc=None, img=None):
        self.reason = why
        muted_for = None if held_since is None else int(self.mono() - held_since)
        if not self.owned:  # dry run, or the mute command never went through
            self.log("unmute", channel=self.d.channel, reason=why, muted_for_s=muted_for,
                     **({"dry_run": True} if self.o["dry_run"] else {}))
            return
        self.release_pending = True
        self.retry_at, self.backoff = 0.0, RETRY_MIN_S
        if self.try_release():
            self.log("unmute", channel=self.d.channel, reason=why, muted_for_s=muted_for,
                     score=None if sc is None else round(sc, 2), frame=self.save_frame("unmute", img))
        else:
            self.log("unmute_failed", channel=self.d.channel, reason=why, retry_in_s=self.backoff)

    def try_release(self):
        """One attempt at our pending unmute; True when done."""
        try:
            self.set_mute(False)
        except Exception as e:
            self.retry_at = self.mono() + self.backoff
            self.last_release_error = repr(e)
            self.backoff = min(self.backoff * 2, RETRY_MAX_S)
            return False
        self.owned = self.release_pending = False
        self.backoff = RETRY_MIN_S
        self._save_state()
        return True

    def drop_ownership(self, why):
        if self.owned or self.release_pending:
            self.owned = self.release_pending = False
            self._save_state()
            self.log("release", channel=self.d.channel, reason=why)

    def save_frame(self, act, img):
        if img is None or not self.o["save_frames"]:
            return ""
        name = f"{int(self.wall())}_{act}_{self.d.channel}.jpg"
        try:
            with open(f"{self.day_dir()}/{name}", "wb") as f:
                f.write(img)
        except OSError:
            return ""
        return name

    # ---- loop ----
    def poll(self):
        o = self.o
        try:
            tv_on, tv_muted, title, source, ch = self.read_tv()
            if o["enable_entity"]:
                was = self.enabled
                try:
                    self.enabled = self.ha("GET", f"/states/{o['enable_entity']}").get("state") == "on"
                    self.enable_problem = None
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        raise
                    # a missing switch must not stop the muter; say so on the sensor and once in the log
                    if self.enable_problem is None:
                        self.log("enable_entity_missing", entity=o["enable_entity"], acting_as="enabled")
                    self.enabled, self.enable_problem = True, f"{o['enable_entity']} not found"
                if self.enabled != was:
                    self.log("enabled" if self.enabled else "disabled", entity=o["enable_entity"])
            if not self.enabled:
                ch = None
        except Exception as e:
            self.log("ha_error", error=repr(e))
            return
        self.tv_on, self.tv_muted = tv_on, tv_muted
        if title != self.last_title:
            self.last_title = title
            self.log("channel", channel=ch, title=title, source=source, tv_on=tv_on)
        # observed TV state settles a pending release
        if self.release_pending and not self.d.holding:
            if not tv_on:
                self.drop_ownership("TV off")
            elif not tv_muted:
                self.drop_ownership("TV shows unmuted")
            elif self.retry_at == float("inf"):
                self.retry_at = 0.0  # after a restart: TV on and muted, release it now
        t = self.mono()
        held_since = self.d.muted_at
        # in dry run the TV never gets muted: do not read that as the user unmuting
        obs_muted = True if (self.o["dry_run"] and self.d.holding) else tv_muted
        act, why = self.d.state(t, ch, tv_on, obs_muted)
        if why and not self.enabled:
            why = "disabled"  # released because enable_entity was switched off
        if act == "unmute":
            self.do_unmute(why, held_since)
        elif why == "user unmuted":
            self.reason = why
            self.drop_ownership(why)
        elif why:  # released without a command (TV off)
            self.reason = why
            self.drop_ownership(why)

    def grab(self):
        """One frame: score it and feed the decider."""
        t, wall = self.mono(), self.wall()
        try:
            img = self.hyp.frame()
            gray, size, colour = to_gray(img)
        except Exception as e:
            self.frame_errors += 1
            self.hyp.close()
            if self.frame_errors <= 3 or self.frame_errors % 30 == 0:
                self.log("frame_error", channel=self.d.channel, error=repr(e), count=self.frame_errors)
            self.next_frame = t + 5
            return
        self.frame_errors = 0
        if size != SIZE and size != self.size_logged:
            self.size_logged = size
            self.log("frame_resized", size=f"{size[0]}x{size[1]}", to="320x180")
        self.last_frame_wall = wall
        a = np.asarray(gray, float)
        g = badge.grad(a)
        sc = badge.score_grad(g, self.d.channel)
        self.last_score = round(sc, 2)
        # motion of the centre only: no badge/logo strip, no ticker band
        small = np.asarray(gray.resize((80, 45)), float)[6:32, 4:76]
        ch = self.d.channel
        mo = float(np.abs(small - self.prev_small[1]).mean()) if self.prev_small[0] == ch else 99.0
        self.prev_small = (ch, small)
        # bottom band stability vs 8-12 s ago: fixed news/talk-show graphics, not an ad
        bnd = g[120:180]
        old = [b for a_, c, b in self.bands if c == ch and 8 <= t - a_ <= 12]
        if old:
            x, y = bnd - bnd.mean(), old[0] - old[0].mean()
            bc = float((x * y).sum() / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-6))
        else:
            bc = 0.0
        self.bands = [(a_, c, b) for a_, c, b in self.bands + [(t, ch, bnd)] if t - a_ <= 12]
        held_since = self.d.muted_at
        tv_muted = False if self.d.holding else self.tv_muted  # our own mute must not block unmute logic
        cap = badge.caption(a, *self.captioned[ch]) if ch in self.captioned else None
        pt = sports.pitch(colour)
        act, why = self.d.frame(t, sc, tv_muted, mo, bc, cap, pt)
        try:
            with open(f"{self.day_dir()}/scores.csv", "a") as f:
                f.write(f"{int(wall)},{ch},{sc:.3f},{int(self.d.holding)},{mo:.1f},{bc:.2f},{'' if cap is None else f'{cap:.0f}'},{pt:.2f}\n")
        except OSError:
            pass
        if act == "mute":
            self.do_mute(why, sc, img)
        elif act == "unmute":
            self.do_unmute(why, held_since, sc, img)

    def step(self):
        """One pass of the loop; returns seconds to sleep."""
        t = self.mono()
        if dt.date.fromtimestamp(self.wall()) != self.today:
            self.today, self.mutes = dt.date.fromtimestamp(self.wall()), 0
            self.prune()
        # 1. pending release first: it matters more than anything else
        if self.release_pending and t >= self.retry_at:
            if self.try_release():
                self.log("unmute", channel=self.d.channel, reason=self.reason, retried=True)
        # 2. time-only checks (max mute time, no picture), frames or not
        held_since = self.d.muted_at
        act, why = self.d.tick(t)
        if act:
            self.do_unmute(why, held_since)
        # 3. TV state
        if t >= self.next_poll:
            self.next_poll = t + self.o["state_poll_s"]
            self.poll()
        # 4. picture
        if self.d.channel is None:
            self.hyp.close()
            self.frame_errors = 0
        elif t >= self.next_frame:
            self.next_frame = t + self.o["frame_interval_s"]
            self.grab()
        self.publish()
        nxt = [self.next_poll] + ([self.next_frame] if self.d.channel else [])
        if self.release_pending:
            nxt.append(self.retry_at)
        return max(min(nxt) - self.mono(), 0.05)

    def shutdown(self):
        if self.owned:
            try:
                self.set_mute(False)
                self.owned = self.release_pending = False
                self._save_state()
                self.log("unmute", channel=self.d.channel, reason="add-on stopped")
            except Exception as e:
                # ownership stays on disk: the next start releases it
                self.log("unmute_failed", channel=self.d.channel, reason="add-on stopped", error=repr(e))
        self.d.muted_at = None
        self.publish_stopped()
        self.log("stop")

    def publish_stopped(self):
        if os.environ.get("TVHYPERMUTER_NO_STATUS"):
            return
        try:
            self.ha("POST", f"/states/{STATUS_ENTITY}", {"state": "stopped", "attributes": {
                "friendly_name": "TV hyper muter", "icon": "mdi:television-off",
                "mutes_today": self.mutes, "dry_run": self.o["dry_run"]}})
        except Exception as e:
            print("status publish failed", repr(e), flush=True)


def main():
    o = json.load(open(os.environ.get("TVHYPERMUTER_OPTIONS", "/data/options.json")))
    out = os.environ.get("TVHYPERMUTER_OUT", "/share/tv_hyper_muter")
    state_path = os.environ.get("TVHYPERMUTER_STATE", "/data/state.json")
    ctx = None
    if os.environ.get("HA_INSECURE"):  # local testing against HA's self-signed certificate only
        import ssl
        ctx = ssl._create_unverified_context()
    # Inside the add-on the Supervisor proxies Core; HA_URL/HA_TOKEN allow running outside it for tests.
    ha = HAClient(os.environ.get("HA_URL", "http://supervisor/core/api"),
                  os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN", ""), ctx)
    os.makedirs(out, exist_ok=True)
    r = Runner(o, ha, Hyperion(o["hyperion_host"], o["hyperion_port"]), out, state_path)
    r.prune()
    r.log("start", dry_run=o["dry_run"], channels=[c for c, _ in r.channels])
    try:
        while True:
            try:
                wait = r.step()
            except Exception as e:  # never let one bad pass kill the loop while we may own a mute
                r.log("error", error=repr(e))
                wait = 2
            time.sleep(wait)
    finally:
        r.shutdown()


def _stop(signum, frame):
    raise SystemExit(0)  # run main()'s finally: release our mute before the container stops


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    sys.exit(main())
