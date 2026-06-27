# Radar_py — ADS-B Flight Tracker

Real-time ADS-B flight tracker using a **Nooelec NESDR SMArt v5** RTL-SDR dongle, with a graphical display designed for a 7" 1024×600 screen.

## What it does

Decodes ADS-B signals from nearby aircraft and shows:
- Live aircraft list with callsign, origin, destination, altitude, speed, and distance
- Detailed panel for the closest commercial flight: airline logo, flight number, aircraft model, airport names, progress bar, flight data

## Hardware

- RTL-SDR dongle: Nooelec NESDR SMArt v5 (or any RTL-SDR compatible device)
- Recommended display: 7" screen at 1024×600

## Software requirements

- Linux with `readsb` running as a systemd service (reads ADS-B from the dongle, exposes `/run/readsb/aircraft.json`)
- Python 3.10+
- Dependencies: `pygame`, `requests`

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

2. Blacklist conflicting kernel modules (`/etc/modprobe.d/blacklist-rtl.conf`):
   ```
   blacklist dvb_usb_rtl28xxu
   blacklist rtl2832
   blacklist rtl2830
   ```

3. Edit `config.json` with your reference point coordinates and detection radii.

## Configuration — `config.json`

```json
{
    "Punto_di_riferimento": "Casa",
    "Punto_rif_lat": 45.17,
    "Punto_rif_lon": 7.36,
    "distanza_rilevamento": 70,
    "distanza_max_princ": 40
}
```

| Parameter | Description |
|-----------|-------------|
| `Punto_di_riferimento` | Label for your reference point |
| `Punto_rif_lat` / `Punto_rif_lon` | Coordinates of your reference point |
| `distanza_rilevamento` | Radius in km for the aircraft list (bottom panel) |
| `distanza_max_princ` | Radius in km for the main detail panel — aircraft beyond this or without route data are skipped |

## Running

```bash
source venv/bin/activate

# Graphical display (pygame, 1024×600)
python3 display.py

# Terminal table
python3 main.py
```

Press `Q` or `Esc` to close the graphical display.

## Display layout

The 1024×600 screen is divided into 8 strips of 75px each:

| Strip | Content |
|-------|---------|
| 1 | Header: title, time, reference point, aircraft count, blinking watchdog dot |
| 2+3 | Main panel: airline logo, flight number, airline name, aircraft model |
| 4 | Departure and arrival airports with full name and city |
| 5 | Flight data: altitude, ground speed, heading, vertical speed, distance |
| 6 | Horizontal progress bar with departure/arrival codes and completion % |
| 7+8 | Table of all detected aircraft within range |

## Data sources

| Source | Data |
|--------|------|
| [adsbdb.com](https://www.adsbdb.com) | Flight routes (origin/destination) and aircraft type by ICAO hex |
| [pics.avs.io](https://pics.avs.io) | Airline logos by IATA code |
| [OurAirports](https://ourairports.com) | Airport database (`airports.csv`, downloaded on first run) |

## File structure

```
Radar_py/
├── display.py      # Graphical entry point (pygame)
├── main.py         # Terminal table
├── routes.py       # Async route/airline/aircraft cache
├── airports.py     # OurAirports CSV database
├── config.json     # User configuration
└── logos/          # Cached airline logo PNGs (auto-downloaded, git-ignored)
```
