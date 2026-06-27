# Radar_py — ADS-B Flight Tracker

Real-time ADS-B flight tracker using a **Nooelec NESDR SMArt v5** RTL-SDR dongle, with a graphical display designed for a 7" 1024×600 screen. Runs on Linux desktop (development/simulation) and Raspberry Pi (deployment).

## What it does

- Decodes ADS-B signals from nearby aircraft via RTL-SDR dongle + `readsb`
- Shows a live graphical display with the closest commercial flight in detail and a full aircraft list
- Fetches route data, airline info, aircraft type and logos asynchronously from public APIs
- Estimates time and closest distance to your reference point for the main aircraft
- Raspberry Pi features: CPU fan control, PIR motion sensor, active hours scheduling, audio beep on motion
- Info screen mode (activated by PIR): date/time, 3-day weather forecast, scrolling news ticker

## Branches

| Branch | Theme | Hardware | Info Screen |
|--------|-------|----------|-------------|
| `main` | Dark | — | — |
| `sfondo-chiaro` | Light azure | fan + PIR + audio | yes |
| `raspberry` | Dark | fan + PIR + audio | — |
| `info-screen` | Dark | fan + PIR + audio | yes |

**`main`** — Core radar display, dark theme, no hardware integration. Development reference branch.

**`sfondo-chiaro`** — Light azure theme. Same hardware and info-screen features as `info-screen`.

**`raspberry`** — Dark theme with full hardware integration (fan, PIR, audio, active hours). No info screen — PIR activity only triggers the audio beep.

**`info-screen`** — Dark theme with hardware integration. When the PIR detects motion, the display switches to a full-screen info panel (date/time, weather, news). When motion stops, it returns to the radar.

## Hardware

- RTL-SDR dongle: Nooelec NESDR SMArt v5 (or any RTL-SDR compatible device)
- Display: 7" screen at 1024×600 (HDMI or DSI on RPi)
- *(raspberry / sfondo-chiaro / info-screen)* Raspberry Pi 4 recommended
- *(raspberry / sfondo-chiaro / info-screen)* PIR motion sensor on GPIO pin (configurable)
- *(raspberry / sfondo-chiaro / info-screen)* Fan on GPIO pin (configurable)
- *(raspberry / sfondo-chiaro / info-screen)* Speaker on audio jack for beep alerts

## Software requirements

- Linux / Raspberry Pi OS with `readsb` running as a systemd service
- Python 3.10+

```bash
python3 -m venv venv
source venv/bin/activate
pip install pygame requests
```

On Raspberry Pi, also install `RPi.GPIO`:
```bash
pip install RPi.GPIO
```

## Setup

1. Install and enable `readsb`:
   ```bash
   sudo apt install readsb
   sudo systemctl enable --now readsb
   ```

2. Blacklist conflicting kernel modules — create `/etc/modprobe.d/blacklist-rtl.conf`:
   ```
   blacklist dvb_usb_rtl28xxu
   blacklist rtl2832
   blacklist rtl2830
   ```
   Then reboot.

3. Copy and edit the configuration file:
   ```bash
   cp config.example.json config.json
   # edit config.json with your coordinates and preferences
   ```

## Configuration — `config.json`

`config.json` is git-ignored to protect your location data. Copy from `config.example.json` to get started.

```json
{
    "Punto_di_riferimento": "Casa",
    "Punto_rif_lat": 45.0000,
    "Punto_rif_lon": 7.0000,
    "distanza_rilevamento": 100,
    "distanza_max_princ": 50,
    "temperatura_max_rpi": 60,
    "ora_inizio": "07:00",
    "ora_fine": "23:00",
    "pir_timeout_min": 5,
    "gpio_fan": 18,
    "gpio_pir": 17,
    "news_rss_url": "https://www.ansa.it/sito/notizie/cronaca/cronaca_rss.xml"
}
```

| Parameter | Branches | Description |
|-----------|----------|-------------|
| `Punto_di_riferimento` | all | Label for your reference point (shown on display) |
| `Punto_rif_lat` / `Punto_rif_lon` | all | Coordinates of your reference point |
| `distanza_rilevamento` | all | Radius in km for the aircraft list (strips 7+8) |
| `distanza_max_princ` | all | Radius in km for the main detail panel — aircraft beyond this or without route data are skipped |
| `temperatura_max_rpi` | raspberry / sfondo-chiaro / info-screen | CPU temperature threshold in °C above which the fan GPIO is activated |
| `ora_inizio` / `ora_fine` | raspberry / sfondo-chiaro / info-screen | Active hours — display shows standby screen outside this range |
| `pir_timeout_min` | raspberry / sfondo-chiaro / info-screen | Minutes without PIR motion before the screen blanks |
| `gpio_fan` | raspberry / sfondo-chiaro / info-screen | BCM pin number for the fan output |
| `gpio_pir` | raspberry / sfondo-chiaro / info-screen | BCM pin number for the PIR sensor input |
| `news_rss_url` | sfondo-chiaro / info-screen | RSS feed URL for the news ticker on the info screen |

## Running

```bash
source venv/bin/activate

# Graphical display (pygame, 1024×600)
python3 display.py

# Terminal table (no GUI required)
python3 main.py
```

Press `Q` or `Esc` to close the graphical display.

## Display layout — radar mode

The 1024×600 screen is divided into 8 strips of 75px each:

| Strip | Content |
|-------|---------|
| 1 | Header: title, time, reference point name + coords, aircraft count, blinking watchdog dot |
| 2+3 | Main panel (3 columns): airline logo · IATA flight number · airline name + aircraft model |
| 4 | Left half: departure and arrival airports (IATA code, full name, city) · Right half: estimated time and distance to fly over your reference point |
| 5 | Flight data: altitude (ft), ground speed (kt), heading, vertical speed (ft/min, color-coded), distance (km) |
| 6 | Horizontal progress bar: geographic % completion, departure and arrival codes |
| 7+8 | Table of all detected aircraft within range — callsign color: green < 30 km, yellow < 80 km, white otherwise |
| *(overlay)* | Debug bar at the very bottom *(raspberry / sfondo-chiaro / info-screen)*: CPU temp, fan, PIR, active hours, screen state |

### Main panel logic

The main panel shows the **closest aircraft that has route data available**. Aircraft without a known route (private, military, or unregistered flights) are skipped. While route data is being fetched, `...` is shown.

### Closest approach estimate

For the aircraft shown in the main panel, the display calculates the **estimated time until it flies closest to your reference point**, based on current position, track, and ground speed. Also shows the minimum pass distance in km. If the aircraft is flying away, `—` is shown.

## Display layout — info screen mode

*(sfondo-chiaro / info-screen branches only)*

When PIR motion is detected during active hours, the display switches to a full-screen info panel divided into three zones:

| Zone | Y range | Content |
|------|---------|---------|
| Date/time | 0–190 | Current time (88px, centered) · date in gray below (weekday, day, month, year) |
| Weather | 190–460 | 3-day forecast from Open-Meteo with geometric icons |
| News ticker | 460–600 | Scrolling headlines separated by `»»` in cyan |

### Weather layout

| Column | X range | Content |
|--------|---------|---------|
| Oggi (today) | 0–512 | Icon · temperature in cyan (80px) · Italian description · wind + humidity details |
| Domani | 512–768 | Icon · max/min temperature |
| Dopodomani | 768–1024 | Icon · max/min temperature |

Weather data is fetched from [Open-Meteo](https://open-meteo.com) (no API key required) using the coordinates from `Punto_rif_lat`/`Punto_rif_lon`. Refreshed every 15 minutes.

### News ticker

Headlines are fetched from the RSS feed configured in `news_rss_url` (default: ANSA Cronaca). Up to 20 headlines scroll continuously from right to left, separated by cyan `»»` markers. Refreshed every 5 minutes.

## Data sources

| Source | Data |
|--------|------|
| [adsbdb.com](https://www.adsbdb.com) | Flight routes (origin/destination/airline) by callsign; aircraft type by ICAO hex |
| [pics.avs.io](https://pics.avs.io) | Airline logos by IATA code (downloaded once, cached in `logos/`) |
| [OurAirports](https://ourairports.com) | Airport database — `airports.csv` downloaded on first run, ~85k airports |
| [Open-Meteo](https://open-meteo.com) | 3-day weather forecast by coordinates, no API key required *(sfondo-chiaro / info-screen)* |
| ANSA RSS | Scrolling news headlines *(sfondo-chiaro / info-screen)* |

Route and aircraft type data are fetched asynchronously in background threads and cached for 30 minutes. The display never blocks waiting for API responses.

## Hardware abstraction

*(raspberry / sfondo-chiaro / info-screen branches)*

`hardware.py` provides a platform-independent interface so the same code runs on both PC (development) and Raspberry Pi (deployment):

| Function | On PC | On Raspberry Pi |
|----------|-------|-----------------|
| `get_cpu_temp()` | reads `/sys/class/thermal/thermal_zone0/temp` | same |
| `set_fan(on)` | no-op | GPIO BCM pin `gpio_fan` |
| `get_pir()` | always returns `True` (simulated motion) | GPIO BCM pin `gpio_pir` |
| `play_beep()` | pygame.mixer sine wave on audio output | same (audio jack) |
| `set_display_power(on)` | no-op | `vcgencmd display_power 0/1` |

On PC, `get_pir()` always returns `True` so the info screen is visible during development without needing physical hardware.

## File structure

```
Radar_py/
├── display.py          # Graphical entry point (pygame 1024×600)
├── main.py             # Terminal table
├── routes.py           # Async route / airline / aircraft type cache
├── airports.py         # OurAirports CSV database loader
├── hardware.py         # Hardware abstraction (fan, PIR, audio) — raspberry / sfondo-chiaro / info-screen
├── info_screen.py      # Info screen: date/time, weather, news ticker — sfondo-chiaro / info-screen
├── config.example.json # Configuration template (copy to config.json)
├── config.json         # Your configuration — git-ignored
└── logos/              # Cached airline logo PNGs — git-ignored
```
