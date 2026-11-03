"""Mute decisions, kept free of I/O so they can be unit-tested and replayed.

Feed it `state()` every poll and `frame()` for every badge score; it returns the action to
take ("mute", "unmute" or None) plus a reason.
"""


class Decider:
    def __init__(self, miss_s=25, max_mute_s=720, on=0.5, off=0.45, arm_sightings=3, grace_s=15,
                 absent=0.30, absent_frac=0.9, arm_gap_s=10,
                 max_mute_by_channel=None, static=2.0, static_frac=0.5, news_band=0.3, news_unmute=0.4, news_hold_s=30,
                 arm_on_by_channel=None, zap_in=True, zap_s=60, zap_absent=0.25, zap_band=0.15):
        self.miss_s, self.max_mute_s, self.grace_s = miss_s, max_mute_s, grace_s
        self.on, self.off, self.arm_sightings = on, off, arm_sightings
        self.absent, self.absent_frac = absent, absent_frac
        self.arm_gap_s = arm_gap_s
        # still picture = not an ad (ads were still at most ~10 s in labelled recordings)
        self.static, self.static_frac = static, static_frac
        # fixed bottom band (news ticker, talk-show captions) = not an ad (Alpha news 2026-11-03)
        self.news_band = news_band
        # while muted: fixed band for news_hold_s = news right after the break (Open 2026-11-03)
        self.news_unmute, self.news_hold_s = news_unmute, news_hold_s
        # per-channel cap: Skai news can follow an ad break with no badge (2026-11-03)
        self.max_mute_by_channel = max_mute_by_channel or {}
        # per-channel 'badge seen' level for arming only (Mega badge 0.45-0.50); unmute keeps `on`
        self.arm_on_by_channel = arm_on_by_channel or {}
        # zapped into a break: unarmed since a channel change -> stricter mute rule (Skai 2026-11-03)
        self.zap_in, self.zap_s, self.zap_absent, self.zap_band = zap_in, zap_s, zap_absent, zap_band
        self.fresh = False  # True from a channel change until the badge arms or any unmute
        self.channel = None
        self.muted_at = None  # time we muted; None while we hold no mute
        self._reset()

    def _reset(self):
        self.seen = 0
        self.last_seen = None
        self.back = 0
        self.hist = []  # (t, score, motion, band) over the last miss_s seconds

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
            self.fresh = False
            return None, "user unmuted"
        if channel != self.channel:
            self.channel = channel
            self._reset()
            self.fresh = True
            if self.holding:
                self.muted_at = None
                return ("unmute" if tv_on else None), "channel/source change"
        return None, None

    def frame(self, t, score, tv_muted, motion=99.0, band=0.0):
        if self.channel is None:
            return None, None
        if score >= self.arm_on_by_channel.get(self.channel, self.on):
            # arm only on a steady badge: sightings spread out over minutes (news graphics in
            # the badge corner) must not add up to an arm
            if (self.seen < self.arm_sightings and self.last_seen is not None
                    and t - self.last_seen > self.arm_gap_s):
                self.seen = 0
            self.seen += 1
            self.last_seen = t
            if self.seen >= self.arm_sightings:
                self.fresh = False
        if score >= self.on:
            self.back += 1
        elif score < self.off:
            self.back = 0
        if self.holding:
            self.mhist = [h for h in self.mhist + [(t, band)] if t - h[0] <= self.miss_s]
            mb = sorted(h[1] for h in self.mhist)
            if mb[len(mb) // 2] >= self.news_unmute and t - self.muted_at >= self.miss_s:
                self.news_since = self.news_since if self.news_since is not None else t
            else:
                self.news_since = None
            if self.back >= 2:
                self.muted_at = None
                self.hist = []
                self.fresh = False
                return "unmute", "badge back"
            if self.news_since is not None and t - self.news_since >= self.news_hold_s:
                self.muted_at = None
                self._reset()  # back off until the badge returns
                self.fresh = False
                return "unmute", "news band"
            if t - self.muted_at >= self.max_mute_by_channel.get(self.channel, self.max_mute_s):
                self.muted_at = None
                self._reset()
                self.fresh = False
                return "unmute", "max mute time"
            return None, None
        # mute only when the badge is clearly gone (score below `absent` in most of the last
        # miss_s seconds), not merely faint: Skai's semi-transparent badge sits at 0.3-0.49
        self.hist = [h for h in self.hist + [(t, score, motion, band)]
                     if t - h[0] <= max(self.miss_s, self.zap_s)]
        armed = self.seen >= self.arm_sightings and self.last_seen is not None
        if not armed and not (self.zap_in and self.fresh):
            return None, None
        win, absent, nb = ((self.miss_s, self.absent, self.news_band) if armed
                           else (self.zap_s, self.zap_absent, self.zap_band))
        hw = [h for h in self.hist if t - h[0] <= win]
        full = self.hist[0][0] <= t - win + 3
        gone = sum(h[1] < absent for h in hw) >= self.absent_frac * len(hw)
        still = sum(h[2] < self.static for h in hw) >= self.static_frac * len(hw)
        bands = sorted(h[3] for h in hw)
        news = bands[len(bands) // 2] >= nb
        if not tv_muted and full and gone and not still and not news:
            self.muted_at = t
            self.back = 0
            self.mhist, self.news_since = [], None
            if armed:
                return "mute", f"badge missing {int(t - self.last_seen)} s"
            return "mute", "zap-in: no badge since channel change"
        return None, None
