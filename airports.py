"""Airport database from OurAirports — downloaded once, cached locally."""

import csv
import os
import requests

AIRPORTS_CSV = os.path.join(os.path.dirname(__file__), "airports.csv")

# ICAO (ident) -> (lat, lon, city)
_by_icao: dict[str, tuple[float, float, str]] = {}
# IATA (iata_code) -> (lat, lon, city)
_by_iata: dict[str, tuple[float, float, str]] = {}


def _download() -> None:
    print("Download database aeroporti (OurAirports)...", flush=True)
    r = requests.get(
        "https://ourairports.com/data/airports.csv",
        timeout=30,
        headers={"User-Agent": "radar_py/1.0"},
    )
    r.raise_for_status()
    with open(AIRPORTS_CSV, "w", encoding="utf-8") as f:
        f.write(r.text)


def _load() -> None:
    if not os.path.exists(AIRPORTS_CSV):
        _download()
    with open(AIRPORTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["latitude_deg"])
                lon = float(row["longitude_deg"])
                city = row.get("municipality") or row.get("name", "")
            except (ValueError, KeyError):
                continue

            icao = row.get("ident", "").strip().upper()
            if icao:
                _by_icao[icao] = (lat, lon, city)

            iata = row.get("iata_code", "").strip().upper()
            if iata:
                _by_iata[iata] = (lat, lon, city)


def _ensure_loaded() -> None:
    if not _by_iata:
        _load()


def get_coords_iata(iata: str) -> tuple[float, float] | None:
    _ensure_loaded()
    entry = _by_iata.get(iata.upper())
    return (entry[0], entry[1]) if entry else None


def get_coords_icao(icao: str) -> tuple[float, float] | None:
    _ensure_loaded()
    entry = _by_icao.get(icao.upper())
    return (entry[0], entry[1]) if entry else None


def get_city_iata(iata: str) -> str:
    _ensure_loaded()
    entry = _by_iata.get(iata.upper())
    return entry[2] if entry else iata
