# Changelog

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
