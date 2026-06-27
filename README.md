# Radar_py — ADS-B Flight Tracker

Real-time ADS-B flight tracker using a **Nooelec NESDR SMArt v5** RTL-SDR dongle, with a graphical display designed for a 7" 1024×600 screen. Runs on Linux desktop (development/simulation) and Raspberry Pi (deployment).

## What it does

- Decodes ADS-B signals from nearby aircraft via RTL-SDR dongle + `readsb`
- Shows a live graphical display with the closest commercial flight in detail and a full aircraft list
- Fetches route data, airline info, aircraft type and logos asynchronously from public APIs
- Estimates time and closest distance to your reference point for the main aircraft
- Raspberry Pi features: CPU fan control, PIR motion sensor, active hours scheduling, audio beep on motion

## Branches

| Branch | Description |
|--------|-------------|
| `main` | Dark theme — core display only |
| `sfondo-chiaro` | Light azure theme — same features as `raspberry` |
| `raspberry` | Dark theme + hardware integration (fan, PIR, audio, active hours) |

## Hardware

- RTL-SDR dongle: Nooelec NESDR SMArt v5 (or any RTL-SDR compatible device)
- Display: 7" screen at 1024×600 (HDMI or DSI on RPi)
- *(raspberry branch)* Raspberry Pi 4 recommended
- *(raspberry branch)* PIR motion sensor on GPIO pin (configurable)
- *(raspberry branch)* Fan on GPIO pin (configurable)
- *(raspberry branch)* Speaker on audio jack for beep alerts

## Software requirements

- Linux / Raspberry Pi OS with `readsb` running as a systemd service
- Python 3.10+

```bash
python3 -m venv venv
source venv/bin/activate
pip install pygame requests
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
    "gpio_pir": 17
}
```

| Parameter | Description |
|-----------|-------------|
| `Punto_di_riferimento` | Label for your reference point (shown on display) |
| `Punto_rif_lat` / `Punto_rif_lon` | Coordinates of your reference point |
| `distanza_rilevamento` | Radius in km for the aircraft list (strips 7+8) |
| `distanza_max_princ` | Radius in km for the main detail panel — aircraft beyond this or without route data are skipped |
| `temperatura_max_rpi` | CPU temperature threshold in °C above which the fan GPIO is activated *(raspberry branch)* |
| `ora_inizio` / `ora_fine` | Active hours — display shows standby screen outside this range *(raspberry branch)* |
| `pir_timeout_min` | Minutes without PIR motion before the screen blanks *(raspberry branch)* |
| `gpio_fan` | BCM pin number for the fan output *(raspberry branch)* |
| `gpio_pir` | BCM pin number for the PIR sensor input *(raspberry branch)* |

## Running

```bash
source venv/bin/activate

# Graphical display (pygame, 1024×600)
python3 display.py

# Terminal table (no GUI required)
python3 main.py
```

Press `Q` or `Esc` to close the graphical display.

## Display layout

The 1024×600 screen is divided into 8 strips of 75px each:

| Strip | Content |
|-------|---------|
| 1 | Header: title, time, reference point name + coords, aircraft count, blinking watchdog dot |
| 2+3 | Main panel (3 columns): airline logo · IATA flight number · airline name + aircraft model |
| 4 | Left half: departure and arrival airports (IATA code, full name, city) · Right half: estimated time and distance to fly over your reference point |
| 5 | Flight data: altitude (ft), ground speed (kt), heading, vertical speed (ft/min, color-coded), distance (km) |
| 6 | Horizontal progress bar: geographic % completion, departure and arrival codes |
| 7+8 | Table of all detected aircraft within range — callsign color: green < 30 km, yellow < 80 km, white otherwise |
| *(overlay)* | Debug bar at the very bottom *(raspberry branch)*: CPU temp, fan, PIR, active hours, screen state |

### Main panel logic

The main panel shows the **closest aircraft that has route data available**. Aircraft without a known route (private, military, or unregistered flights) are skipped. While route data is being fetched, `...` is shown.

### Closest approach estimate

For the aircraft shown in the main panel, the display calculates the **estimated time until it flies closest to your reference point**, based on current position, track, and ground speed. Also shows the minimum pass distance in km. If the aircraft is flying away, `—` is shown.

## Data sources

| Source | Data |
|--------|------|
| [adsbdb.com](https://www.adsbdb.com) | Flight routes (origin/destination/airline) by callsign; aircraft type by ICAO hex |
| [pics.avs.io](https://pics.avs.io) | Airline logos by IATA code (downloaded once, cached in `logos/`) |
| [OurAirports](https://ourairports.com) | Airport database — `airports.csv` downloaded on first run, ~85k airports |

Route and aircraft type data are fetched asynchronously in background threads and cached for 30 minutes. The display never blocks waiting for API responses.

## Hardware abstraction (raspberry branch)

`hardware.py` provides a platform-independent interface:

| Function | On PC | On Raspberry Pi |
|----------|-------|-----------------|
| `get_cpu_temp()` | reads `/sys/class/thermal/thermal_zone0/temp` | same |
| `set_fan(on)` | no-op | GPIO BCM pin `gpio_fan` |
| `get_pir()` | always returns `True` (simulated) | GPIO BCM pin `gpio_pir` |
| `play_beep()` | pygame.mixer sine wave on audio output | same (audio jack) |
| `set_display_power(on)` | no-op | `vcgencmd display_power 0/1` |

On Raspberry Pi, install `RPi.GPIO`:
```bash
pip install RPi.GPIO
```

## File structure

```
Radar_py/
├── display.py          # Graphical entry point (pygame 1024×600)
├── main.py             # Terminal table
├── routes.py           # Async route / airline / aircraft type cache
├── airports.py         # OurAirports CSV database loader
├── hardware.py         # Hardware abstraction (fan, PIR, audio) — raspberry branch
├── config.example.json # Configuration template (copy to config.json)
├── config.json         # Your configuration — git-ignored
└── logos/              # Cached airline logo PNGs — git-ignored
```
