# TV Ad Mute

## How it decides

1. Works only when the TV is on, the source is `live_source` and the channel title matches
   one of `channels`.
2. Arms after the badge was seen `arm_sightings` times on the current channel, so shows
   without a badge are never muted.
3. Mutes when the badge score was below `absent_below` in at least `absent_fraction` of the
   last `miss_seconds` (clearly gone, not just faint), and the TV is not already muted.
4. Unmutes when the badge is back in 2 frames in a row, after `max_mute_minutes`, or when
   the channel, source or power changes.
5. If you unmute during an ad, it backs off until the badge has been seen again. If you
   muted the TV yourself, it never unmutes it.
6. Stopping the add-on releases its mute.

## Options

| Option | Default | Meaning |
|---|---|---|
| `tv_entity` | `media_player.tv` | LG webOS media player |
| `live_source` | `Live TV` | Source name that means broadcast TV |
| `hyperion_host` / `hyperion_port` | `192.168.10.30` / `8090` | Hyperion.NG websocket on the TV |
| `enable_entity` | empty | Optional `input_boolean` (or any on/off entity); when off, the add-on does nothing |
| `dry_run` | `false` | Log decisions without muting |
| `frame_interval_s` | `2` | Seconds between frames |
| `state_poll_s` | `5` | Seconds between TV state checks |
| `miss_seconds` | `60` | Length of the window checked before muting. Shorter mutes sooner but risks false mutes |
| `absent_below` / `absent_fraction` | `0.3` / `0.9` | Badge counts as gone below this score, in at least this share of the window |
| `max_mute_minutes` | `12` | Safety limit |
| `badge_on` / `badge_off` | `0.5` / `0.45` | Score above `badge_on` = badge present, below `badge_off` = absent |
| `search_shift` | `2` | Pixels the badge may move around its calibrated spot |
| `arm_sightings` | `3` | Badge sightings needed before muting is possible on a channel |
| `save_frames` | `true` | Save the frame at every mute/unmute |
| `keep_days` | `14` | Days of logs to keep |
| `channels` | 9 Greek channels | `name`, `match` (regex on the channel title), badge centre `y`, `x` and radius `r` on Hyperion's 320×180 image |

## Status entity

`sensor.tv_admute` shows `idle`, `watching`, `muted`, `disabled` or `stopped`, with
attributes `channel`, `badge_score`, `mutes_today` and `dry_run`. It is recreated when the
add-on starts (it is not stored by Home Assistant across restarts).

## Logs

`/share/tv_admute/<date>/`: `events.jsonl` (every decision), `scores.csv` (badge score per
frame) and the saved frames. The add-on log shows the same events.

## Adding a channel

Watch the channel for a minute while it shows the badge, take a few frames from Hyperion
and find the badge centre on the 320×180 image (top-left is 0,0). Add an entry to
`channels` with a `match` regex for the channel title as Home Assistant reports it.
