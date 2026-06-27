#!/usr/bin/env python3
"""ADS-B aircraft tracker — reads live data from readsb JSON output."""

import json
import math
import time
import os
from datetime import datetime

import airports
import routes

AIRCRAFT_JSON = "/run/readsb/aircraft.json"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
REFRESH_SECONDS = 3
AIRPORT_COL = 18  # chars per airport column: "LHR London          "


def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return json.load(f)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def flight_pct(ac: dict) -> str:
    callsign = (ac.get("flight") or "").strip()
    lat = ac.get("lat")
    if not callsign or lat is None:
        return "   ?"

    orig, dest = routes.get_route(callsign)
    if orig["iata"] == "...":
        return " ..."
    if orig["iata"] == "?" or dest["iata"] == "?":
        return "   ?"

    # Use coordinates from adsbdb directly; fall back to airports.csv if missing
    olat, olon = orig["lat"], orig["lon"]
    dlat, dlon = dest["lat"], dest["lon"]
    if olat is None:
        c = airports.get_coords_iata(orig["iata"])
        if c:
            olat, olon = c
    if dlat is None:
        c = airports.get_coords_iata(dest["iata"])
        if c:
            dlat, dlon = c
    if None in (olat, olon, dlat, dlon):
        return "   ?"

    total = haversine_km(olat, olon, dlat, dlon)
    if total < 10:
        return "   ?"

    flown = haversine_km(olat, olon, lat, ac["lon"])
    pct = min(flown / total * 100, 100)
    return f"{pct:3.0f}%"


def fmt_alt(aircraft: dict) -> str:
    alt = aircraft.get("alt_baro") or aircraft.get("alt_geom")
    if alt is None:
        return "    ?"
    if alt == "ground":
        return "   GND"
    return f"{alt:6d}"


def fmt_speed(aircraft: dict) -> str:
    gs = aircraft.get("gs")
    return f"{gs:5.0f}" if gs is not None else "    ?"


def fmt_pos(aircraft: dict) -> str:
    lat = aircraft.get("lat")
    lon = aircraft.get("lon")
    if lat is None or lon is None:
        return "        ?"
    return f"{lat:8.4f} {lon:9.4f}"


def fmt_dist(aircraft: dict, ref_lat: float, ref_lon: float) -> str:
    lat = aircraft.get("lat")
    lon = aircraft.get("lon")
    if lat is None or lon is None:
        return "    ?"
    return f"{haversine_km(ref_lat, ref_lon, lat, lon):5.1f}"


def fmt_airport(ap: dict) -> str:
    """Format airport dict as 'LHR London' padded to AIRPORT_COL chars."""
    iata = ap["iata"]
    if iata in ("?", "..."):
        return f"{iata:<{AIRPORT_COL}}"
    city = ap.get("municipality") or ap.get("name", "")
    label = f"{iata} {city}"
    return f"{label[:AIRPORT_COL]:<{AIRPORT_COL}}"


def load_aircraft() -> list[dict]:
    with open(AIRCRAFT_JSON) as f:
        data = json.load(f)
    return data.get("aircraft", [])


def print_table(aircraft_list: list[dict], config: dict) -> None:
    os.system("clear")
    now = datetime.now().strftime("%H:%M:%S")
    total = len(aircraft_list)
    with_pos = sum(1 for a in aircraft_list if a.get("lat") is not None)
    ref_name = config.get("Punto_di_riferimento", "Riferimento")
    ref_lat = config["Punto_rif_lat"]
    ref_lon = config["Punto_rif_lon"]
    max_dist = config.get("distanza_rilevamento")  # km, None = nessun limite

    print(f"  ADS-B Radar — {now}   {total} aerei ({with_pos} con posizione)")
    dist_label = f"  |  Raggio: {max_dist} km" if max_dist else ""
    print(f"  Punto di riferimento: {ref_name}  ({ref_lat:.4f}, {ref_lon:.4f}){dist_label}")
    print()
    c = AIRPORT_COL
    print(
        f"  {'CALLSIGN':<10} {'ICAO':<7} {'PARTENZA':<{c}} {'ARRIVO':<{c}} {'%':>4}"
        f"  {'ALT ft':>6}  {'GS kt':>5}"
        f"  {'LAT':>8}  {'LON':>9}  {'DIST km':>7}  {'RSSI':>6}"
    )
    sep_len = 10 + 1 + 7 + 1 + c + 1 + c + 1 + 4 + 2 + 6 + 3 + 5 + 3 + 8 + 2 + 9 + 2 + 7 + 2 + 6
    print("  " + "─" * sep_len)

    def dist_from_ref(a: dict) -> float:
        if a.get("lat") is None:
            return 9999.0
        return haversine_km(ref_lat, ref_lon, a["lat"], a["lon"])

    if max_dist is not None:
        aircraft_list = [a for a in aircraft_list if dist_from_ref(a) <= max_dist]

    sorted_ac = sorted(aircraft_list, key=lambda a: (a.get("lat") is None, dist_from_ref(a)))

    for ac in sorted_ac:
        flight = (ac.get("flight") or "").strip() or "—"
        icao = ac.get("hex", "?").upper()
        callsign = flight if flight != "—" else ""
        orig, dest = routes.get_route(callsign) if callsign else (routes._MISSING, routes._MISSING)
        pct = flight_pct(ac)
        alt = fmt_alt(ac)
        speed = fmt_speed(ac)
        pos = fmt_pos(ac)
        dist = fmt_dist(ac, ref_lat, ref_lon)
        rssi = ac.get("rssi")
        rssi_str = f"{rssi:5.1f}" if rssi is not None else "    ?"

        print(
            f"  {flight:<10} {icao:<7} {fmt_airport(orig)} {fmt_airport(dest)} {pct:>4}"
            f"  {alt} ft  {speed} kt"
            f"  {pos}  {dist} km  {rssi_str} dB"
        )

    print()
    print(f"  Aggiornamento ogni {REFRESH_SECONDS}s  |  Rotte: adsbdb.com  |  Ctrl+C per uscire")


def main() -> None:
    try:
        config = load_config()
    except FileNotFoundError:
        print(f"File di configurazione non trovato: {CONFIG_FILE}")
        return
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Errore nel file di configurazione: {e}")
        return

    print("Caricamento database aeroporti...", flush=True)
    airports.get_coords_iata("FCO")  # pre-warm per il fallback coordinate

    while True:
        try:
            aircraft_list = load_aircraft()
            print_table(aircraft_list, config)
        except FileNotFoundError:
            print(f"File non trovato: {AIRCRAFT_JSON}")
            print("Assicurati che readsb sia in esecuzione: systemctl status readsb")
        except json.JSONDecodeError as e:
            print(f"Errore JSON: {e}")
        except KeyboardInterrupt:
            print("\nUscita.")
            break
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
