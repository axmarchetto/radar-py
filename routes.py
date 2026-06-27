"""Route info from adsbdb.com — threaded, cached. Returns full airport and airline objects."""

import time
import threading
import requests

# cache entry: (origin, dest, airline, callsign_iata, fetched_at)
_cache: dict[str, tuple] = {}
_pending: set[str] = set()
_lock = threading.Lock()

CACHE_TTL = 1800
API_TIMEOUT = 6

_MISSING  = {"iata": "?",   "name": "?", "municipality": "?", "lat": None, "lon": None}
_FETCHING = {"iata": "...", "name": "",  "municipality": "",  "lat": None, "lon": None}
_AIRLINE_MISSING  = {"iata": "?",   "icao": "?", "name": "?"}
_AIRLINE_FETCHING = {"iata": "...", "icao": "",  "name": ""}


def _parse_airport(raw: dict) -> dict:
    return {
        "iata": raw.get("iata_code", "?"),
        "name": raw.get("name", ""),
        "municipality": raw.get("municipality", ""),
        "lat": raw.get("latitude"),
        "lon": raw.get("longitude"),
    }


def _parse_airline(raw: dict) -> dict:
    return {
        "iata": raw.get("iata", "?"),
        "icao": raw.get("icao", "?"),
        "name": raw.get("name", "?"),
    }


def _fetch(callsign: str) -> None:
    try:
        r = requests.get(
            f"https://api.adsbdb.com/v0/callsign/{callsign}",
            timeout=API_TIMEOUT,
            headers={"User-Agent": "radar_py/1.0"},
        )
        if r.status_code == 200:
            fr = r.json()["response"]["flightroute"]
            origin          = _parse_airport(fr["origin"])
            dest            = _parse_airport(fr["destination"])
            airline         = _parse_airline(fr.get("airline") or {})
            callsign_iata   = fr.get("callsign_iata") or callsign
        else:
            origin, dest    = _MISSING.copy(), _MISSING.copy()
            airline         = _AIRLINE_MISSING.copy()
            callsign_iata   = callsign
    except Exception:
        origin, dest    = _MISSING.copy(), _MISSING.copy()
        airline         = _AIRLINE_MISSING.copy()
        callsign_iata   = callsign

    with _lock:
        _cache[callsign] = (origin, dest, airline, callsign_iata, time.time())
        _pending.discard(callsign)


def _ensure(callsign: str) -> tuple | None:
    """Return cache entry if fresh, else trigger fetch and return None."""
    with _lock:
        cached = _cache.get(callsign)
        if cached and time.time() - cached[4] < CACHE_TTL:
            return cached
        if callsign not in _pending:
            _pending.add(callsign)
            threading.Thread(target=_fetch, args=(callsign,), daemon=True).start()
    return None


def get_route(callsign: str) -> tuple[dict, dict]:
    if not callsign:
        return _MISSING.copy(), _MISSING.copy()
    cached = _ensure(callsign)
    if cached:
        return cached[0], cached[1]
    return _FETCHING.copy(), _FETCHING.copy()


def get_airline(callsign: str) -> dict:
    if not callsign:
        return _AIRLINE_MISSING.copy()
    cached = _ensure(callsign)
    if cached:
        return cached[2]
    return _AIRLINE_FETCHING.copy()


def get_callsign_iata(callsign: str) -> str:
    """Return IATA-style flight number (e.g. 'AZ770') or original callsign."""
    if not callsign:
        return callsign
    cached = _ensure(callsign)
    if cached:
        return cached[3] or callsign
    return callsign


# ── Aircraft type cache (keyed by ICAO hex24) ─────────────────────────────────

_ac_cache: dict[str, tuple] = {}   # hex24 -> (model_str, fetched_at)
_ac_pending: set[str] = set()
_ac_lock = threading.Lock()


def _fetch_aircraft(hex24: str) -> None:
    try:
        r = requests.get(
            f"https://api.adsbdb.com/v0/aircraft/{hex24}",
            timeout=API_TIMEOUT,
            headers={"User-Agent": "radar_py/1.0"},
        )
        if r.status_code == 200:
            ac = r.json()["response"]["aircraft"]
            manufacturer = ac.get("manufacturer", "")
            icao_type    = ac.get("icao_type", "")
            model = f"{manufacturer} {icao_type}".strip() if (manufacturer or icao_type) else "?"
        else:
            model = "?"
    except Exception:
        model = "?"

    with _ac_lock:
        _ac_cache[hex24] = (model, time.time())
        _ac_pending.discard(hex24)


def get_aircraft_type(hex24: str) -> str:
    """Return 'Airbus A320' style string, '...' while fetching, '?' if unknown."""
    if not hex24:
        return "?"
    hex24 = hex24.lower()
    with _ac_lock:
        cached = _ac_cache.get(hex24)
        if cached and time.time() - cached[1] < CACHE_TTL:
            return cached[0]
        if hex24 in _ac_pending:
            return "..."
        _ac_pending.add(hex24)
    threading.Thread(target=_fetch_aircraft, args=(hex24,), daemon=True).start()
    return "..."
