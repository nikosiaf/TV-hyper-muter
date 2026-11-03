# Changelog

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
