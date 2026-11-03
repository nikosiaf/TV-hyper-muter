# TV hyper muter

## How it decides

1. Works only when the TV is on, the source is `live_source` and the channel title matches
   one of `channels`.
2. Arms after the badge was seen `arm_sightings` times, each within 10 s of the previous one,
   on the current channel, so shows without a badge are never muted.
3. Mutes when the badge score was below `absent_below` in at least `absent_fraction` of the
   last `miss_seconds` (clearly gone, not just faint), and the TV is not already muted. It does
   not mute when:
   - the picture is still (centre motion below `static_motion` in `static_fraction` of the
     window): a paused or frozen picture is not an ad;
   - the bottom band (news ticker, captions) stays the same: median band match at least
     `news_band` over the window, or at least `news_band_now` over the last 10 s (fixed
     graphics that just appeared, such as a weather map).
4. Zap-in (`zap_in`): after a channel change, before the badge has armed, it mutes with a
   stricter rule: score below 0.25 in 90 % of 60 s, and a changing bottom band.
5. Unmutes when the badge is back in 2 frames in a row, when the news follows the break (band
   match at least `news_unmute` for `news_hold_s` while muted), after `max_mute_minutes`, or
   when the channel, source or power changes, or `enable_entity` is switched off.
6. If you unmute during an ad, it backs off until the badge has been seen again. If you
   muted the TV yourself, it never unmutes it.
7. Stopping the add-on releases its mute.

## Options

| Option | Default | Meaning |
|---|---|---|
| `tv_entity` | `media_player.tv` | LG webOS media player |
| `live_source` | `Live TV` | Source name that means broadcast TV |
| `hyperion_host` / `hyperion_port` | `192.168.10.30` / `8090` | Hyperion.NG websocket on the TV |
| `enable_entity` | empty | Optional `input_boolean` (or any on/off entity); when off, the add-on does nothing. Changes are logged as `enabled` / `disabled` |
| `dry_run` | `false` | Log decisions without muting |
| `frame_interval_s` | `2` | Seconds between frames |
| `state_poll_s` | `5` | Seconds between TV state checks |
| `miss_seconds` | `25` | Length of the window checked before muting. Shorter mutes sooner but risks false mutes |
| `absent_below` / `absent_fraction` | `0.3` / `0.9` | Badge counts as gone below this score, in at least this share of the window |
| `max_mute_minutes` | `12` | Safety limit |
| `badge_on` / `badge_off` | `0.5` / `0.45` | Score above `badge_on` = badge present, below `badge_off` = absent |
| `search_shift` | `2` | Pixels the badge may move around its calibrated spot |
| `arm_sightings` | `3` | Badge sightings needed before muting is possible on a channel |
| `static_motion` / `static_fraction` | `2.0` / `0.5` | Still-picture veto: motion below this in this share of the window |
| `news_band` | `0.3` | Bottom-band veto over the whole window |
| `news_band_now` | `0.5` | Bottom-band veto over the last 10 s |
| `news_unmute` / `news_hold_s` | `0.4` / `30` | While muted: unmute when the band stays this fixed for this long |
| `zap_in` | `true` | Allow the zap-in rule after a channel change |
| `save_frames` | `true` | Save the frame at every mute/unmute |
| `keep_days` | `14` | Days of logs to keep |
| `channels` | 10 Greek channels | `name`, `match` (regex on the channel title), badge centre `y`, `x` and radius `r` on Hyperion's 320×180 image |

Optional per-channel fields: `max_mute_minutes` (own safety limit), `alt` (more badge shapes,
`"y,x,r;y,x,r"`), `arm_on` (lower 'badge seen' level for arming only, for faint badges) and
`absent_below` (own 'clearly gone' level, for channels whose ads score high).

## Status entity

`sensor.tv_hyper_muter` shows `idle`, `watching`, `muted`, `disabled` or `stopped`, with
attributes `channel`, `badge_score`, `mutes_today` and `dry_run`. It is recreated when the
add-on starts (it is not stored by Home Assistant across restarts).

## Dashboard card

The TV tile with a small on/off button for the add-on on the same row. Needs
[layout-card](https://github.com/thomasloven/lovelace-layout-card) and
[Mushroom](https://github.com/piitaya/lovelace-mushroom), and an `input_boolean` set as
`enable_entity` (here `input_boolean.tvadblocker`). The button is green while watching, red
while muting an ad and grey when switched off; tap toggles it, hold opens it.

```yaml
type: conditional
conditions:
  - entity: media_player.tv
    state: 'on'
card:
  type: custom:layout-card
  layout_type: custom:grid-layout
  layout:
    grid-template-columns: 1fr 64px
    grid-gap: 8px
    margin: 0
    padding: 0
  cards:
    - type: tile
      entity: media_player.tv
      vertical: false
      features:
        - type: media-player-volume-buttons
      features_position: inline
    - type: custom:mushroom-template-card
      entity: input_boolean.tvadblocker
      icon: >-
        {{ 'mdi:advertisements-off' if is_state('input_boolean.tvadblocker', 'on')
           else 'mdi:advertisements' }}
      icon_color: >-
        {% if is_state('input_boolean.tvadblocker', 'off') %}grey
        {% elif is_state('sensor.tv_hyper_muter', 'muted') %}red
        {% else %}green{% endif %}
      layout: vertical
      fill_container: true
      tap_action:
        action: toggle
      hold_action:
        action: more-info
```

## Logs

`/share/tv_hyper_muter/<date>/`: `events.jsonl` (every decision), `scores.csv` (time, channel,
badge score, muted, motion, band per frame) and the saved frames. The add-on log shows the
same events.

## Adding a channel

Watch the channel for a minute while it shows the badge, take a few frames from Hyperion
and find the badge centre on the 320×180 image (top-left is 0,0). Add an entry to
`channels` with a `match` regex for the channel title as Home Assistant reports it. Check an
ad break too: the badge must disappear, and if ads score above 0.3 give the channel its own
`absent_below`.
