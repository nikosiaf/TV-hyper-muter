"""Mute decisions, kept free of I/O so they can be unit-tested and replayed.

Feed it `state()` every poll and `frame()` for every badge score; it returns the action to
take ("mute", "unmute" or None) plus a reason.
"""


class Decider:
    def __init__(self, miss_s=30, max_mute_s=720, on=0.5, off=0.45, arm_sightings=3, grace_s=15,
                 absent=0.30, absent_frac=0.9, arm_gap_s=10,
                 max_mute_by_channel=None):
        self.miss_s, self.max_mute_s, self.grace_s = miss_s, max_mute_s, grace_s
        self.on, self.off, self.arm_sightings = on, off, arm_sightings
        self.absent, self.absent_frac = absent, absent_frac
        self.arm_gap_s = arm_gap_s
        # per-channel cap: Skai news can follow an ad break with no badge (2026-11-03)
        self.max_mute_by_channel = max_mute_by_channel or {}
        self.channel = None
        self.muted_at = None  # time we muted; None while we hold no mute
        self._reset()

    def _reset(self):
        self.seen = 0
        self.last_seen = None
        self.back = 0
        self.hist = []  # (t, score) over the last miss_s seconds

    @property
    def holding(self):
        return self.muted_at is not None

    def state(self, t, channel, tv_on, tv_muted):
        """channel = calibrated channel name on Live TV, else None."""
        if self.holding and tv_on and not tv_muted and t - self.muted_at > self.grace_s:
            # the user unmuted during our mute (HA state may lag our own mute by a few
            # seconds, hence the grace): back off until the badge is seen again
            self.muted_at = None
            self._reset()
            return None, "user unmuted"
        if channel != self.channel:
            self.channel = channel
            self._reset()
            if self.holding:
                self.muted_at = None
                return ("unmute" if tv_on else None), "channel/source change"
        return None, None

    def frame(self, t, score, tv_muted):
        if self.channel is None:
            return None, None
        if score >= self.on:
            # arm only on a steady badge: sightings spread out over minutes (news graphics in
            # the badge corner) must not add up to an arm
            if (self.seen < self.arm_sightings and self.last_seen is not None
                    and t - self.last_seen > self.arm_gap_s):
                self.seen = 0
            self.seen += 1
            self.last_seen = t
            self.back += 1
        elif score < self.off:
            self.back = 0
        if self.holding:
            if self.back >= 2:
                self.muted_at = None
                self.hist = []
                return "unmute", "badge back"
            if t - self.muted_at >= self.max_mute_by_channel.get(self.channel, self.max_mute_s):
                self.muted_at = None
                self._reset()
                return "unmute", "max mute time"
            return None, None
        # mute only when the badge is clearly gone (score below `absent` in most of the last
        # miss_s seconds), not merely faint: Skai's semi-transparent badge sits at 0.3-0.49
        self.hist = [(a, b) for a, b in self.hist + [(t, score)] if t - a <= self.miss_s]
        armed = self.seen >= self.arm_sightings and self.last_seen is not None
        full = self.hist[0][0] <= t - self.miss_s + 3
        gone = sum(b < self.absent for _, b in self.hist) >= self.absent_frac * len(self.hist)
        if armed and not tv_muted and full and gone:
            self.muted_at = t
            self.back = 0
            return "mute", f"badge missing {int(t - self.last_seen)} s"
        return None, None
