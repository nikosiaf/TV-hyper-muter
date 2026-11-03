<img src="tv_hyper_muter/logo.png" alt="TV hyper muter" width="400">

# TV hyper muter – Home Assistant add-on

Mutes an LG webOS TV during ad breaks on Live TV, and unmutes when the programme returns.

Greek channels show a small round age-rating badge (K, 8, 12, 16, 18) during programmes
and drop it during ads, while the channel logo stays. The add-on reads the TV picture from
Hyperion.NG (PicCap on a rooted webOS TV), looks for that badge in the channel's corner,
and mutes the TV through Home Assistant when the badge has been missing for about 25 s.
Nothing is installed or changed on the TV.

## Requirements

- LG webOS TV with Hyperion.NG + PicCap running (webOS Brew, rooted TV); Hyperion's
  websocket API (port 8090) reachable from Home Assistant without a login.
- The TV in Home Assistant through the LG webOS integration (`media_player.*`).

## Install

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnikosiaf%2FTV-hyper-muter)

Or: Home Assistant → Settings → Add-ons → Add-on store → ⋮ → Repositories → add
`https://github.com/nikosiaf/TV-hyper-muter`, then install **TV hyper muter**.

Before starting it, set `hyperion_host` to your TV's address and `tv_entity` to your TV's
media player. The channel list is calibrated for Greek free-to-air channels; see
[DOCS](tv_hyper_muter/DOCS.md#adding-a-channel) to add others. Try new channels with
`dry_run` on first.

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

See [DOCS](tv_hyper_muter/DOCS.md) for options, logs and tuning.

## License

MIT, see [LICENSE](LICENSE).
