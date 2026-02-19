"""
Driver Buzzer — Alertes sonores à patterns.

Buzzer passif sur GPIO PWM.
Patterns :
  - info     : 1 bip court
  - warning  : 2 bips moyens
  - critical : 3 bips rapides
  - success  : bip montant
  - error    : bip descendant
"""
from __future__ import annotations
import time
import threading

_gpio = None
_pwm = None
_pin = None
_freq = 2000
_initialized = False
_lock = threading.Lock()


def init(gpio_pin: int = 27, freq_hz: int = 2000) -> bool:
    global _gpio, _pwm, _pin, _freq, _initialized
    try:
        import RPi.GPIO as GPIO
        _gpio = GPIO
        _pin = gpio_pin
        _freq = freq_hz
        _gpio.setwarnings(False)
        _gpio.setmode(_gpio.BCM)
        _gpio.setup(_pin, _gpio.OUT)
        _pwm = _gpio.PWM(_pin, _freq)
        _initialized = True
        print(f"[BUZZER] Initialisé sur GPIO {_pin} @ {_freq} Hz")
        return True
    except Exception as e:
        print(f"[BUZZER] Init échoué: {e}")
        return False


def _beep(duration: float = 0.1, duty: int = 50, freq: int = None):
    """Un bip de durée donnée."""
    if not _initialized or _pwm is None:
        return
    try:
        if freq and freq != _freq:
            _pwm.ChangeFrequency(freq)
        _pwm.start(duty)
        time.sleep(duration)
        _pwm.stop()
    except Exception:
        pass


def _run_pattern(fn):
    """Exécute un pattern dans un thread (non-bloquant)."""
    def _wrapper():
        with _lock:
            fn()
    t = threading.Thread(target=_wrapper, daemon=True)
    t.start()


def play(pattern: str = "info"):
    """Joue un pattern sonore (non-bloquant)."""
    patterns = {
        "info": _pattern_info,
        "warning": _pattern_warning,
        "critical": _pattern_critical,
        "success": _pattern_success,
        "error": _pattern_error,
    }
    fn = patterns.get(pattern, _pattern_info)
    _run_pattern(fn)


def _pattern_info():
    _beep(0.1, 40)

def _pattern_warning():
    _beep(0.15, 50)
    time.sleep(0.1)
    _beep(0.15, 50)

def _pattern_critical():
    for _ in range(3):
        _beep(0.1, 70, freq=2500)
        time.sleep(0.08)

def _pattern_success():
    _beep(0.1, 40, freq=1500)
    time.sleep(0.05)
    _beep(0.15, 40, freq=2500)

def _pattern_error():
    _beep(0.15, 50, freq=2500)
    time.sleep(0.05)
    _beep(0.2, 50, freq=1200)


def cleanup():
    global _initialized
    if _pwm:
        try:
            _pwm.stop()
        except Exception:
            pass
    if _gpio and _pin:
        try:
            _gpio.cleanup(_pin)
        except Exception:
            pass
    _initialized = False
