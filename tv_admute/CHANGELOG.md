# Changelog

## 0.2.0

- Mute only when the badge is clearly gone (score below 0.30 in 90 % of the last minute), not
  merely faint. Fixes repeated false mutes on Skai's news and talk shows, whose badge is
  semi-transparent. On the 2026-11-03 morning trial: false mutes 9 → 3, all 7 ad breaks kept.
- Fresh window after every unmute, so a mute cannot re-trigger on frames from before it.

## 0.1.0

- First add-on version of the TV ad muter trial: age-rating badge detector (ring shape,
  any digit), 9 calibrated Greek channels, mute rules with user-override handling,
  status sensor, daily logs in `/share/tv_admute`.
