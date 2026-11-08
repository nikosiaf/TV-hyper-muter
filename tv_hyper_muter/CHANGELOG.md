# Changelog

## 0.13.0

- Sports veto: live football has no age-rating badge, so the zap-in rule muted a Skai match on
  2026-11-08 (twice, 18:36 and 18:43) and a Mega match on 2026-11-04. Now, when a quarter of the
  picture is pitch-green (yellow-green grass, median over 25 s), the muter does not mute for the
  next 3 minutes, and a mute it holds is released at once ("sport (pitch on screen)").
  New options `sports_pitch` (0.25, `0` = off) and `sports_memory_s` (180).
- Measured on recordings: 0 of 961 ad windows reach 0.15 (green-screen promos, teal product ads
  and a green olive-net teleshopping spot included); 81 % of football windows reach 0.25, the
  rest are close-ups and replays of up to ~30 s, covered by the 3 minutes.
- The status sensor has a `sport` attribute; scores.csv has an 8th column with the pitch share.

## 0.12.0

- Channels' own promos no longer unmute during a break. Skai, Open and Star show the age badge on
  promos for their own shows ("ΣΑΒΒΑΤΟ 14:30"), which looked like the programme coming back:
  5 premature unmutes a day on Skai alone. New per-channel option `unmute_hold_s`: the badge must
  stay that long before unmuting. Defaults: Skai 60 s, Open 45 s, Star 30 s.
- Skai: new per-channel option `caption`. When a programme resumes, Skai shows a small caption
  next to the badge ("Κατάλληλο για όλους"); promos never do. With the caption the muter unmutes
  at once, without the hold (7 of 10 real returns on 2026-11-04/05).
- Star: second badge shape bottom-right (`alt: "168,301,4"`), the age circle Star shows in series
  and shows without the top-right badge. Its programme scored 0.1-0.25 before, so returns were missed.
- scores.csv has a 7th column with the caption score (empty for channels without `caption`).
- Replay of 2026-11-04/05: 54 -> 36 and 24 -> 13 mute/unmute switches; every removed one was a
  promo unmute and the re-mute after it. Real returns without a caption come 30-60 s later.

## 0.11.1

- The zap-in rule (muting when you switch into a break before any badge was seen) now only
  applies in the first 12 minutes after a channel change. Live football on Mega (no age badge,
  the "UCL" logo in the badge corner) was muted 26 minutes in. Replay of 2026-11-03/04: that
  mute and one Mega break after a badge-less programme 12.8 min in are no longer muted;
  nothing else changes.

## 0.11.0

- Badge sightings in the first 8 s after a channel change no longer arm the mute: the TV's own
  channel banner scores like a faint badge (~0.52) for 4-6 s. On 2026-11-04 20:35 this armed
  the muter on the Skai news (no badge), which then muted the news. Replay of 2026-11-03/04:
  that mute and one other banner-armed Skai mute disappear, a real Skai break is still muted
  (by the zap-in rule, ~1 min later), nothing else changes.
- Internal, not yet an option: optional per-channel "unmute hold" (badge must stay for N s
  before unmuting) for Skai's own promos; off by default while data is collected.
- Status `possible_ad` uses the same "clearly gone" level as the mute rule (`absent_below`,
  or the channel's own), so a faint badge (Mega 0.40-0.50) no longer flickers the status
  between `armed` and `possible_ad`.

## 0.10.0

Reliability release, from an external code review.

- Mute ownership is tracked apart from the decision: owned only after Home Assistant accepted
  the mute, kept until an unmute is accepted. A failed unmute is retried with backoff (2 s up
  to 60 s) instead of crashing the add-on and leaving the TV muted.
- An owned mute is saved in `/data`; after a crash or a failed stop, the next start releases
  it once the TV is seen on and muted.
- `max_mute_minutes` is checked on every loop, frames or not. While muted, 60 s without a
  picture unmutes ("no picture").
- Mutes need fresh evidence: the window must be covered by frames with no gap over 8 s
  (trial: 25k frames, max gap 6 s). The TV is checked again right before muting.
- Frames of other 16:9 sizes are scaled to 320×180, other shapes refused; Hyperion messages
  over 4 MB and over-long handshakes are refused; a bad frame no longer stops the loop.
- Status sensor: new states `learning`, `armed`, `possible_ad`, `would_mute` (dry run),
  `releasing`, `no_picture` (was `watching`); new attributes `reason`, `mute_left_s`,
  `last_frame`, `problem`.
- Dry run: a held "would mute" is no longer dropped after 15 s as a user unmute.
- Monotonic clock for all durations; gradient computed once per frame, ring templates cached
  (scores unchanged, ~20 % faster).
- 16 new runner tests (fake HA, fake Hyperion, fake clock). Replay of 7,423 trial frames
  gives the same 27 decisions as 0.9.1.

## 0.9.1

- Logo twice the size (500×200) with the name in red.

## 0.9.0

- New cartoon icon and logo.
- Switching `enable_entity` off now logs the released mute with reason `disabled` (was
  `channel/source change`).
- DOCS: all current options and rules (still picture, bottom band, zap-in, news unmute,
  per-channel fields), and a dashboard card: the TV tile with an on/off button on the same row.

## 0.8.2

- `enable_entity`: logs `enabled` / `disabled` when the switch changes, and the status sensor
  shows `disabled` at once. A missing entity no longer stops the muter with a 404 every poll:
  it logs `enable_entity_missing` once and keeps working as enabled.

## 0.8.1

- Fix: every Home Assistant call failed with 401 Unauthorized. The base image's s6 init
  started the app with a clean environment, without `SUPERVISOR_TOKEN` (and `TZ`, so log
  times were UTC). The app now runs directly as the container entrypoint.

## 0.8.0

- New channel Kontra (badge y 12, x 300, r 4.5; programme 0.70-0.75). Its ads score up to
  0.38, so it gets a per-channel `absent_below` 0.4 (new optional channel field).

## 0.7.0

- No mute while fixed graphics have just appeared: band median of the last 5 frames (10 s)
  >= `news_band_now` 0.5. Mega 2026-11-03 20:55: the weather map (band 0.57-0.88) appeared just
  before the 25 s window filled and was muted; all real ad mutes that day were at <= 0.33.
- Skai `max_mute_minutes` 9 -> 11: an 11 min break on 2026-11-03 21:47 was unmuted by the
  cap during the promos at the end.

## 0.6.0

- Per-channel `arm_on` (badge level that counts for arming only); Mega 0.45: its badge scores
  0.45-0.50 in programme (0 % above 0.5 before). Unmute still needs 0.5 (a Mitsubishi ad hit
  0.45-0.47 twice in a row).
- Zap-in (`zap_in`): after a channel change with no badge seen yet, mute when the badge score
  is below 0.25 in 90 % of 60 s and the bottom band is changing (median < 0.15). Off again after
  arming or any unmute. Replay 2026-11-03 19:03-21:20: catches the Skai break zapped into, no
  false mutes.

## 0.5.1

- Unmute when the news follows an ad break: while muted, band median >= `news_unmute` 0.4 for
  `news_hold_s` 30 s. Open 2026-11-03 19:39: would unmute 35 s into the news instead of the
  12 min cap; no unmute in 16 min of labelled ads.

## 0.5.0

- No mute while the bottom band (rows 120-180) stays the same as 10 s earlier (median match
  >= `news_band` 0.3 over the window): news tickers and talk-show caption bands. Alpha news
  2026-11-03 had badge-less segments and was muted 3 times; its band scores 0.32-0.52,
  ads median 0.04. scores.csv gets a 6th column (band).

## 0.4.2

- Mute after 25 s without the badge (was 30 s). Replay of 2026-11-03: no new false mutes,
  one Skai break 46 s sooner. 20 s added a 4.6 min false mute on a Skai talk show.

## 0.4.1

- Channels can have extra badge shapes (`alt: "y,x,r;..."`). Open gets its small talk-show
  badge (9,308,3): live talk-show frames 0 % -> 100 % above 0.5, no ad frame above 0.5.

## 0.4.0

- Renamed to TV hyper muter: slug `tv_hyper_muter`, status `sensor.tv_hyper_muter`, logs in
  `/share/tv_hyper_muter`. HA sees it as a new add-on; remove the old TV Ad Mute entry if listed.

## 0.3.1

- Fix install: add build.yaml (HA base image per arch) and an Alpine default for
  BUILD_FROM. The Supervisor no longer supplies a base image when none is given.

## 0.3.0

- No mute while the picture is still (centre of the screen barely changes in half of the
  window). Still screens at the start of the news looked like an ad break. In labelled
  recordings ads were never still for more than ~10 s. Options `static_motion`,
  `static_fraction`; scores.csv gets a motion column.

## 0.2.3

- Mute after 30 s without the badge (was 60 s): breaks are muted ~26 s sooner.

## 0.2.2

- Optional per-channel `max_mute_minutes`; Skai set to 9 (news can follow a break).

## 0.2.1

- Arm only when the badge sightings come within 10 s of each other. Scattered news graphics
  had added up to an arm and muted the Skai news.

## 0.2.0

- Mute only when the badge is clearly gone (score below 0.30 in 90 % of the last minute), not
  merely faint. Fixes repeated false mutes on Skai's news and talk shows, whose badge is
  semi-transparent. On the 2026-11-03 morning trial: false mutes 9 → 3, all 7 ad breaks kept.
- Fresh window after every unmute, so a mute cannot re-trigger on frames from before it.

## 0.1.0

- First add-on version of the TV ad muter trial: age-rating badge detector (ring shape,
  any digit), 9 calibrated Greek channels, mute rules with user-override handling,
  status sensor, daily logs in `/share/tv_admute`.
