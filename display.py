#!/usr/bin/env python3
"""Graphical ADS-B display — 800×480, designed for 7-inch screens."""

import json
import math
import os
import sys
import time
import threading
from datetime import datetime

import pygame
import requests

import airports
import routes
from main import load_config, load_aircraft, haversine_km

# ── Colors ────────────────────────────────────────────────────────────────────
BLACK  = (  0,   0,   0)
WHITE  = (255, 255, 255)
GRAY   = ( 90,  90,  90)
LGRAY  = (160, 160, 160)
GREEN  = (  0, 200,  80)
YELLOW = (240, 200,   0)
CYAN   = (  0, 200, 220)
RED    = (220,  50,  50)

# ── Layout ────────────────────────────────────────────────────────────────────
W, H       = 1024, 600
N_STRIPS   = 8
STRIP_H    = H // N_STRIPS   # 75 px each
DIVIDER_W  = 2
MARGIN_X   = 14
REFRESH_MS = 3000

CLOSEST_STRIP_START = 1   # strips 2+3 (0-indexed 1+2), y=75..224
CLOSEST_PANEL_H     = 2 * STRIP_H   # 150 px

AC_STRIP_START = 6        # strips 7+8 (0-indexed 6+7), y=450..599
AC_PANEL_H     = 2 * STRIP_H   # 150 px

# Aircraft list column x positions (scaled for 1024 px width)
COL_CS   =  14
COL_DEP  = 140
COL_ARR  = 368
COL_PCT  = 596
COL_ALT  = 660
COL_GS   = 800
COL_DIST = 912

# ── Airline logo cache ────────────────────────────────────────────────────────
LOGOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos")

_logo_surfaces: dict[str, pygame.Surface | None] = {}  # iata -> Surface or None
_logo_pending: set[str] = set()
_logo_lock = threading.Lock()


def _download_logo(iata: str) -> None:
    os.makedirs(LOGOS_DIR, exist_ok=True)
    path = os.path.join(LOGOS_DIR, f"{iata}.png")
    if not os.path.exists(path):
        try:
            r = requests.get(
                f"https://pics.avs.io/200/200/{iata}.png",
                timeout=6,
                headers={"User-Agent": "radar_py/1.0"},
            )
            if r.status_code == 200 and len(r.content) > 500:
                with open(path, "wb") as f:
                    f.write(r.content)
        except Exception:
            pass

    surf = None
    if os.path.exists(path):
        try:
            surf = pygame.image.load(path).convert_alpha()
        except Exception:
            pass

    with _logo_lock:
        _logo_surfaces[iata] = surf
        _logo_pending.discard(iata)


def get_logo(iata: str, size: int) -> pygame.Surface | None:
    """Return a Surface scaled to size×size, or None while loading / not found."""
    if not iata or iata in ("?", "..."):
        return None
    with _logo_lock:
        if iata in _logo_surfaces:
            raw = _logo_surfaces[iata]
            if raw is None:
                return None
            return pygame.transform.smoothscale(raw, (size, size))
        if iata not in _logo_pending:
            _logo_pending.add(iata)
            threading.Thread(target=_download_logo, args=(iata,), daemon=True).start()
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_alt(ac: dict) -> str:
    alt = ac.get("alt_baro") or ac.get("alt_geom")
    if alt is None:
        return "—"
    if alt == "ground":
        return "GND"
    return f"{alt:,d}"

def fmt_speed(ac: dict) -> str:
    gs = ac.get("gs")
    return f"{gs:.0f}" if gs is not None else "—"

def fmt_dist(ac: dict, ref_lat: float, ref_lon: float) -> str:
    if ac.get("lat") is None:
        return "—"
    return f"{haversine_km(ref_lat, ref_lon, ac['lat'], ac['lon']):.1f}"

def flight_pct(ac: dict) -> str:
    cs = (ac.get("flight") or "").strip()
    lat = ac.get("lat")
    if not cs or lat is None:
        return "—"
    orig, dest = routes.get_route(cs)
    if orig["iata"] == "...":
        return "…"
    if orig["iata"] == "?" or dest["iata"] == "?":
        return "—"
    olat, olon = orig["lat"], orig["lon"]
    dlat, dlon = dest["lat"], dest["lon"]
    if None in (olat, olon, dlat, dlon):
        c = airports.get_coords_iata(orig["iata"])
        if c: olat, olon = c
        c = airports.get_coords_iata(dest["iata"])
        if c: dlat, dlon = c
    if None in (olat, olon, dlat, dlon):
        return "—"
    total = haversine_km(olat, olon, dlat, dlon)
    if total < 10:
        return "—"
    return f"{min(haversine_km(olat, olon, lat, ac['lon']) / total * 100, 100):.0f}%"

def fmt_airport(ap: dict, max_city: int = 10) -> str:
    iata = ap["iata"]
    if iata in ("?", "..."):
        return iata
    city = (ap.get("municipality") or "").strip()
    return f"{iata} {city[:max_city]}" if city else iata

def dist_from_ref(ac: dict, ref_lat: float, ref_lon: float) -> float:
    if ac.get("lat") is None:
        return 9999.0
    return haversine_km(ref_lat, ref_lon, ac["lat"], ac["lon"])


# ── Font cache ────────────────────────────────────────────────────────────────

_fonts: dict[tuple, pygame.font.Font] = {}

def font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _fonts:
        for name in ("ubuntumono", "dejavusansmono", "liberationmono", "monospace", "courier"):
            try:
                _fonts[key] = pygame.font.SysFont(name, size, bold=bold)
                break
            except Exception:
                continue
        else:
            _fonts[key] = pygame.font.Font(None, size)
    return _fonts[key]

def blit_text(surf: pygame.Surface, text: str, x: int, y: int,
              size: int = 15, color: tuple = WHITE, bold: bool = False,
              align: str = "left") -> None:
    f = font(size, bold)
    rendered = f.render(text, True, color)
    if align == "right":
        x -= rendered.get_width()
    elif align == "center":
        x -= rendered.get_width() // 2
    surf.blit(rendered, (x, y))


# ── Strip drawing ─────────────────────────────────────────────────────────────

def draw_strip_debug_label(surf: pygame.Surface, index: int, label: str) -> None:
    cx = W // 2
    cy = index * STRIP_H + STRIP_H // 2
    blit_text(surf, label, cx, cy - 10, size=18, color=GRAY, align="center")


def draw_strip0_header(surf: pygame.Surface, config: dict,
                       n_total: int, n_visible: int, now_str: str,
                       blink_on: bool = True) -> None:
    mid_y = STRIP_H // 2 - 10
    blit_text(surf, "ADS-B  RADAR", MARGIN_X + 22, mid_y - 2, size=24, bold=True, color=CYAN)
    ref   = config.get("Punto_di_riferimento", "Riferimento")
    rlat  = config["Punto_rif_lat"]
    rlon  = config["Punto_rif_lon"]
    mdist = config.get("distanza_rilevamento")
    raggio = f"  ·  raggio {mdist} km" if mdist else ""
    blit_text(surf, f"{ref}  ({rlat:.4f}, {rlon:.4f}){raggio}",
              MARGIN_X + 22, mid_y + 24, size=14, color=LGRAY)
    blit_text(surf, now_str, W - MARGIN_X, mid_y - 2, size=24, bold=True,
              color=WHITE, align="right")
    blit_text(surf, f"{n_visible} aerei  (tot {n_total})",
              W - MARGIN_X, mid_y + 24, size=14, color=LGRAY, align="right")

    # Watchdog dot
    dot_color = GREEN if blink_on else (20, 80, 20)
    pygame.draw.circle(surf, dot_color, (MARGIN_X + 7, STRIP_H // 2), 7)


def draw_strip23_closest(surf: pygame.Surface, principal: dict | None,
                         config: dict) -> None:
    """Strips 2+3 merged (150 px): 3-column layout — logo | flight number | airline+type."""
    panel_y = CLOSEST_STRIP_START * STRIP_H
    panel_h = CLOSEST_PANEL_H

    if principal is None:
        cy = panel_y + panel_h // 2
        blit_text(surf, "nessun volo con dati disponibili nel raggio principale",
                  W // 2, cy - 10, size=16, color=GRAY, align="center")
        return

    ac  = principal
    cs  = (ac.get("flight") or "").strip()

    airline     = routes.get_airline(cs) if cs else routes._AIRLINE_MISSING
    iata_flight = routes.get_callsign_iata(cs) if cs else cs
    ac_type     = routes.get_aircraft_type(ac.get("hex", ""))

    airline_iata = airline.get("iata", "?")
    airline_name = airline.get("name", "")

    # Column boundaries
    COL1_W = 210   # logo column
    COL2_W = 310   # flight number column
    # COL3 takes the rest

    COL1_CX = COL1_W // 2
    COL2_CX = COL1_W + COL2_W // 2
    COL3_CX = COL1_W + COL2_W + (W - COL1_W - COL2_W) // 2

    mid_y = panel_y + panel_h // 2

    # ── Column 1: Logo ──
    LOGO_SIZE = 140
    logo_x = COL1_CX - LOGO_SIZE // 2
    logo_y = panel_y + (panel_h - LOGO_SIZE) // 2
    logo = get_logo(airline_iata, LOGO_SIZE)
    if logo:
        surf.blit(logo, (logo_x, logo_y))
    elif airline_iata not in ("?", "..."):
        pygame.draw.rect(surf, GRAY, (logo_x, logo_y, LOGO_SIZE, LOGO_SIZE), 1)
        blit_text(surf, airline_iata, COL1_CX, mid_y - 10, size=20, color=GRAY, align="center")

    # Vertical divider after col 1
    pygame.draw.line(surf, GRAY, (COL1_W, panel_y + 10), (COL1_W, panel_y + panel_h - 10), 1)

    # ── Column 2: Flight number ──
    display_cs = iata_flight or cs or "—"
    blit_text(surf, display_cs, COL2_CX, mid_y - 28, size=46, bold=True, color=WHITE, align="center")

    # Vertical divider after col 2
    pygame.draw.line(surf, GRAY, (COL1_W + COL2_W, panel_y + 10), (COL1_W + COL2_W, panel_y + panel_h - 10), 1)

    # ── Column 3: Airline name + aircraft type ──
    if airline_name and airline_name != "?":
        blit_text(surf, airline_name, COL3_CX, mid_y - 22, size=20, color=CYAN, align="center")

    if ac_type and ac_type not in ("?", "..."):
        blit_text(surf, ac_type, COL3_CX, mid_y + 12, size=16, color=LGRAY, align="center")
    elif ac_type == "...":
        blit_text(surf, "...", COL3_CX, mid_y + 12, size=16, color=GRAY, align="center")


def find_principal_aircraft(aircraft_list: list[dict], config: dict) -> dict | None:
    """Return the closest aircraft eligible for the main panel:
    - within distanza_max_princ (if set)
    - has a callsign
    - route data is not definitively missing (origin iata != '?')
    """
    max_princ = config.get("distanza_max_princ")
    ref_lat   = config["Punto_rif_lat"]
    ref_lon   = config["Punto_rif_lon"]

    for ac in aircraft_list:
        if max_princ is not None and dist_from_ref(ac, ref_lat, ref_lon) > max_princ:
            continue
        cs = (ac.get("flight") or "").strip()
        if not cs:
            continue
        orig, _ = routes.get_route(cs)
        if orig["iata"] == "?":          # rotta definitivamente sconosciuta
            continue
        return ac
    return None


def draw_strip3_airports(surf: pygame.Surface, principal: dict | None) -> None:
    """Strip 4 (index 3): departure and arrival airports for principal aircraft."""
    y0    = 3 * STRIP_H
    mid_y = y0 + STRIP_H // 2
    if principal is None:
        return

    ac = principal
    cs = (ac.get("flight") or "").strip()
    orig, dest = routes.get_route(cs) if cs else (routes._MISSING, routes._MISSING)

    # ── Centre arrow ──
    cx = W // 2
    blit_text(surf, "->", cx, mid_y - 12, size=22, color=GRAY, align="center")

    # ── Left: departure ──
    dep_iata = orig["iata"]
    dep_name = (orig.get("name") or "").strip()
    dep_city = (orig.get("municipality") or "").strip()

    blit_text(surf, dep_iata if dep_iata not in ("?","...") else "—",
              MARGIN_X, y0 + 8, size=30, bold=True, color=WHITE)
    if dep_name and dep_name != "?":
        blit_text(surf, dep_name[:38], MARGIN_X, y0 + 42, size=13, color=LGRAY)
    if dep_city and dep_city != "?":
        blit_text(surf, dep_city, MARGIN_X, y0 + 57, size=13, color=CYAN)

    # ── Right: arrival ──
    arr_iata = dest["iata"]
    arr_name = (dest.get("name") or "").strip()
    arr_city = (dest.get("municipality") or "").strip()

    blit_text(surf, arr_iata if arr_iata not in ("?","...") else "—",
              W - MARGIN_X, y0 + 8, size=30, bold=True, color=WHITE, align="right")
    if arr_name and arr_name != "?":
        blit_text(surf, arr_name[:38], W - MARGIN_X, y0 + 42, size=13,
                  color=LGRAY, align="right")
    if arr_city and arr_city != "?":
        blit_text(surf, arr_city, W - MARGIN_X, y0 + 57, size=13,
                  color=CYAN, align="right")


def _track_to_compass(deg: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    return dirs[round(deg / 22.5) % 16]


def draw_strip4_flightdata(surf: pygame.Surface, principal: dict | None,
                           config: dict) -> None:
    """Strip 5 (index 4): altitude, speed, heading, vertical speed, distance."""
    y0 = 4 * STRIP_H
    if principal is None:
        return
    ac = principal

    ref_lat = config["Punto_rif_lat"]
    ref_lon = config["Punto_rif_lon"]

    # Build the 5 data boxes
    alt = ac.get("alt_baro") or ac.get("alt_geom")
    alt_str = f"{alt:,}" if isinstance(alt, int) else ("GND" if alt == "ground" else "—")

    gs      = ac.get("gs")
    gs_str  = f"{gs:.0f}" if gs is not None else "—"

    track   = ac.get("track")
    hdg_str = f"{track:.0f}°  {_track_to_compass(track)}" if track is not None else "—"

    vrate   = ac.get("baro_rate")
    if vrate is None:
        vs_str   = "—"
        vs_color = LGRAY
    elif vrate > 64:
        vs_str   = f"+{vrate:,}"
        vs_color = GREEN
    elif vrate < -64:
        vs_str   = f"{vrate:,}"
        vs_color = RED
    else:
        vs_str   = "~0"
        vs_color = LGRAY

    if ac.get("lat") is not None:
        dist_km  = haversine_km(ref_lat, ref_lon, ac["lat"], ac["lon"])
        dist_str = f"{dist_km:.1f}"
    else:
        dist_str = "—"

    boxes = [
        ("ALT ft",    alt_str,  WHITE),
        ("GS kt",     gs_str,   WHITE),
        ("ROTTA",     hdg_str,  WHITE),
        ("V/S ft/m",  vs_str,   vs_color),
        ("DIST km",   dist_str, WHITE),
    ]

    n     = len(boxes)
    col_w = W // n
    lbl_s = 13
    val_s = 22

    for i, (label, value, color) in enumerate(boxes):
        cx = i * col_w + col_w // 2
        blit_text(surf, label, cx, y0 + 10, size=lbl_s, color=LGRAY, align="center")
        blit_text(surf, value, cx, y0 + 30, size=val_s, bold=True, color=color, align="center")

        # vertical separator between boxes
        if i > 0:
            pygame.draw.line(surf, GRAY,
                             (i * col_w, y0 + 8), (i * col_w, y0 + STRIP_H - 8), 1)


def draw_strip5_progress(surf: pygame.Surface, principal: dict | None) -> None:
    """Strip 6 (index 5): horizontal progress bar."""
    y0 = 5 * STRIP_H
    if principal is None:
        return
    ac = principal

    cs = (ac.get("flight") or "").strip()
    orig, dest = routes.get_route(cs) if cs else (routes._MISSING, routes._MISSING)

    dep_iata = orig["iata"]
    arr_iata = dest["iata"]

    # Compute percentage
    pct_val: float | None = None
    if ac.get("lat") is not None and dep_iata not in ("?", "...") and arr_iata not in ("?", "..."):
        import airports as _ap
        oc = (orig["lat"], orig["lon"]) if orig["lat"] else _ap.get_coords_iata(dep_iata)
        dc = (dest["lat"], dest["lon"]) if dest["lat"] else _ap.get_coords_iata(arr_iata)
        if oc and dc:
            total = haversine_km(oc[0], oc[1], dc[0], dc[1])
            if total > 10:
                flown   = haversine_km(oc[0], oc[1], ac["lat"], ac["lon"])
                pct_val = min(flown / total * 100, 100)

    # Layout
    LABEL_W  = 60
    BAR_X    = MARGIN_X + LABEL_W + 12
    BAR_W    = W - BAR_X - LABEL_W - MARGIN_X - 12
    BAR_H    = 28
    BAR_Y    = y0 + (STRIP_H - BAR_H) // 2

    # Departure label (left)
    dep_label = dep_iata if dep_iata not in ("?", "...") else "—"
    blit_text(surf, dep_label, MARGIN_X + LABEL_W, BAR_Y + BAR_H // 2 - 10,
              size=18, bold=True, color=WHITE, align="right")

    # Arrival label (right)
    arr_label = arr_iata if arr_iata not in ("?", "...") else "—"
    blit_text(surf, arr_label, W - MARGIN_X - LABEL_W, BAR_Y + BAR_H // 2 - 10,
              size=18, bold=True, color=WHITE)

    # Bar background
    pygame.draw.rect(surf, GRAY, (BAR_X, BAR_Y, BAR_W, BAR_H), 1)

    if pct_val is not None:
        filled = int(BAR_W * pct_val / 100)
        if filled > 0:
            # Filled portion: gradient-like effect with two rects
            pygame.draw.rect(surf, CYAN, (BAR_X, BAR_Y, filled, BAR_H))
            # Bright leading edge
            pygame.draw.rect(surf, WHITE, (BAR_X + filled - 2, BAR_Y, 2, BAR_H))

        # Percentage text centred on bar
        pct_text = f"{pct_val:.0f}%"
        txt_x    = BAR_X + BAR_W // 2
        txt_y    = BAR_Y + BAR_H // 2 - 9
        txt_color = BLACK if filled > BAR_W // 2 else WHITE
        blit_text(surf, pct_text, txt_x, txt_y, size=16, bold=True,
                  color=txt_color, align="center")
    else:
        blit_text(surf, "—", BAR_X + BAR_W // 2, BAR_Y + BAR_H // 2 - 9,
                  size=16, color=GRAY, align="center")


def draw_strip67_aircraft(surf: pygame.Surface, aircraft_list: list[dict],
                          config: dict) -> None:
    """Strips 7+8 merged (120 px): aircraft table."""
    ref_lat = config["Punto_rif_lat"]
    ref_lon = config["Punto_rif_lon"]
    y0 = AC_STRIP_START * STRIP_H + DIVIDER_W + 4

    hs = 14
    hy = y0
    blit_text(surf, "CALLSIGN", COL_CS,   hy, size=hs, color=LGRAY, bold=True)
    blit_text(surf, "PARTENZA", COL_DEP,  hy, size=hs, color=LGRAY, bold=True)
    blit_text(surf, "ARRIVO",   COL_ARR,  hy, size=hs, color=LGRAY, bold=True)
    blit_text(surf, "%",        COL_PCT,  hy, size=hs, color=LGRAY, bold=True)
    blit_text(surf, "ALT ft",   COL_ALT,  hy, size=hs, color=LGRAY, bold=True)
    blit_text(surf, "GS kt",    COL_GS,   hy, size=hs, color=LGRAY, bold=True)
    blit_text(surf, "DIST km",  COL_DIST, hy, size=hs, color=LGRAY, bold=True)

    sep_y = hy + hs + 4
    pygame.draw.line(surf, GRAY, (MARGIN_X, sep_y), (W - MARGIN_X, sep_y), 1)

    row_h    = 20
    row_s    = 15
    max_rows = (AC_PANEL_H - (sep_y - y0) - 10) // row_h

    for i, ac in enumerate(aircraft_list[:max_rows]):
        ry = sep_y + 5 + i * row_h
        cs = (ac.get("flight") or "").strip() or "—"
        callsign = cs if cs != "—" else ""
        orig, dest = routes.get_route(callsign) if callsign else (
            routes._MISSING, routes._MISSING)

        d = dist_from_ref(ac, ref_lat, ref_lon)
        row_color = GREEN if d < 30 else (YELLOW if d < 80 else WHITE)

        blit_text(surf, cs,               COL_CS,   ry, size=row_s, color=row_color, bold=True)
        blit_text(surf, fmt_airport(orig), COL_DEP,  ry, size=row_s, color=WHITE)
        blit_text(surf, fmt_airport(dest), COL_ARR,  ry, size=row_s, color=WHITE)
        blit_text(surf, flight_pct(ac),   COL_PCT,  ry, size=row_s, color=LGRAY)
        blit_text(surf, fmt_alt(ac),      COL_ALT,  ry, size=row_s, color=LGRAY)
        blit_text(surf, fmt_speed(ac),    COL_GS,   ry, size=row_s, color=LGRAY)
        blit_text(surf, fmt_dist(ac, ref_lat, ref_lon), COL_DIST, ry, size=row_s, color=LGRAY)


def draw_dividers(surf: pygame.Surface) -> None:
    """White lines between strips — skip internal dividers of merged panels."""
    merged_internal = {CLOSEST_STRIP_START + 1, AC_STRIP_START + 1}
    for i in range(1, N_STRIPS):
        if i in merged_internal:
            continue
        pygame.draw.line(surf, WHITE, (0, i * STRIP_H), (W, i * STRIP_H), DIVIDER_W)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    config  = load_config()
    ref_lat = config["Punto_rif_lat"]
    ref_lon = config["Punto_rif_lon"]
    max_dist = config.get("distanza_rilevamento")

    threading.Thread(target=lambda: airports.get_coords_iata("FCO"), daemon=True).start()

    pygame.init()
    pygame.display.set_caption("ADS-B Radar")
    surf  = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    last_refresh = 0
    aircraft_list: list[dict] = []

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
                pygame.quit(); sys.exit()

        now = time.time()
        if now - last_refresh >= REFRESH_MS / 1000:
            last_refresh = now
            try:
                raw = load_aircraft()
                filtered = [a for a in raw
                            if max_dist is None or dist_from_ref(a, ref_lat, ref_lon) <= max_dist]
                aircraft_list = sorted(filtered, key=lambda a: dist_from_ref(a, ref_lat, ref_lon))
                for ac in aircraft_list:
                    cs  = (ac.get("flight") or "").strip()
                    hex24 = ac.get("hex", "")
                    if cs:
                        routes.get_route(cs)
                        routes.get_airline(cs)
                    if hex24:
                        routes.get_aircraft_type(hex24)
            except Exception:
                pass

        # ── Draw ──
        surf.fill(BLACK)
        now_str   = datetime.now().strftime("%H:%M:%S")
        n_total   = sum(1 for _ in (load_aircraft() or []))
        n_visible = len(aircraft_list)
        blink_on  = int(time.time() * 2) % 2 == 0   # toggle ogni 0.5 s
        principal = find_principal_aircraft(aircraft_list, config)

        draw_strip0_header(surf, config, n_total, n_visible, now_str, blink_on)
        draw_strip23_closest(surf, principal, config)
        draw_strip3_airports(surf, principal)
        draw_strip4_flightdata(surf, principal, config)
        draw_strip5_progress(surf, principal)
        draw_strip67_aircraft(surf, aircraft_list, config)
        draw_dividers(surf)

        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()
