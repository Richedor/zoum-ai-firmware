"""
Driver Boutons — 4 boutons poussoir avec debounce.

Câblage : chaque bouton entre GPIO et GND (pull-up interne).
  BTN_START (▶) : GPIO 5
  BTN_STOP  (■) : GPIO 6
  BTN_MENU  (☰) : GPIO 13
  BTN_BACK  (↩) : GPIO 19

Appui = GPIO LOW (pull-up interne activé).
Debounce logiciel 200 ms.
"""
from __future__ import annotations
import time
from collections import deque

_gpio = None
_initialized = False
_event_queue: deque = deque(maxlen=32)
_pins = {}
_last_press = {}

BTN_START = "start"
BTN_STOP  = "stop"
BTN_MENU  = "menu"
BTN_BACK  = "back"

DEBOUNCE_MS = 200


def init(pin_start: int = 13, pin_stop: int = 13, pin_menu: int = 13, pin_back: int = 13) -> bool:
    global _gpio, _initialized, _pins
    try:
        print("[BTN][DEBUG] Import RPi.GPIO...")
        import RPi.GPIO as GPIO
        _gpio = GPIO
        print("[BTN][DEBUG] setwarnings(False)")
        _gpio.setwarnings(False)
        print("[BTN][DEBUG] setmode(BCM)")
        _gpio.setmode(_gpio.BCM)

        _pins = {
            pin_start: BTN_START,
            pin_stop:  BTN_STOP,
            pin_menu:  BTN_MENU,
            pin_back:  BTN_BACK,
        }

        for pin in _pins:
            print(f"[BTN][DEBUG] setup pin {pin}")
            _gpio.setup(pin, _gpio.IN, pull_up_down=_gpio.PUD_UP)
            print(f"[BTN][DEBUG] add_event_detect pin {pin}")
            _gpio.add_event_detect(
                pin, _gpio.FALLING,
                callback=_on_press,
                bouncetime=DEBOUNCE_MS,
            )
            _last_press[pin] = 0.0

        _initialized = True
        print(f"[BTN] 4 boutons initialisés : {list(_pins.values())}")
        return True
    except Exception as e:
        print(f"[BTN] Init échoué: {e}")
        import traceback
        traceback.print_exc()
        return False
        print("[BTN][DEBUG] Import RPi.GPIO...")
        import RPi.GPIO as GPIO
        _gpio = GPIO
        print("[BTN][DEBUG] setwarnings(False)")
        _gpio.setwarnings(False)
        print("[BTN][DEBUG] setmode(BCM)")
        _gpio.setmode(_gpio.BCM)

        _pins = {
            pin_start: BTN_START,
            pin_stop:  BTN_STOP,
            pin_menu:  BTN_MENU,
            pin_back:  BTN_BACK,
        }

        for pin in _pins:
            print(f"[BTN][DEBUG] setup pin {pin}")
            _gpio.setup(pin, _gpio.IN, pull_up_down=_gpio.PUD_UP)
            print(f"[BTN][DEBUG] add_event_detect pin {pin}")
            _gpio.add_event_detect(
                pin, _gpio.FALLING,
                callback=_on_press,
                bouncetime=DEBOUNCE_MS,
            )
            _last_press[pin] = 0.0

        _initialized = True
        print(f"[BTN] 4 boutons initialisés : {list(_pins.values())}")
        return True
    except Exception as e:
        print(f"[BTN] Init échoué: {e}")
        import traceback
        traceback.print_exc()
        return False


def _on_press(channel):
    """Callback interrupt sur front descendant."""
    now = time.time()
    if now - _last_press.get(channel, 0) < DEBOUNCE_MS / 1000.0:
        print(f"[BTN][DEBUG] debounce sur pin {channel}")
        return
    _last_press[channel] = now
    name = _pins.get(channel)
    if name:
        print(f"[BTN][DEBUG] événement détecté : {name}")
        _event_queue.append((name, now))


def poll() -> str | None:
    """Retourne le prochain événement bouton, ou None."""
    if _event_queue:
        name, _ts = _event_queue.popleft()
        return name
    return None


def poll_all() -> list[str]:
    """Retourne tous les événements en attente."""
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
    if _gpio:
        for pin in _pins:
            try:
                _gpio.remove_event_detect(pin)
            except Exception:
                pass
    _initialized = False
