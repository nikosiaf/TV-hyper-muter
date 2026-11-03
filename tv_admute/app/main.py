"""TV Ad Mute add-on entry point."""
import datetime as dt
import json
import os
import re
import shutil
import signal
import sys
import time
import urllib.request
from io import BytesIO

import numpy as np
from PIL import Image

import badge
from decider import Decider
from hyperion import Hyperion

OPTIONS = os.environ.get("TVADMUTE_OPTIONS", "/data/options.json")
OUT = os.environ.get("TVADMUTE_OUT", "/share/tv_admute")
# Inside the add-on the Supervisor proxies Core; HA_URL/HA_TOKEN allow running outside it for tests.
HA_URL = os.environ.get("HA_URL", "http://supervisor/core/api")
HA_TOKEN = os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN", "")
STATUS_ENTITY = "sensor.tv_admute"

o = json.load(open(OPTIONS))
CHANNELS = [(c["name"], re.compile(c["match"], re.I)) for c in o["channels"]]
badge.CENTRES.update({c["name"]: (int(c["y"]), int(c["x"]), float(c["r"])) for c in o["channels"]})
badge.SHIFT = int(o["search_shift"])


def log(event, **kw):
    rec = {"t": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "event": event, **kw}
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    with open(f"{day_dir()}/events.jsonl", "a") as f:
        f.write(line + "\n")


def day_dir():
    d = f"{OUT}/{dt.date.today().isoformat()}"
    os.makedirs(d, exist_ok=True)
    return d


def prune():
    cutoff = dt.date.today() - dt.timedelta(days=int(o["keep_days"]))
    for name in os.listdir(OUT):
        try:
            if dt.date.fromisoformat(name) < cutoff:
                shutil.rmtree(f"{OUT}/{name}")
        except ValueError:
            pass


_CTX = None
if os.environ.get("HA_INSECURE"):  # local testing against HA's self-signed certificate only
    import ssl
    _CTX = ssl._create_unverified_context()


def ha(method, path, body=None):
    req = urllib.request.Request(f"{HA_URL}{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {HA_TOKEN}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15, context=_CTX) as r:
        return json.loads(r.read() or b"null")


def channel_of(title):
    for name, rx in CHANNELS:
        if rx.search(title or ""):
            return name
    return None


def set_mute(on):
    if o["dry_run"]:
        return
    ha("POST", "/services/media_player/volume_mute", {"entity_id": o["tv_entity"], "is_volume_muted": on})


def publish(status, channel=None, score=None, mutes=0):
    if os.environ.get("TVADMUTE_NO_STATUS"):
        return
    try:
        ha("POST", f"/states/{STATUS_ENTITY}", {
            "state": status,
            "attributes": {"friendly_name": "TV ad mute", "icon": "mdi:television-off",
                           "channel": channel, "badge_score": score, "mutes_today": mutes,
                           "dry_run": o["dry_run"]}})
    except Exception as e:
        print("status publish failed", repr(e), flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    prune()
    d = Decider(miss_s=o["miss_seconds"], max_mute_s=o["max_mute_minutes"] * 60,
                on=o["badge_on"], off=o["badge_off"], arm_sightings=o["arm_sightings"],
                absent=o["absent_below"], absent_frac=o["absent_fraction"],
                max_mute_by_channel={c["name"]: c["max_mute_minutes"] * 60
                                     for c in o["channels"] if c.get("max_mute_minutes")},
                static=o["static_motion"], static_frac=o["static_fraction"])
    hyp = Hyperion(o["hyperion_host"], o["hyperion_port"])
    log("start", dry_run=o["dry_run"], channels=[c for c, _ in CHANNELS])
    next_poll, tv_on, tv_muted, enabled, last_title = 0, False, False, True, object()
    prev_small = (None, None)  # (channel, centre of last frame) for picture motion
    mutes, today, last_pub = 0, dt.date.today(), 0
    try:
        while True:
            t = time.time()
            if dt.date.today() != today:
                today, mutes = dt.date.today(), 0
                prune()
            if t >= next_poll:
                next_poll = t + o["state_poll_s"]
                try:
                    st = ha("GET", f"/states/{o['tv_entity']}")
                    at = st.get("attributes", {})
                    tv_on = st.get("state") == "on"
                    tv_muted = bool(at.get("is_volume_muted"))
                    title = at.get("media_title")
                    ch = channel_of(title) if tv_on and at.get("source") == o["live_source"] else None
                    if o["enable_entity"]:
                        enabled = ha("GET", f"/states/{o['enable_entity']}").get("state") == "on"
                    if not enabled:
                        ch = None
                except Exception as e:
                    log("ha_error", error=repr(e))
                    time.sleep(o["state_poll_s"])
                    continue
                if title != last_title:
                    last_title = title
                    log("channel", channel=ch, title=title, source=at.get("source"), tv_on=tv_on)
                held_since = d.muted_at
                act, why = d.state(t, ch, tv_on, tv_muted)
                if act == "unmute":
                    set_mute(False)
                if why:
                    log(act or "release", channel=d.channel, reason=why,
                        muted_for_s=None if held_since is None else int(t - held_since))
                if d.holding:
                    tv_muted = False
            if d.channel is None:
                hyp.close()
                if t - last_pub > 60:
                    publish("idle" if enabled else "disabled", mutes=mutes)
                    last_pub = t
                time.sleep(max(next_poll - time.time(), 0.5))
                continue
            try:
                img = hyp.frame()
            except Exception as e:
                log("frame_error", channel=d.channel, error=repr(e))
                time.sleep(5)
                continue
            gray = Image.open(BytesIO(img)).convert("L")
            sc = badge.score(np.asarray(gray, float), d.channel)
            # motion of the centre only: no badge/logo strip, no ticker band
            small = np.asarray(gray.resize((80, 45)), float)[6:32, 4:76]
            mo = float(np.abs(small - prev_small[1]).mean()) if prev_small[0] == d.channel else 99.0
            prev_small = (d.channel, small)
            muted_before = d.muted_at
            act, why = d.frame(t, sc, tv_muted, mo)
            with open(f"{day_dir()}/scores.csv", "a") as f:
                f.write(f"{int(t)},{d.channel},{sc:.3f},{int(d.holding)},{mo:.1f}\n")
            if act:
                set_mute(act == "mute")
                frame = ""
                if o["save_frames"]:
                    frame = f"{int(t)}_{act}_{d.channel}.jpg"
                    open(f"{day_dir()}/{frame}", "wb").write(img)
                if act == "mute":
                    mutes += 1
                log(act, channel=d.channel, score=round(sc, 2), reason=why, frame=frame,
                    muted_for_s=int(t - muted_before) if act == "unmute" and muted_before else None)
                publish("muted" if d.holding else "watching", d.channel, round(sc, 2), mutes)
                last_pub = t
            elif t - last_pub > 30:
                publish("muted" if d.holding else "watching", d.channel, round(sc, 2), mutes)
                last_pub = t
            time.sleep(max(o["frame_interval_s"] - (time.time() - t), 0))
    finally:
        if d.holding:
            try:
                set_mute(False)
                log("unmute", channel=d.channel, reason="add-on stopped")
            except Exception as e:
                print("final unmute failed", repr(e), flush=True)
        publish("stopped", mutes=mutes)
        log("stop")


def _stop(signum, frame):
    raise SystemExit(0)  # run main()'s finally: release our mute before the container stops


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    sys.exit(main())
