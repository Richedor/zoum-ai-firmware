"""
Driver MQ-9 (placeholder MQ-3 alcool) — Détection de gaz.

Capteur : MQ-9 (CO / méthane) — sera remplacé par MQ-3 (alcool).
Interface : GPIO digital (DO)
  - LOW  = gaz détecté (au-dessus du seuil potentiomètre)
  - HIGH = air normal

Note : pas d'ADC sur Pi → lecture digitale uniquement.
"""
from __future__ import annotations

_gpio = None
_pin = None
_initialized = False


def init(gpio_pin: int = 17) -> bool:
    global _gpio, _pin, _initialized
    try:
        import RPi.GPIO as GPIO
        _gpio = GPIO
        _pin = gpio_pin
        _gpio.setwarnings(False)
        _gpio.setmode(_gpio.BCM)
        _gpio.setup(_pin, _gpio.IN)
        _initialized = True
        print(f"[GAS] MQ-9 initialisé sur GPIO {_pin}")
        return True
    except Exception as e:
        print(f"[GAS] Init échoué: {e}")
        return False


def read() -> dict:
    """Retourne l'état du capteur de gaz."""
    if not _initialized or _gpio is None:
        return {"gas_detected": False, "ttl_state": True, "ok": False}

    try:
        val = _gpio.input(_pin)
        gas_detected = (val == _gpio.LOW)
        return {
            "gas_detected": gas_detected,
            "ttl_state": not gas_detected,   # HIGH = normal
            "ok": True,
        }
    except Exception as e:
        print(f"[GAS] Erreur: {e}")
        return {"gas_detected": False, "ttl_state": True, "ok": False}


def cleanup():
    global _initialized
    if _gpio and _pin and _initialized:
        try:
            _gpio.cleanup(_pin)
        except Exception:
            pass
    _initialized = False
