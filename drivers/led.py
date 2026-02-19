"""
Driver LED RGB — Feedback visuel.

LED RGB (cathode commune) sur 3 GPIO avec PWM.
Couleurs prédéfinies :
  - ok        : #cfff47 (vert-jaune Zoum branding)
  - red       : rouge
  - orange    : orange (warning)
  - blue      : bleu (info)
  - offline   : bleu sombre
"""
from __future__ import annotations
import threading
import time

_gpio = None
_pwm_r = None
_pwm_g = None
_pwm_b = None
_initialized = False
_blink_thread = None
_blink_stop = threading.Event()

# Couleurs prédéfinies (R, G, B) 0-255
COLORS = {
    "off":     (0, 0, 0),
    "ok":      (207, 255, 71),      # #cfff47 Zoum branding
    "red":     (255, 0, 0),
    "green":   (0, 255, 0),
    "blue":    (0, 0, 255),
    "orange":  (255, 120, 0),
    "yellow":  (255, 255, 0),
    "white":   (255, 255, 255),
    "offline": (0, 0, 80),
    "error":   (255, 0, 0),
    "warning": (255, 120, 0),
    "info":    (0, 80, 255),
}


def init(pin_r: int = 22, pin_g: int = 23, pin_b: int = 24) -> bool:
    global _gpio, _pwm_r, _pwm_g, _pwm_b, _initialized
    try:
        import RPi.GPIO as GPIO
        _gpio = GPIO
        _gpio.setwarnings(False)
        _gpio.setmode(_gpio.BCM)

        for p in (pin_r, pin_g, pin_b):
            _gpio.setup(p, _gpio.OUT)

        _pwm_r = _gpio.PWM(pin_r, 1000)
        _pwm_g = _gpio.PWM(pin_g, 1000)
        _pwm_b = _gpio.PWM(pin_b, 1000)

        _pwm_r.start(0)
        _pwm_g.start(0)
        _pwm_b.start(0)

        _initialized = True
        print(f"[LED] RGB initialisée sur GPIO R={pin_r} G={pin_g} B={pin_b}")
        return True
    except Exception as e:
        print(f"[LED] Init échoué: {e}")
        return False


def set_color(r: int = 0, g: int = 0, b: int = 0):
    """Fixe la couleur (0-255 par canal)."""
    if not _initialized:
        return
    try:
        _pwm_r.ChangeDutyCycle(r * 100 / 255)
        _pwm_g.ChangeDutyCycle(g * 100 / 255)
        _pwm_b.ChangeDutyCycle(b * 100 / 255)
    except Exception:
        pass


def set_named(name: str):
    """Fixe une couleur prédéfinie."""
    stop_blink()
    r, g, b = COLORS.get(name, (0, 0, 0))
    set_color(r, g, b)


def off():
    stop_blink()
    set_color(0, 0, 0)


def blink(name: str = "red", on_s: float = 0.5, off_s: float = 0.5):
    """Clignotement continu (non-bloquant)."""
    stop_blink()
    _blink_stop.clear()

    def _loop():
        r, g, b = COLORS.get(name, (255, 0, 0))
        while not _blink_stop.is_set():
            set_color(r, g, b)
            if _blink_stop.wait(on_s):
                break
            set_color(0, 0, 0)
            if _blink_stop.wait(off_s):
                break
        set_color(0, 0, 0)

    global _blink_thread
    _blink_thread = threading.Thread(target=_loop, daemon=True)
    _blink_thread.start()


def stop_blink():
    _blink_stop.set()
    if _blink_thread and _blink_thread.is_alive():
        _blink_thread.join(timeout=2)


def cleanup():
    global _initialized
    stop_blink()
    off()
    for pwm in (_pwm_r, _pwm_g, _pwm_b):
        if pwm:
            try:
                pwm.stop()
            except Exception:
                pass
    _initialized = False
