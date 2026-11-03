# TV Ad Mute – Home Assistant add-on

Mutes an LG webOS TV during ad breaks on Live TV, and unmutes when the programme returns.

Greek channels show a small round age-rating badge (K, 8, 12, 16, 18) during programmes
and drop it during ads, while the channel logo stays. The add-on reads the TV picture from
Hyperion.NG (PicCap on a rooted webOS TV), looks for that badge in the channel's corner,
and mutes the TV through Home Assistant when the badge has been missing for a minute.
Nothing is installed or changed on the TV.

## Requirements

- LG webOS TV with Hyperion.NG + PicCap running (webOS Brew, rooted TV); Hyperion's
  websocket API (port 8090) reachable from Home Assistant without a login.
- The TV in Home Assistant through the LG webOS integration (`media_player.*`).

## Install

Home Assistant → Settings → Add-ons → Add-on store → ⋮ → Repositories → add this
repository's URL, then install **TV Ad Mute**. For a private repository, use
`https://<user>:<token>@github.com/<user>/TV-hyper-muter` with a read-only token.

See [DOCS](tv_admute/DOCS.md) for options, logs and tuning.
