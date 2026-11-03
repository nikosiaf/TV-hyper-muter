import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tv_admute", "app"))
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
        self.assertEqual(acts[0][0], 8 + 60)  # last badge at t=8
        self.assertEqual(acts[1][2], "badge back")

    def test_single_badge_frame_does_not_unmute(self):
        acts = run(self.d, [BADGE] * 5 + [NONE] * 35 + [BADGE] + [NONE] * 5)
        self.assertEqual([a for _, a, _ in acts], ["mute"])

    def test_never_arms_without_badge(self):
        self.assertEqual(run(self.d, [NONE] * 200), [])

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

    def test_tv_off_while_muted_releases_without_unmute(self):
        run(self.d, [BADGE] * 5 + [NONE] * 40)
        self.assertEqual(self.d.state(200, None, False, True), (None, "channel/source change"))


if __name__ == "__main__":
    unittest.main()
