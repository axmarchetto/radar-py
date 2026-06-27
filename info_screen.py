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


# ── Weather fetching (OpenWeatherMap) ─────────────────────────────────────────
WEATHER_TTL = 600  # 10 minutes

_weather:      dict | None = None
_weather_at    = 0.0
_weather_lock  = threading.Lock()
_weather_pend  = False


def _fetch_weather(api_key: str, city: str) -> None:
    global _weather, _weather_at, _weather_pend
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": "metric", "lang": "it"},
            timeout=8,
            headers={"User-Agent": "radar_py/1.0"},
        )
        if r.status_code == 200:
            d = r.json()
            result = {
                "temp":     round(d["main"]["temp"]),
                "feels":    round(d["main"]["feels_like"]),
                "temp_min": round(d["main"]["temp_min"]),
                "temp_max": round(d["main"]["temp_max"]),
                "humidity": d["main"]["humidity"],
                "wind":     round(d["wind"]["speed"] * 3.6),   # m/s → km/h
                "desc":     d["weather"][0]["description"].capitalize(),
                "icon":     d["weather"][0]["icon"],
                "city":     d["name"],
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
    api_key = config.get("openweather_api_key", "").strip()
    city    = config.get("openweather_city", "").strip()
    if not api_key or not city:
        return None
    with _weather_lock:
        fresh = _weather is not None and (time.time() - _weather_at < WEATHER_TTL)
        if not fresh and not _weather_pend:
            _weather_pend = True
            threading.Thread(target=_fetch_weather, args=(api_key, city), daemon=True).start()
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
    text = "   ✦   ".join(headlines) + "   ✦   "
    f    = _font(20)
    return f.render(text, True, WHITE)


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
    _text(surf, time_str, W // 2, DATETIME_Y_TOP + 20, size=88, bold=True,
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
    cx      = W // 2
    mid_y   = WEATHER_Y_TOP + panel_h // 2

    api_key = config.get("openweather_api_key", "").strip()

    if not api_key:
        # No API key configured
        _text(surf, "Meteo non configurato", cx, mid_y - 30, size=22,
              color=GRAY, align="center")
        _text(surf, "Aggiungere openweather_api_key e openweather_city in config.json",
              cx, mid_y + 10, size=15, color=GRAY, align="center")
        _text(surf, "API gratuita su openweathermap.org",
              cx, mid_y + 36, size=14, color=GRAY, align="center")
    elif weather is None:
        _text(surf, "...", cx, mid_y - 10, size=28, color=GRAY, align="center")
    else:
        ICON_CX = 220
        ICON_CY = mid_y
        ICON_SZ = 180

        # Weather icon
        draw_weather_icon(surf, ICON_CX, ICON_CY, weather["icon"], ICON_SZ)

        # City name
        _text(surf, weather["city"], cx + 60, WEATHER_Y_TOP + 18,
              size=22, color=LGRAY, align="center")

        # Temperature (large)
        _text(surf, f"{weather['temp']}°", cx + 60, WEATHER_Y_TOP + 50,
              size=90, bold=True, color=CYAN, align="center")

        # Description
        _text(surf, weather["desc"], cx + 60, WEATHER_Y_TOP + 155,
              size=22, color=WHITE, align="center")

        # Details row
        details_y = WEATHER_Y_TOP + 195
        details = [
            (f"min {weather['temp_min']}°  max {weather['temp_max']}°", LGRAY),
            (f"Umidita'  {weather['humidity']}%",                        LGRAY),
            (f"Vento  {weather['wind']} km/h",                           LGRAY),
            (f"Percepita  {weather['feels']}°",                          LGRAY),
        ]
        col_w = (W - 120) // len(details)
        for i, (txt, col) in enumerate(details):
            _text(surf, txt, 60 + i * col_w + col_w // 2, details_y,
                  size=17, color=col, align="center")

    # Divider
    pygame.draw.line(surf, GRAY, (40, WEATHER_Y_BOT - 2), (W - 40, WEATHER_Y_BOT - 2), 1)


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
        _text(surf, "recupero notizie...", label_w + 20, mid_y - 10,
              size=18, color=GRAY)
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
