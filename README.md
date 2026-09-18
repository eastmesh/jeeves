# The mess we call Jeeves


Connects to a MeshCore companion radio, listens for commands on configured channels, resolves hex path prefixes to repeater names using a persistent database, and replies on the channel. Includes a full web dashboard for live monitoring, repeater management, path visualization, and configuration.

### Commands

| Command | Description |
|---|---|
| `trace` | Resolves the hop path to repeater names |
| `ping` | Acknowledges receipt with path and hop count |
| `paths` | Lists unique paths seen from the sender |
| `multipath` | Shows all distinct paths for the sender's most recent message |
| `prefix <hex>` | Looks up repeater names for given hex prefixes (e.g. `prefix fb:1f:7a`) |
| `weather [postcode]` | Current conditions for home location or a given postcode |
| `forecast [postcode]` | 3-day forecast for home location or a given postcode |
| `help` | Lists enabled commands on the current channel |

### Features

- **Path resolution** — resolves 1-byte and multibyte (2-byte hash) hex path prefixes to repeater names with geographic disambiguation
- **Per-channel command control** — each channel independently enables commands; `weather` and `forecast` are off by default
- **Rate limiting** — optional per-user per-channel cooldown to prevent command spam
- **Web dashboard** (port 8075) — live message feed, path visualizer, repeater management, overlap analysis, statistics, and full settings UI
- **Guest dashboard** (port 8076, optional) — read-only view of ping history, paths, and repeater info
- **Weather & forecasts** — `weather` and `forecast` commands via Open-Meteo, with optional postcode lookup
- **Daily forecast broadcast** — scheduled 3-day forecast sent to configured channels at a set hour (configurable IANA timezone)
- **Radio management** — read and update radio name, frequency, TX power, and channel keys directly from the web UI
- **Systemd & Docker** — production-ready deployment with auto-restart

## Quick Start

```bash
pip install -e .
meshcore-pathbot --serial /dev/ttyUSB0 --config config.toml
```

Then open http://localhost:8075 for the web dashboard.

## Usage

```
meshcore-pathbot [OPTIONS]

Connection (pick one):
  -s, --serial PORT     Serial port (e.g. /dev/ttyUSB0, COM3)
  -t, --tcp HOST        TCP host (e.g. 192.168.1.100)
  -b, --ble [ADDR]      BLE address (or empty to scan)

Options:
  -C, --config FILE     TOML config file
  -p, --port PORT       TCP port (default: 5000)
  -B, --baud RATE       Serial baud rate
  -c, --channel N       Channel to listen on (default: 2, used when no [[bot.channels]] defined)
  -r, --repeaters-file FILE  Repeaters DB path (.db preferred; .json auto-migrates)
  -i, --ignore NAME     Additional node names to ignore
  -d, --debug           Enable debug logging
  --web-host HOST       Web dashboard bind host
  --web-port PORT       Web dashboard port (default: 8075)
  --no-web              Disable web dashboard
```

## Configuration

Copy `config.example.toml` to `config.toml` and edit to your setup. CLI arguments override config file values.

Key settings:
- **`[[bot.channels]]`** — define one or more channels with their enabled commands and rate limit settings; if omitted, falls back to `bot.channel`
- **`bot.timezone`** — IANA timezone for daily forecast scheduling (e.g. `"Australia/Melbourne"`); defaults to system local time
- **`guest_web.ping_channels`** — restrict the guest dashboard to specific channels (empty = all ping-enabled channels)

## Docker

```bash
docker compose up -d
```

Mount your serial device by uncommenting the `devices` section in `docker-compose.yml`.

## Systemd

```bash
sudo cp meshcore-pathbot.service /etc/systemd/system/
sudo systemctl enable --now meshcore-pathbot
```

## Deployment readiness checklist

- Use a dedicated `config.toml` per environment (do not commit live configs).
- Run behind a trusted network boundary or reverse proxy; admin UI can modify radio settings.
- Set `guest_web.enabled = true` only when you explicitly want read-only public visibility.
- Rotate channel names/keys operationally on radios as part of commissioning.
- Persist `repeaters.db` and your config volume when using Docker.

## Security note

The radio channels table intentionally shows **masked** channel secret values in the UI/API. Full channel secrets are not returned by the dashboard endpoint.
