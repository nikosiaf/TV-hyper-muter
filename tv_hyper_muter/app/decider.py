"""Mute decisions, kept free of I/O so they can be unit-tested and replayed.

Feed it `state()` every poll and `frame()` for every badge score; it returns the action to
take ("mute", "unmute" or None) plus a reason.
"""


class Decider:
    def __init__(self, miss_s=25, max_mute_s=720, on=0.5, off=0.45, arm_sightings=3, grace_s=15,
                 absent=0.30, absent_frac=0.9, arm_gap_s=10,
                 max_mute_by_channel=None, static=2.0, static_frac=0.5, news_band=0.3, news_unmute=0.4, news_hold_s=30,
                 arm_on_by_channel=None, zap_in=True, zap_s=60, zap_absent=0.25, zap_band=0.15,
                 band_now=0.5, band_now_n=5, absent_by_channel=None, max_gap_s=8, no_picture_s=60,
                 unmute_hold_s=0, unmute_hold_by_channel=None, hold_dips=2, zap_settle_s=8, zap_window_s=720,
                 caption_min=10.0):
        self.miss_s, self.max_mute_s, self.grace_s = miss_s, max_mute_s, grace_s
        self.on, self.off, self.arm_sightings = on, off, arm_sightings
        self.absent, self.absent_frac = absent, absent_frac
        # per-channel 'clearly gone' level (Kontra ads score up to 0.38, programme 0.70-0.75)
        self.absent_by_channel = absent_by_channel or {}
        self.arm_gap_s = arm_gap_s
        # still picture = not an ad (ads were still at most ~10 s in labelled recordings)
        self.static, self.static_frac = static, static_frac
        # fixed bottom band (news ticker, talk-show captions) = not an ad (Alpha news 2026-11-03)
        self.news_band = news_band
        # ... or fixed graphics that just appeared: median of the last band_now_n frames (Mega weather 2026-11-03)
        self.band_now, self.band_now_n = band_now, band_now_n
        # while muted: fixed band for news_hold_s = news right after the break (Open 2026-11-03)
        self.news_unmute, self.news_hold_s = news_unmute, news_hold_s
        # per-channel cap: Skai news can follow an ad break with no badge (2026-11-03)
        self.max_mute_by_channel = max_mute_by_channel or {}
        # per-channel 'badge seen' level for arming only (Mega badge 0.45-0.50); unmute keeps `on`
        self.arm_on_by_channel = arm_on_by_channel or {}
        # zapped into a break: unarmed since a channel change -> stricter mute rule (Skai 2026-11-03)
        self.zap_in, self.zap_s, self.zap_absent, self.zap_band = zap_in, zap_s, zap_absent, zap_band
        # evidence must be fresh: no gap over max_gap_s inside a mute window (frames normally
        # come every 2-3 s, max 6 s in 25k trial frames); while muted, no frame for no_picture_s
        # releases the mute instead of waiting for the max mute time
        self.max_gap_s, self.no_picture_s = max_gap_s, no_picture_s
        # badge back must last unmute_hold_s before unmuting: Skai promos for its own shows carry
        # the badge for 18-30 s inside a break (2026-11-04); hold_dips frames in a row below the
        # absent level end the run
        self.unmute_hold_s = unmute_hold_s
        self.unmute_hold_by_channel = unmute_hold_by_channel or {}
        self.hold_dips = hold_dips
        # ... unless the programme's own caption is next to the badge (Skai shows 'Κατάλληλο για
        # όλους' when a programme resumes; its promos never do): then unmute at once
        self.caption_min = caption_min
        self.back_since, self.back_ok, self.dips = None, False, 0
        # right after a channel change the TV's own channel banner can look like a badge for 4-6 s
        # (score ~0.52, Skai/Mega 2026-11-04): such sightings must not arm the mute
        self.zap_settle_s = zap_settle_s
        # the zap-in rule is for switching INTO a break; after this long on a channel with no badge
        # seen, the programme itself has no badge (live football on Mega 2026-11-04 21:18, 26 min in)
        self.zap_window_s = zap_window_s
        self.changed_at = None
        self.last_frame_t = None
        self.last_score = None
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

    def mute_cap(self):
        return self.max_mute_by_channel.get(self.channel, self.max_mute_s)

    def tick(self, t):
        """Time-only checks while we hold a mute; call often, frames or not."""
        if not self.holding:
            return None, None
        why = None
        if t - self.muted_at >= self.mute_cap():
            why = "max mute time"
        elif t - max(self.muted_at, self.last_frame_t or self.muted_at) >= self.no_picture_s:
            why = "no picture"
        if why is None:
            return None, None
        self.muted_at = None
        self._reset()
        self.fresh = False
        return "unmute", why

    def cancel_mute(self):
        """The mute command failed or the context changed: forget the mute, rebuild evidence."""
        self.muted_at = None
        self.hist = []

    @property
    def phase(self):
        if self.channel is None:
            return "idle"
        if self.holding:
            return "muted"
        if self.seen >= self.arm_sightings and self.last_seen is not None:
            # same 'clearly gone' level the mute rule uses, so a faint badge (Mega 0.40-0.50)
            # does not flicker the status between armed and possible_ad
            gone = (self.last_score is not None
                    and self.last_score < self.absent_by_channel.get(self.channel, self.absent)
                    and self.last_frame_t - self.last_seen >= 6)
            return "possible_ad" if gone else "armed"
        return "learning"

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
            self.changed_at = t
            self._reset()
            self.fresh = True
            if self.holding:
                self.muted_at = None
                return ("unmute" if tv_on else None), "channel/source change"
        return None, None

    def frame(self, t, score, tv_muted, motion=99.0, band=0.0, caption=None):
        if self.channel is None:
            return None, None
        self.last_frame_t, self.last_score = t, score
        settling = self.changed_at is not None and t - self.changed_at < self.zap_settle_s
        if score >= self.arm_on_by_channel.get(self.channel, self.on) and not settling:
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
            hold = self.unmute_hold_by_channel.get(self.channel, self.unmute_hold_s)
            if score < self.absent_by_channel.get(self.channel, self.absent):
                self.dips += 1
                if self.dips >= self.hold_dips:
                    self.back_since, self.back_ok = None, False
            else:
                self.dips = 0
            if score >= self.on and self.back_since is None:
                self.back_since = t
            if self.back >= 2 and self.back_since is not None:
                self.back_ok = True
            captioned = caption is not None and caption >= self.caption_min and score >= self.on
            if captioned or (self.back_ok and t - self.back_since >= hold):
                self.back_since, self.back_ok, self.dips = None, False, 0
                self.muted_at = None
                self.hist = []
                self.fresh = False
                return "unmute", "badge back with programme caption" if captioned and hold else "badge back"
            if self.news_since is not None and t - self.news_since >= self.news_hold_s:
                self.muted_at = None
                self._reset()  # back off until the badge returns
                self.fresh = False
                return "unmute", "news band"
            return self.tick(t)
        # mute only when the badge is clearly gone (score below `absent` in most of the last
        # miss_s seconds), not merely faint: Skai's semi-transparent badge sits at 0.3-0.49
        self.hist = [h for h in self.hist + [(t, score, motion, band)]
                     if t - h[0] <= max(self.miss_s, self.zap_s)]
        armed = self.seen >= self.arm_sightings and self.last_seen is not None
        zapping = (self.zap_in and self.fresh
                   and (self.changed_at is None or t - self.changed_at <= self.zap_window_s))
        if not armed and not zapping:
            return None, None
        win, absent, nb = ((self.miss_s, self.absent_by_channel.get(self.channel, self.absent), self.news_band) if armed
                           else (self.zap_s, self.zap_absent, self.zap_band))
        hw = [h for h in self.hist if t - h[0] <= win]
        # the window must be covered by observations: starts near its beginning, no big gaps
        ts = [h[0] for h in hw]
        full = (ts[0] <= t - win + 3
                and all(b - a <= self.max_gap_s for a, b in zip(ts, ts[1:])))
        gone = sum(h[1] < absent for h in hw) >= self.absent_frac * len(hw)
        still = sum(h[2] < self.static for h in hw) >= self.static_frac * len(hw)
        bands = sorted(h[3] for h in hw)
        recent = sorted(h[3] for h in hw[-self.band_now_n:])
        news = bands[len(bands) // 2] >= nb or recent[len(recent) // 2] >= self.band_now
        if not tv_muted and full and gone and not still and not news:
            self.muted_at = t
            self.back = 0
            self.mhist, self.news_since = [], None
            self.back_since, self.back_ok, self.dips = None, False, 0
            if armed:
                return "mute", f"badge missing {int(t - self.last_seen)} s"
            return "mute", "zap-in: no badge since channel change"
        return None, None
