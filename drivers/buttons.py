"""
Driver Boutons — 4 boutons poussoir avec debounce (polling).

Câblage : chaque bouton entre GPIO et GND (pull-up interne).
  BTN_START (▶) : GPIO 5
  BTN_STOP  (■) : GPIO 6
  BTN_MENU  (☰) : GPIO 13
  BTN_BACK  (↩) : GPIO 19

Appui = GPIO LOW (pull-up interne activé).
Debounce logiciel 200 ms.
Mode polling (compatible Pi Zero 2W / kernels récents).
"""
from __future__ import annotations
import time
from collections import deque

_gpio = None
_initialized = False
_event_queue: deque = deque(maxlen=32)
_pins = {}
_last_press = {}
_prev_state = {}  # état précédent de chaque pin (HIGH/LOW)

BTN_START = "start"
BTN_STOP  = "stop"
BTN_MENU  = "menu"
BTN_BACK  = "back"

DEBOUNCE_S = 0.2  # 200 ms


def init(pin_start: int = 5, pin_stop: int = 6, pin_menu: int = 13, pin_back: int = 19) -> bool:
    global _gpio, _initialized, _pins
    try:
        import RPi.GPIO as GPIO
        _gpio = GPIO
        _gpio.setwarnings(False)
        _gpio.setmode(_gpio.BCM)

        _pins = {
            pin_start: BTN_START,
            pin_stop:  BTN_STOP,
            pin_menu:  BTN_MENU,
            pin_back:  BTN_BACK,
        }

        for pin in _pins:
            _gpio.setup(pin, _gpio.IN, pull_up_down=_gpio.PUD_UP)
            _last_press[pin] = 0.0
            _prev_state[pin] = _gpio.HIGH  # bouton relâché

        _initialized = True
        print(f"[BTN] 4 boutons initialisés (polling) : {list(_pins.values())}")
        return True
    except Exception as e:
        print(f"[BTN] Init échoué: {e}")
        import traceback
        traceback.print_exc()
        return False


def _scan():
    """Lit l'état de chaque pin et détecte les fronts descendants (press)."""
    if not _initialized or _gpio is None:
        return
    now = time.time()
    for pin, name in _pins.items():
        current = _gpio.input(pin)
        prev = _prev_state.get(pin, _gpio.HIGH)

        # Front descendant : HIGH → LOW = bouton pressé
        if prev == _gpio.HIGH and current == _gpio.LOW:
            if now - _last_press.get(pin, 0) >= DEBOUNCE_S:
                _last_press[pin] = now
                _event_queue.append((name, now))

        _prev_state[pin] = current


def poll() -> str | None:
    """Scanne les pins puis retourne le prochain événement, ou None."""
    _scan()
    if _event_queue:
        name, _ts = _event_queue.popleft()
        return name
    return None


def poll_all() -> list[str]:
    """Retourne tous les événements en attente."""
    _scan()
    events = []
    while _event_queue:
        name, _ts = _event_queue.popleft()
        events.append(name)
    return events


def is_pressed(button_name: str) -> bool:
    """Vérifie si un bouton est actuellement enfoncé."""
    if not _initialized or _gpio is None:
        return False
    for pin, name in _pins.items():
        if name == button_name:
            return _gpio.input(pin) == _gpio.LOW
    return False


def cleanup():
    global _initialized
    _initialized = False
