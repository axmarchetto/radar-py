"""Hardware abstraction — runs on both PC (simulated) and Raspberry Pi (real GPIO/audio)."""

import array
import math
import os
import threading
import time

import pygame

# ── Detect platform ───────────────────────────────────────────────────────────

def _is_rpi() -> bool:
    try:
        with open("/proc/device-tree/model") as f:
            return "Raspberry" in f.read()
    except OSError:
        return False

IS_RPI = _is_rpi()

# ── GPIO abstraction ──────────────────────────────────────────────────────────

_gpio_ready = False
_fan_pin    = None
_pir_pin    = None

def _init_gpio(fan_pin: int, pir_pin: int) -> None:
    global _gpio_ready, _fan_pin, _pir_pin
    _fan_pin = fan_pin
    _pir_pin = pir_pin
    if not IS_RPI:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(fan_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(pir_pin, GPIO.IN)
        _gpio_ready = True
    except Exception as e:
        print(f"[hardware] GPIO init failed: {e}")


def set_fan(on: bool) -> None:
    if not IS_RPI or not _gpio_ready:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.output(_fan_pin, GPIO.HIGH if on else GPIO.LOW)
    except Exception:
        pass


def get_pir() -> bool:
    """Return True if motion detected. On PC always returns True (simulated)."""
    if not IS_RPI or not _gpio_ready:
        return True   # PC simulation: always motion detected
    try:
        import RPi.GPIO as GPIO
        return GPIO.input(_pir_pin) == GPIO.HIGH
    except Exception:
        return True


def cleanup() -> None:
    if not IS_RPI or not _gpio_ready:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except Exception:
        pass


# ── CPU temperature ───────────────────────────────────────────────────────────

def get_cpu_temp() -> float:
    """Return CPU temperature in °C. Falls back to 40.0 if not readable."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return 40.0   # PC simulation fallback


# ── Audio beep (pygame.mixer) ─────────────────────────────────────────────────

_beep_sound: pygame.mixer.Sound | None = None
_audio_ok = False


def _make_beep(freq: int = 880, duration: float = 0.25,
               volume: float = 0.6, sample_rate: int = 22050) -> pygame.mixer.Sound:
    n   = int(sample_rate * duration)
    buf = array.array("h", [0] * n)
    fade = int(sample_rate * 0.02)   # 20 ms fade-in/out to avoid clicks
    for i in range(n):
        t   = i / sample_rate
        val = math.sin(2 * math.pi * freq * t)
        if i < fade:
            val *= i / fade
        elif i > n - fade:
            val *= (n - i) / fade
        buf[i] = int(val * volume * 32767)
    return pygame.mixer.Sound(buffer=buf)


def init_audio() -> None:
    global _beep_sound, _audio_ok
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        _beep_sound = _make_beep()
        _audio_ok   = True
    except Exception as e:
        print(f"[hardware] audio init failed: {e}")


def play_beep() -> None:
    if _audio_ok and _beep_sound:
        _beep_sound.play()


# ── Display power (RPi only) ──────────────────────────────────────────────────

def set_display_power(on: bool) -> None:
    """Turn HDMI display on/off on RPi. No-op on PC."""
    if not IS_RPI:
        return
    cmd = "vcgencmd display_power 1" if on else "vcgencmd display_power 0"
    os.system(cmd)


# ── Public init ───────────────────────────────────────────────────────────────

def init(config: dict) -> None:
    fan_pin = config.get("gpio_fan", 18)
    pir_pin = config.get("gpio_pir", 17)
    _init_gpio(fan_pin, pir_pin)
    init_audio()
