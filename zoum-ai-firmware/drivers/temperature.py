"""
Driver DHT22 — Température + Humidité.

Capteur : DHT22 (AM2302)
Interface : GPIO digital (1-wire propriétaire)
Données : température (-40 à 80°C, ±0.5°C), humidité (0-100%, ±2-5%)

Fréquence max : 1 lecture / 2 secondes (cache interne).
"""
from __future__ import annotations
import time

_dht = None
_last_read = 0.0
_cache = {"temperature_c": None, "humidity_pct": None, "ok": False}


def init(gpio_pin: int = 4) -> bool:
    global _dht
    try:
        import board
        import adafruit_dht
        pin_map = {4: board.D4, 17: board.D17, 27: board.D27, 22: board.D22}
        _dht = adafruit_dht.DHT22(pin_map.get(gpio_pin, board.D4))
        print(f"[TEMP] DHT22 initialisé sur GPIO {gpio_pin}")
        return True
    except Exception as e:
        print(f"[TEMP] Init échoué: {e}")
        return False


def read() -> dict:
    """Retourne température et humidité. Cache de 2s (limite DHT22)."""
    global _last_read, _cache
    now = time.time()
    if now - _last_read < 2.0:
        return _cache

    if _dht is None:
        return _cache

    try:
        temp = _dht.temperature
        hum = _dht.humidity
        if temp is not None and hum is not None:
            _cache = {
                "temperature_c": round(temp, 1),
                "humidity_pct": round(hum, 1),
                "ok": True,
            }
            _last_read = now
    except RuntimeError:
        pass  # DHT22 rate souvent, on garde le cache
    except Exception as e:
        print(f"[TEMP] Erreur: {e}")

    return _cache


def cleanup():
    global _dht
    if _dht:
        try:
            _dht.exit()
        except Exception:
            pass
        _dht = None
