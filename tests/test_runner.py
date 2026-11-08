"""Runner tests: fake Home Assistant, fake Hyperion with generated frames, fake clock.

They cover what the decider tests cannot: command failures, retries, restart recovery,
frame gaps, frame sizes and the status sensor.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tv_hyper_muter", "app"))
os.environ.pop("TVHYPERMUTER_NO_STATUS", None)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import main  # noqa: E402

CH = {"name": "test", "match": r"\bTEST\b", "y": 40, "x": 160, "r": 5}
T0 = 1_800_000_000.0


def options(**kw):
    o = {"tv_entity": "media_player.tv", "live_source": "Live TV", "hyperion_host": "x",
         "hyperion_port": 1, "enable_entity": "", "dry_run": False, "frame_interval_s": 2,
         "state_poll_s": 5, "miss_seconds": 25, "max_mute_minutes": 12, "badge_on": 0.5,
         "badge_off": 0.45, "absent_below": 0.3, "absent_fraction": 0.9, "search_shift": 2,
         "arm_sightings": 3, "static_motion": 2.0, "static_fraction": 0.5, "news_band": 0.3,
         "news_band_now": 0.5, "news_unmute": 0.4, "news_hold_s": 30, "zap_in": True,
         "save_frames": False, "keep_days": 14, "channels": [CH]}
    o.update(kw)
    return o


class Clock:
    def __init__(self):
        self.t = 0.0

    def mono(self):
        return self.t

    def wall(self):
        return T0 + self.t


class FakeHA:
    def __init__(self):
        self.tv = {"state": "on", "source": "Live TV", "title": "TEST HD", "muted": False}
        self.fail_mute = 0      # fail the next N volume_mute calls
        self.down = False       # every call fails
        self.mute_calls = []
        self.status = []
        self.switch = None      # state of the enable entity, None = 404

    def __call__(self, method, path, body=None):
        if self.down:
            raise urllib.error.URLError("HA down")
        if path == "/states/media_player.tv":
            return {"state": self.tv["state"], "attributes": {
                "source": self.tv["source"], "media_title": self.tv["title"],
                "is_volume_muted": self.tv["muted"]}}
        if path == "/states/input_boolean.sw":
            if self.switch is None:
                raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)
            return {"state": self.switch}
        if path == "/services/media_player/volume_mute":
            if self.fail_mute:
                self.fail_mute -= 1
                raise urllib.error.URLError("timeout")
            self.mute_calls.append(body["is_volume_muted"])
            self.tv["muted"] = body["is_volume_muted"]
            return []
        if path.startswith("/states/sensor."):
            self.status.append(body)
            return {}
        raise AssertionError(path)


class FakeHyperion:
    """'badge' = programme, 'ad' = no badge, 'fail' = no frame. Noise everywhere else so the
    picture moves and the bottom band changes, like an ad."""

    def __init__(self, size=(320, 180)):
        self.mode, self.size = "badge", size
        self.rng = np.random.default_rng(1)

    def frame(self):
        if self.mode == "fail":
            raise TimeoutError("no frame from Hyperion")
        a = self.rng.integers(0, 255, (180, 320)).astype(np.uint8)
        a[25:56, 145:176] = 60
        im = Image.fromarray(a)
        if self.mode == "badge":
            ImageDraw.Draw(im).ellipse((155, 35, 165, 45), outline=230, width=1)
        if self.size != (320, 180):
            im = im.resize(self.size, Image.NEAREST)
        b = BytesIO()
        im.save(b, "PNG")
        return b.getvalue()

    def close(self):
        pass


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "state.json")
        self.clock, self.ha, self.hyp = Clock(), FakeHA(), FakeHyperion()
        self.r = self.make()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def make(self, **kw):
        return main.Runner(options(**kw), self.ha, self.hyp, self.dir, self.state,
                           mono=self.clock.mono, wall=self.clock.wall)

    def run_until(self, t, r=None):
        r = r or self.r
        while self.clock.t < t:
            self.clock.t += max(r.step(), 0.05)

    def events(self):
        out = []
        for root, _, files in os.walk(self.dir):
            if "events.jsonl" in files:
                out += [json.loads(x) for x in open(os.path.join(root, "events.jsonl"))]
        return out

    def ev(self, name):
        return [e for e in self.events() if e["event"] == name]

    def owned_on_disk(self):
        return json.load(open(self.state))["owned"] if os.path.exists(self.state) else False

    def mute_by_ad(self):
        self.run_until(30)
        self.hyp.mode = "ad"
        self.run_until(70)
        self.assertEqual(self.ha.mute_calls, [True])
        self.assertTrue(self.r.owned and self.owned_on_disk())

    def test_mutes_on_ad_and_unmutes_on_badge(self):
        self.mute_by_ad()
        mute_t = self.ev("mute")[0]
        self.assertEqual(mute_t["reason"][:13], "badge missing")
        self.hyp.mode = "badge"
        self.run_until(80)
        self.assertEqual(self.ha.mute_calls, [True, False])
        self.assertFalse(self.r.owned or self.owned_on_disk())

    def test_failed_unmute_is_retried(self):
        self.mute_by_ad()
        self.ha.fail_mute = 3
        self.hyp.mode = "badge"
        self.run_until(76)
        self.assertTrue(self.ev("unmute_failed"))
        self.assertTrue(self.ha.tv["muted"])
        self.assertTrue(self.r.owned)
        self.run_until(110)  # backoff 2, 4, 8 s
        self.assertFalse(self.ha.tv["muted"])
        self.assertFalse(self.r.owned or self.owned_on_disk())
        self.assertTrue(any(e.get("retried") for e in self.ev("unmute")))

    def test_failed_mute_is_not_owned(self):
        self.run_until(30)
        self.ha.fail_mute = 1
        self.hyp.mode = "ad"
        self.run_until(58)
        self.assertTrue(self.ev("mute_failed"))
        self.assertFalse(self.r.owned)
        self.assertFalse(self.r.d.holding)

    def test_restart_releases_owned_mute(self):
        self.mute_by_ad()
        self.ha.down = True
        self.r.shutdown()  # cannot unmute: ownership stays on disk
        self.assertTrue(self.owned_on_disk())
        self.ha.down = False
        r2 = self.make()
        self.assertTrue(self.ev("owned_mute_found"))
        self.hyp.mode = "ad"
        self.run_until(self.clock.t + 3, r2)
        self.assertFalse(self.ha.tv["muted"])
        self.assertFalse(r2.owned or self.owned_on_disk())

    def test_restart_with_tv_already_unmuted_sends_nothing(self):
        with open(self.state, "w") as f:
            json.dump({"owned": True}, f)
        r2 = self.make()
        self.run_until(3, r2)
        self.assertEqual(self.ha.mute_calls, [])
        self.assertFalse(r2.owned)

    def test_max_mute_time_without_frames(self):
        self.mute_by_ad()
        self.hyp.mode = "fail"
        self.run_until(70 + 65)
        self.assertEqual(self.ha.mute_calls, [True, False])
        self.assertEqual(self.ev("unmute")[-1]["reason"], "no picture")

    def test_frame_gap_is_not_evidence(self):
        # review case: badge, then a 26 s gap, then one missing-badge frame -> no mute
        self.run_until(30)
        self.hyp.mode = "fail"
        self.run_until(56)
        self.hyp.mode = "ad"
        self.run_until(60)
        self.assertEqual(self.ha.mute_calls, [])

    def test_gap_inside_window_is_not_evidence(self):
        # ads, a 15 s capture gap, ads again: the 25 s window is not covered until 25 s after it
        self.run_until(30)
        self.hyp.mode = "ad"
        self.run_until(40)
        self.hyp.mode = "fail"
        self.run_until(55)
        self.hyp.mode = "ad"
        self.run_until(64)
        self.assertEqual(self.ha.mute_calls, [])
        self.run_until(95)
        self.assertEqual(self.ha.mute_calls, [True])

    def test_channel_rechecked_before_mute(self):
        self.run_until(30)
        self.hyp.mode = "ad"
        self.run_until(50)
        self.ha.tv["title"] = "OTHER"  # zapped away inside the poll interval
        self.r.d.muted_at = self.clock.t
        self.r.do_mute("badge missing", 0.1, None)
        self.assertEqual(self.ha.mute_calls, [])
        self.assertFalse(self.r.d.holding)
        self.assertEqual(self.ev("mute_skipped")[0]["reason"], "context changed")

    def test_bigger_16_9_frames_are_scaled(self):
        self.hyp.size = (640, 360)
        self.mute_by_ad()
        self.assertEqual(self.ev("frame_resized")[0]["size"], "640x360")

    def test_non_16_9_frames_are_refused(self):
        self.hyp.size = (320, 240)
        self.run_until(30)
        self.hyp.mode = "ad"
        self.run_until(70)
        self.assertEqual(self.ha.mute_calls, [])
        self.assertIn("unsupported frame size", self.ev("frame_error")[0]["error"])
        self.assertEqual(self.ha.status[-1]["state"], "no_picture")

    def test_dry_run_would_mute_and_holds(self):
        self.r = self.make(dry_run=True)
        self.run_until(30)
        self.hyp.mode = "ad"
        self.run_until(100)  # past the 15 s user-unmute grace
        self.assertEqual(self.ha.mute_calls, [])
        self.assertTrue(self.r.d.holding)
        self.assertEqual(self.ha.status[-1]["state"], "would_mute")

    def test_status_phases(self):
        self.run_until(1)
        self.assertEqual(self.ha.status[-1]["state"], "learning")
        self.run_until(30)
        self.assertEqual(self.ha.status[-1]["state"], "armed")
        self.hyp.mode = "ad"
        self.run_until(45)
        self.assertEqual(self.ha.status[-1]["state"], "possible_ad")
        self.run_until(70)
        st = self.ha.status[-1]
        self.assertEqual(st["state"], "muted")
        self.assertGreater(st["attributes"]["mute_left_s"], 600)
        self.assertIsNotNone(st["attributes"]["last_frame"])

    def test_switch_off_releases_with_reason_disabled(self):
        self.ha.switch = "on"
        self.r = self.make(enable_entity="input_boolean.sw")
        self.mute_by_ad()
        self.ha.switch = "off"
        self.run_until(80)
        self.assertFalse(self.ha.tv["muted"])
        self.assertEqual(self.ev("unmute")[-1]["reason"], "disabled")
        self.assertEqual(self.ha.status[-1]["state"], "disabled")

    def test_missing_switch_is_reported(self):
        self.r = self.make(enable_entity="input_boolean.sw")
        self.run_until(10)
        self.assertEqual(len(self.ev("enable_entity_missing")), 1)
        self.assertIn("not found", self.ha.status[-1]["attributes"]["problem"])

    def test_user_unmute_drops_ownership(self):
        self.mute_by_ad()
        self.ha.tv["muted"] = False  # remote control
        self.run_until(90)
        self.assertFalse(self.r.owned or self.owned_on_disk())
        self.assertEqual(self.ha.mute_calls, [True])


if __name__ == "__main__":
    unittest.main()


class CaptionTest(unittest.TestCase):
    """badge.caption: two small caption lines next to a top-left badge vs a promo's day/time label."""

    def frame(self, rows):
        a = np.full((180, 320), 60.0)
        for y in rows:
            a[y, 18:60:2] = 230.0  # text strokes: bright/dark alternation
        return a

    def test_two_caption_lines_score_high(self):
        self.assertGreater(main.badge.caption(self.frame([8, 9, 10, 11, 13, 14, 15]), 10, 13), 10)

    def test_one_big_label_scores_low(self):
        self.assertLessEqual(main.badge.caption(self.frame([10, 11, 12, 13, 14]), 10, 13), 0)

    def test_badge_alone_scores_zero(self):
        self.assertEqual(main.badge.caption(self.frame([]), 10, 13), 0)


class OptionsTest(unittest.TestCase):
    def test_hold_and_caption_options_reach_the_decider(self):
        ch = dict(CH, unmute_hold_s=60, caption=True)
        d = main.make_decider(options(channels=[ch]))
        self.assertEqual(d.unmute_hold_by_channel, {"test": 60})
        r = main.Runner(options(channels=[ch]), FakeHA(), FakeHyperion(), tempfile.mkdtemp(), "/nonexistent/s.json")
        self.assertEqual(r.captioned, {"test": (40, 160)})


class SportsRunnerTest(unittest.TestCase):
    setUp, tearDown, make, run_until = RunnerTest.setUp, RunnerTest.tearDown, RunnerTest.make, RunnerTest.run_until

    def test_grass_green_picture_is_sport(self):
        from PIL import Image as I
        import sports
        grass = I.new("RGB", (320, 180), (70, 150, 50))
        teal = I.new("RGB", (320, 180), (30, 150, 140))
        self.assertGreater(sports.pitch(grass), 0.9)
        self.assertEqual(sports.pitch(teal), 0.0)

    def test_options_reach_the_decider(self):
        r = self.make(sports_pitch=0.4, sports_memory_s=60)
        self.assertEqual((r.d.sports, r.d.sports_memory_s), (0.4, 60))
        self.assertEqual(self.make().d.sports, 0.25)  # saved options without the keys

    def test_scores_have_a_pitch_column(self):
        self.run_until(20)
        rows = [l.split(",") for root, _, fs in os.walk(self.dir) if "scores.csv" in fs
                for l in open(os.path.join(root, "scores.csv"))]
        self.assertTrue(rows and all(len(x) == 8 for x in rows))
