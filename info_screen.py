"""Info screen: date/time, weather, scrolling ANSA news ticker."""

import math
import os
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import pygame
import requests

# ── Colors (dark theme) ───────────────────────────────────────────────────────
BLACK  = (  0,   0,   0)
WHITE  = (255, 255, 255)
GRAY   = ( 70,  70,  70)
LGRAY  = (160, 160, 160)
CYAN   = (  0, 200, 220)
YELLOW = (240, 200,   0)
BLUE   = ( 80, 140, 220)
RED    = (220,  60,  60)

W, H = 1024, 600

# ── Layout zones ──────────────────────────────────────────────────────────────
DATETIME_Y_TOP  = 0
DATETIME_Y_BOT  = 190
WEATHER_Y_TOP   = 190
WEATHER_Y_BOT   = 460
TICKER_Y_TOP    = 460
TICKER_Y_BOT    = H

# ── Font cache ────────────────────────────────────────────────────────────────
_fonts: dict[tuple, pygame.font.Font] = {}

def _font(size: int, bold: bool = False) -> pygame.font.Font:
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

def _text(surf, text, x, y, size=16, color=WHITE, bold=False, align="left"):
    f = _font(size, bold)
    rendered = f.render(str(text), True, color)
    if align == "right":
        x -= rendered.get_width()
    elif align == "center":
        x -= rendered.get_width() // 2
    surf.blit(rendered, (x, y))
    return rendered.get_width()

# ── News fetching (ANSA RSS) ──────────────────────────────────────────────────
DEFAULT_RSS = "https://www.ansa.it/sito/notizie/cronaca/cronaca_rss.xml"
NEWS_TTL    = 300   # 5 minutes

_news: list[str] = []
_news_at   = 0.0
_news_lock = threading.Lock()
_news_pend = False


def _fetch_news(url: str) -> None:
    global _news, _news_at, _news_pend
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "radar_py/1.0"})
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:20]:
            title = (item.findtext("title") or "").strip()
            if title:
                items.append(title)
    except Exception:
        items = []
    with _news_lock:
        if items:
            _news = items
        _news_at   = time.time()
        _news_pend = False


def _get_news(config: dict) -> list[str]:
    global _news_pend
    url = config.get("news_rss_url", DEFAULT_RSS)
    with _news_lock:
        fresh = bool(_news) and (time.time() - _news_at < NEWS_TTL)
        if not fresh and not _news_pend:
            _news_pend = True
            threading.Thread(target=_fetch_news, args=(url,), daemon=True).start()
        return list(_news)


# ── Weather fetching (Open-Meteo — no API key required) ──────────────────────
WEATHER_TTL = 600  # 10 minutes

_weather:     dict | None = None
_weather_at   = 0.0
_weather_lock = threading.Lock()
_weather_pend = False

_WMO_DESC = {
    0: "Cielo sereno", 1: "Prevalentemente sereno", 2: "Parzialmente nuvoloso",
    3: "Nuvoloso", 45: "Nebbia", 48: "Nebbia con brina",
    51: "Pioggerella leggera", 53: "Pioggerella", 55: "Pioggerella intensa",
    61: "Pioggia leggera", 63: "Pioggia", 65: "Pioggia intensa",
    71: "Neve leggera", 73: "Neve", 75: "Neve intensa", 77: "Granelli di neve",
    80: "Rovesci leggeri", 81: "Rovesci", 82: "Rovesci intensi",
    85: "Rovesci di neve", 86: "Rovesci di neve intensi",
    95: "Temporale", 96: "Temporale con grandine", 99: "Temporale con grandine intensa",
}

_WMO_ICON = {
    0: "01d", 1: "02d", 2: "02d", 3: "03d",
    45: "50d", 48: "50d",
    51: "09d", 53: "09d", 55: "09d",
    61: "10d", 63: "10d", 65: "10d",
    71: "13d", 73: "13d", 75: "13d", 77: "13d",
    80: "09d", 81: "09d", 82: "09d",
    85: "13d", 86: "13d",
    95: "11d", 96: "11d", 99: "11d",
}


def _fetch_weather(lat: float, lon: float, city_name: str) -> None:
    global _weather, _weather_at, _weather_pend
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":  lat,
                "longitude": lon,
                "current":   "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily":     "temperature_2m_max,temperature_2m_min,weather_code",
                "wind_speed_unit": "kmh",
                "timezone":  "auto",
            },
            timeout=8,
            headers={"User-Agent": "radar_py/1.0"},
        )
        if r.status_code == 200:
            d    = r.json()
            cur  = d["current"]
            day  = d["daily"]
            code = int(cur["weather_code"])
            result = {
                "temp":     round(cur["temperature_2m"]),
                "feels":    round(cur["apparent_temperature"]),
                "temp_min": round(day["temperature_2m_min"][0]),
                "temp_max": round(day["temperature_2m_max"][0]),
                "humidity": cur["relative_humidity_2m"],
                "wind":     round(cur["wind_speed_10m"]),
                "desc":     _WMO_DESC.get(code, f"Codice {code}"),
                "icon":     _WMO_ICON.get(code, "03d"),
                "city":     city_name,
                "tomorrow_min":  round(day["temperature_2m_min"][1]),
                "tomorrow_max":  round(day["temperature_2m_max"][1]),
                "tomorrow_icon": _WMO_ICON.get(int(day["weather_code"][1]), "03d"),
                "d2_min":  round(day["temperature_2m_min"][2]),
                "d2_max":  round(day["temperature_2m_max"][2]),
                "d2_icon": _WMO_ICON.get(int(day["weather_code"][2]), "03d"),
            }
        else:
            result = None
    except Exception:
        result = None
    with _weather_lock:
        _weather    = result
        _weather_at = time.time()
        _weather_pend = False


def _get_weather(config: dict) -> dict | None:
    global _weather_pend
    lat  = config.get("Punto_rif_lat")
    lon  = config.get("Punto_rif_lon")
    name = config.get("Punto_di_riferimento", "Casa")
    if lat is None or lon is None:
        return None
    with _weather_lock:
        fresh = _weather is not None and (time.time() - _weather_at < WEATHER_TTL)
        if not fresh and not _weather_pend:
            _weather_pend = True
            threading.Thread(target=_fetch_weather, args=(lat, lon, name), daemon=True).start()
        return dict(_weather) if _weather else None


# ── Weather icon drawing (geometric, no external images) ──────────────────────

def _draw_sun(surf, cx, cy, r, color=YELLOW):
    pygame.draw.circle(surf, color, (cx, cy), r)
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = int(cx + (r + 4) * math.cos(angle))
        y1 = int(cy + (r + 4) * math.sin(angle))
        x2 = int(cx + (r + 14) * math.cos(angle))
        y2 = int(cy + (r + 14) * math.sin(angle))
        pygame.draw.line(surf, color, (x1, y1), (x2, y2), 3)


def _draw_cloud(surf, cx, cy, r, color=(180, 180, 180)):
    pygame.draw.ellipse(surf, color, (cx - r,       cy - r//2, r*2,       r))
    pygame.draw.ellipse(surf, color, (cx - r*2//3,  cy - r,    r*4//3,    r))
    pygame.draw.ellipse(surf, color, (cx,            cy - r//3, r*4//3,    r))


def _draw_rain_drops(surf, cx, cy, r, color=BLUE):
    for i in range(4):
        x = cx - r + i * (r * 2 // 3)
        pygame.draw.line(surf, color, (x, cy), (x - 6, cy + 18), 2)


def _draw_snow_flakes(surf, cx, cy, r, color=WHITE):
    for i in range(4):
        x = cx - r + i * (r * 2 // 3)
        pygame.draw.circle(surf, color, (x, cy + 10), 4)
        pygame.draw.circle(surf, color, (x, cy + 20), 3)


def _draw_lightning(surf, cx, cy, color=YELLOW):
    pts = [(cx+5, cy), (cx-5, cy+12), (cx+2, cy+12), (cx-8, cy+28), (cx+10, cy+14), (cx+2, cy+14)]
    pygame.draw.polygon(surf, color, pts)


def _draw_mist_lines(surf, cx, cy, r, color=LGRAY):
    for i in range(4):
        y = cy - r//2 + i * (r//3)
        w = r + 10 - i * 5
        pygame.draw.line(surf, color, (cx - w, y), (cx + w, y), 3)


def draw_weather_icon(surf: pygame.Surface, cx: int, cy: int,
                      icon_code: str, size: int) -> None:
    """Draw a geometric weather icon centred at (cx, cy)."""
    r = size // 4
    base = icon_code[:2]

    if base == "01":                          # clear sky
        _draw_sun(surf, cx, cy, r)
    elif base == "02":                        # few clouds
        _draw_sun(surf, cx - r//2, cy - r//2, r * 2 // 3)
        _draw_cloud(surf, cx + r//3, cy + r//3, r)
    elif base in ("03", "04"):               # cloudy
        _draw_cloud(surf, cx, cy, r + 8)
    elif base == "09":                        # shower rain
        _draw_cloud(surf, cx, cy - r//2, r)
        _draw_rain_drops(surf, cx, cy + r//2, r)
    elif base == "10":                        # rain
        _draw_sun(surf, cx - r//2, cy - r, r * 2 // 3)
        _draw_cloud(surf, cx, cy - r//3, r)
        _draw_rain_drops(surf, cx, cy + r//2, r)
    elif base == "11":                        # thunderstorm
        _draw_cloud(surf, cx, cy - r//2, r)
        _draw_lightning(surf, cx - 6, cy + r//3)
    elif base == "13":                        # snow
        _draw_cloud(surf, cx, cy - r//2, r)
        _draw_snow_flakes(surf, cx, cy + r//3, r)
    elif base == "50":                        # mist/fog
        _draw_mist_lines(surf, cx, cy, r + 12)
    else:
        pygame.draw.circle(surf, LGRAY, (cx, cy), r, 2)


# ── Scrolling ticker state ────────────────────────────────────────────────────
_ticker_x    = float(W)
_ticker_surf: pygame.Surface | None = None
_ticker_text = ""


def _build_ticker(headlines: list[str]) -> pygame.Surface | None:
    if not headlines:
        return None
    f   = _font(30)
    sep = f.render("  »»  ", True, CYAN)

    text_surfs = [f.render(h, True, WHITE) for h in headlines]
    line_h     = max(s.get_height() for s in text_surfs)
    total_w    = sum(s.get_width() for s in text_surfs) + sep.get_width() * len(text_surfs)

    ticker = pygame.Surface((total_w, line_h))
    ticker.fill(BLACK)

    x = 0
    for ts in text_surfs:
        sep_surf = f.render("  »»  ", True, CYAN)
        ticker.blit(sep_surf, (x, (line_h - sep_surf.get_height()) // 2))
        x += sep_surf.get_width()
        ticker.blit(ts, (x, (line_h - ts.get_height()) // 2))
        x += ts.get_width()

    return ticker


def _update_ticker(headlines: list[str]) -> None:

    global _ticker_surf, _ticker_text, _ticker_x
    joined = " | ".join(headlines)
    if joined != _ticker_text:
        _ticker_text = joined
        _ticker_surf = _build_ticker(headlines)
        _ticker_x    = float(W)


# ── Main draw function ────────────────────────────────────────────────────────

def draw(surf: pygame.Surface, config: dict, now_dt: datetime) -> None:
    surf.fill(BLACK)

    weather  = _get_weather(config)
    headlines = _get_news(config)

    _draw_datetime(surf, now_dt)
    _draw_weather(surf, weather, config)
    _draw_ticker(surf, headlines)


def _draw_datetime(surf: pygame.Surface, now_dt: datetime) -> None:
    panel_h = DATETIME_Y_BOT - DATETIME_Y_TOP

    # Large time
    time_str = now_dt.strftime("%H:%M:%S")
    _text(surf, time_str, W // 2, DATETIME_Y_TOP + 20, size=88,
          color=WHITE, align="center")

    # Date with weekday
    DAYS = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"]
    MONTHS = ["","Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
              "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]
    day_name  = DAYS[now_dt.weekday()]
    date_str  = f"{day_name} {now_dt.day} {MONTHS[now_dt.month]} {now_dt.year}"
    _text(surf, date_str, W // 2, DATETIME_Y_TOP + 130, size=28,
          color=LGRAY, align="center")

    # Divider
    pygame.draw.line(surf, GRAY, (40, DATETIME_Y_BOT - 2), (W - 40, DATETIME_Y_BOT - 2), 1)


def _draw_weather(surf: pygame.Surface, weather: dict | None, config: dict) -> None:
    panel_h = WEATHER_Y_BOT - WEATHER_Y_TOP
    mid_y   = WEATHER_Y_TOP + panel_h // 2

    if weather is None:
        _text(surf, "...", W // 2, mid_y - 10, size=28, color=GRAY, align="center")
        pygame.draw.line(surf, GRAY, (40, WEATHER_Y_BOT - 2), (W - 40, WEATHER_Y_BOT - 2), 1)
        return

    # ── Column boundaries ──
    # Cols: [TODAY (0–512)] | [DOMANI (512–768)] | [DOPODOMANI (768–1024)]
    C1 = 0
    C2 = W // 2          # 512 — start of "domani"
    C3 = W * 3 // 4      # 768 — start of "dopodomani"

    # Vertical dividers
    for x in (C2, C3):
        pygame.draw.line(surf, GRAY, (x, WEATHER_Y_TOP + 10), (x, WEATHER_Y_BOT - 10), 1)

    # ── TODAY (col 1+2) ──
    label_y  = WEATHER_Y_TOP + 8
    _text(surf, "OGGI", C2 // 2, label_y, size=15, color=LGRAY, align="center")

    ICON_SZ = 130
    ICON_CX = C1 + 90
    ICON_CY = WEATHER_Y_TOP + 60 + ICON_SZ // 2
    draw_weather_icon(surf, ICON_CX, ICON_CY, weather["icon"], ICON_SZ)

    txt_x   = C1 + 200
    txt_y   = WEATHER_Y_TOP + 28
    _text(surf, f"{weather['temp']}°", txt_x, txt_y,      size=80, color=CYAN, align="left")
    _text(surf, weather["desc"],       txt_x, txt_y + 88, size=18, color=WHITE, align="left")

    details = [
        f"min {weather['temp_min']}°  max {weather['temp_max']}°",
        f"Percepita {weather['feels']}°",
        f"Umidita' {weather['humidity']}%    Vento {weather['wind']} km/h",
    ]
    for i, txt in enumerate(details):
        _text(surf, txt, txt_x, txt_y + 114 + i * 24, size=16, color=LGRAY, align="left")

    # ── DOMANI (col 3) ──
    _draw_forecast_col(surf, C2, C3, "DOMANI",
                       weather["tomorrow_icon"],
                       weather["tomorrow_min"], weather["tomorrow_max"])

    # ── DOPODOMANI (col 4) ──
    _draw_forecast_col(surf, C3, W, "DOPODOMANI",
                       weather["d2_icon"],
                       weather["d2_min"], weather["d2_max"])

    # Horizontal divider
    pygame.draw.line(surf, GRAY, (40, WEATHER_Y_BOT - 2), (W - 40, WEATHER_Y_BOT - 2), 1)


def _draw_forecast_col(surf: pygame.Surface, x0: int, x1: int, label: str,
                       icon: str, t_min: int, t_max: int) -> None:
    col_w   = x1 - x0
    cx      = x0 + col_w // 2
    panel_h = WEATHER_Y_BOT - WEATHER_Y_TOP

    _text(surf, label, cx, WEATHER_Y_TOP + 8, size=15, color=LGRAY, align="center")

    ICON_SZ = 100
    icon_y  = WEATHER_Y_TOP + 40
    draw_weather_icon(surf, cx, icon_y + ICON_SZ // 2, icon, ICON_SZ)

    _text(surf, f"max {t_max}°", cx, icon_y + ICON_SZ + 14, size=18, color=CYAN, align="center")
    _text(surf, f"min {t_min}°", cx, icon_y + ICON_SZ + 38, size=16, color=LGRAY, align="center")


def _draw_ticker(surf: pygame.Surface, headlines: list[str]) -> None:
    global _ticker_x

    panel_h = TICKER_Y_BOT - TICKER_Y_TOP
    mid_y   = TICKER_Y_TOP + panel_h // 2

    # Source label
    label_w = 80
    pygame.draw.rect(surf, CYAN, (0, TICKER_Y_TOP, label_w, panel_h))
    _text(surf, "ANSA", label_w // 2, mid_y - 11, size=18, bold=True,
          color=BLACK, align="center")

    # Clip region for scrolling text
    clip_rect = pygame.Rect(label_w + 10, TICKER_Y_TOP, W - label_w - 10, panel_h)
    surf.set_clip(clip_rect)

    if not headlines:
        _text(surf, "recupero notizie...", label_w + 20, mid_y - 15,
              size=30, color=GRAY)
    else:
        _update_ticker(headlines)
        if _ticker_surf:
            surf.blit(_ticker_surf, (int(_ticker_x), mid_y - _ticker_surf.get_height() // 2))
            # Advance scroll
            _ticker_x -= 2.5
            tw = _ticker_surf.get_width()
            if _ticker_x < -tw:
                _ticker_x = float(W)

    surf.set_clip(None)
