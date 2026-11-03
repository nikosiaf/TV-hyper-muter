import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tv_hyper_muter", "app"))
from decider import Decider  # noqa: E402

BADGE, NONE = 0.7, 0.1


def run(d, scores, start=0, step=2, tv_muted=False):
    acts = []
    for i, s in enumerate(scores):
        t = start + i * step
        a, why = d.frame(t, s, tv_muted)
        if a:
            acts.append((t, a, why))
    return acts


class DeciderTest(unittest.TestCase):
    def setUp(self):
        self.d = Decider(miss_s=60, max_mute_s=720)
        self.d.state(0, "alpha", True, False)

    def test_mutes_after_60s_and_unmutes_when_badge_returns(self):
        acts = run(self.d, [BADGE] * 5 + [NONE] * 40 + [BADGE] * 3)
        self.assertEqual([a for _, a, _ in acts], ["mute", "unmute"])
        self.assertTrue(60 <= acts[0][0] <= 70)  # badge gone from t=10; 90 % of a 60 s window
        self.assertEqual(acts[1][2], "badge back")

    def test_single_badge_frame_does_not_unmute(self):
        acts = run(self.d, [BADGE] * 5 + [NONE] * 35 + [BADGE] + [NONE] * 5)
        self.assertEqual([a for _, a, _ in acts], ["mute"])

    def test_scattered_badge_hits_do_not_arm(self):
        # news on Skai 2026-11-03: single >=0.5 frames minutes apart re-armed and muted the news
        scores = ([NONE] * 100 + [BADGE]) * 3 + [NONE] * 60
        d = Decider(miss_s=60, max_mute_s=720, zap_in=False)  # arming logic only
        d.state(0, "alpha", True, False)
        self.assertEqual(run(d, scores), [])

    def test_per_channel_max_mute(self):
        d = Decider(miss_s=60, max_mute_s=720, max_mute_by_channel={"skai": 540})
        d.state(0, "skai", True, False)
        acts = run(d, [BADGE] * 5 + [NONE] * 400)
        self.assertEqual([a for _, a, _ in acts], ["mute", "unmute"])
        self.assertEqual(acts[1][0] - acts[0][0], 540)
        self.assertEqual(acts[1][2], "max mute time")

    def test_30s_window_mutes_about_30s_after_badge_goes(self):
        d = Decider(miss_s=30, max_mute_s=720)
        d.state(0, "alpha", True, False)
        acts = run(d, [BADGE] * 5 + [NONE] * 30)
        self.assertEqual([a for _, a, _ in acts], ["mute"])
        self.assertTrue(28 <= acts[0][0] - 8 <= 34)  # last badge frame at t=8

    def test_still_picture_does_not_mute(self):
        # Skai 13:04 2026-11-03: a still screen at the start of the news, no badge
        acts = []
        for i in range(60):
            t = i * 2
            a, _ = self.d.frame(t, BADGE if i < 5 else NONE, False, 50.0 if i < 5 else 0.3)
            if a:
                acts.append(a)
        self.assertEqual(acts, [])

    def test_short_still_packshot_still_mutes(self):
        acts = []
        for i in range(45):
            t = i * 2
            still = 25 <= i < 30  # 10 s still product shot inside the ad
            a, _ = self.d.frame(t, BADGE if i < 5 else NONE, False, 0.5 if still else 50.0)
            if a:
                acts.append(a)
        self.assertEqual(acts, ["mute"])

    def test_news_band_blocks_mute(self):
        acts = []
        for i in range(60):
            a, _ = self.d.frame(i * 2, BADGE if i < 5 else NONE, False, 50.0, 0.45)
            if a:
                acts.append(a)
        self.assertEqual(acts, [])

    def test_changing_band_still_mutes(self):
        acts = []
        for i in range(45):
            a, _ = self.d.frame(i * 2, BADGE if i < 5 else NONE, False, 50.0, 0.05)
            if a:
                acts.append(a)
        self.assertEqual(acts, ["mute"])

    def test_graphics_just_appeared_block_mute(self):
        # Mega weather 2026-11-03 20:55: badge gone, band low, then a fixed map band 0.6-0.9
        # appears just before the 25 s window fills; it must not mute
        d = Decider(miss_s=25, max_mute_s=720)
        d.state(0, "mega", True, False)
        acts = []
        for i in range(60):
            band = 0.05 if i < 14 else 0.85
            a, _ = d.frame(i * 2, BADGE if i < 5 else NONE, False, 8.0, band)
            if a:
                acts.append(a)
        self.assertEqual(acts, [])

    def test_news_after_break_unmutes(self):
        acts = []
        for i in range(120):
            band = 0.05 if i < 60 else 0.6  # ads, then news with a fixed band from t=120
            a, why = self.d.frame(i * 2, BADGE if i < 5 else NONE, False, 50.0, band)
            if a:
                acts.append((i * 2, a, why))
        self.assertEqual([a for _, a, _ in acts], ["mute", "unmute"])
        self.assertEqual(acts[1][2], "news band")
        self.assertTrue(150 <= acts[1][0] <= 200)

    def test_short_band_blip_in_ads_keeps_mute(self):
        acts = []
        for i in range(120):
            band = 0.6 if 60 <= i < 70 else 0.05  # 20 s of stable band inside the break
            a, _ = self.d.frame(i * 2, BADGE if i < 5 else NONE, False, 50.0, band)
            if a:
                acts.append(a)
        self.assertEqual(acts, ["mute"])

    def test_never_arms_without_badge(self):
        d = Decider(miss_s=60, max_mute_s=720, zap_in=False)
        d.state(0, "alpha", True, False)
        self.assertEqual(run(d, [NONE] * 200), [])

    def test_zap_in_mutes_after_60s_without_badge(self):
        acts = run(self.d, [NONE] * 60)
        self.assertEqual([a for _, a, _ in acts], ["mute"])
        self.assertTrue(56 <= acts[0][0] <= 64)  # window counts as full 3 s early
        self.assertTrue(acts[0][2].startswith("zap-in"))

    def test_zap_in_blocked_by_fixed_band(self):
        acts = [a for i in range(60) for a in [self.d.frame(i * 2, NONE, False, 50.0, 0.3)[0]] if a]
        self.assertEqual(acts, [])

    def test_no_zap_in_after_user_unmute(self):
        run(self.d, [NONE] * 40)  # zap-in mute at ~60 s
        self.assertTrue(self.d.holding)
        self.d.state(100, "alpha", True, False)  # user unmuted
        self.assertEqual(run(self.d, [NONE] * 100, start=102), [])

    def test_arm_on_per_channel(self):
        d = Decider(miss_s=25, max_mute_s=720, arm_on_by_channel={"mega": 0.45}, zap_in=False)
        d.state(0, "mega", True, False)
        acts = run(d, [0.47] * 5 + [NONE] * 20)
        self.assertEqual([a for _, a, _ in acts], ["mute"])

    def test_does_not_mute_when_tv_already_muted(self):
        self.assertEqual(run(self.d, [BADGE] * 5 + [NONE] * 40, tv_muted=True), [])

    def test_max_mute_time(self):
        acts = run(self.d, [BADGE] * 5 + [NONE] * 500)
        self.assertEqual([a for _, a, _ in acts], ["mute", "unmute"])
        self.assertEqual(acts[1][2], "max mute time")

    def test_channel_change_unmutes(self):
        run(self.d, [BADGE] * 5 + [NONE] * 40)
        self.assertTrue(self.d.holding)
        self.assertEqual(self.d.state(100, "skai", True, True), ("unmute", "channel/source change"))
        self.assertFalse(self.d.holding)

    def test_user_unmute_backs_off(self):
        run(self.d, [BADGE] * 5 + [NONE] * 40)
        muted_at = self.d.muted_at
        self.assertEqual(self.d.state(muted_at + 5, "alpha", True, False), (None, None))  # HA lag
        self.assertEqual(self.d.state(muted_at + 20, "alpha", True, False), (None, "user unmuted"))
        self.assertEqual(run(self.d, [NONE] * 100, start=muted_at + 22), [])

    def test_faint_badge_does_not_mute(self):
        # semi-transparent badge: scores between absent_below and badge_on for minutes
        self.assertEqual(run(self.d, [BADGE] * 5 + [0.42] * 200), [])

    def test_mostly_gone_mutes(self):
        # one stray mid score per 30 s does not stop a mute
        scores = [BADGE] * 5 + ([NONE] * 14 + [0.4]) * 6
        self.assertEqual([a for _, a, _ in run(self.d, scores)], ["mute"])

    def test_no_immediate_remute_after_unmute(self):
        acts = run(self.d, [BADGE] * 5 + [NONE] * 40 + [BADGE] * 2 + [NONE] * 10)
        self.assertEqual([a for _, a, _ in acts], ["mute", "unmute"])

    def test_tv_off_while_muted_releases_without_unmute(self):
        run(self.d, [BADGE] * 5 + [NONE] * 40)
        self.assertEqual(self.d.state(200, None, False, True), (None, "channel/source change"))


if __name__ == "__main__":
    unittest.main()
