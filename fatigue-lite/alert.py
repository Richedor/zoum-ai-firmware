"""
Module d'alerte — buzzer GPIO (Pi) + alerte console/visuelle.

Sur Raspberry Pi : utilise RPi.GPIO pour piloter un buzzer passif.
Sur PC / sans GPIO : alerte console uniquement.
"""
import time
import config

# ─── Tentative d'import GPIO ────────────────────────────────────────
_HAS_GPIO = False
_gpio = None
try:
    import RPi.GPIO as GPIO  # type: ignore
    _HAS_GPIO = True
    _gpio = GPIO
except ImportError:
    try:
        import lgpio  # type: ignore
        # lgpio est le nouveau standard sur Pi 5 / Bookworm
        _HAS_GPIO = False  # API différente, on gère séparément
    except ImportError:
        pass


class AlertManager:
    """Gère les alertes sonores (buzzer) et visuelles."""

    def __init__(self, enabled=None, gpio_pin=None, freq_hz=None):
        self.enabled = enabled if enabled is not None else config.BUZZER_ENABLED
        self.gpio_pin = gpio_pin or config.BUZZER_GPIO_PIN
        self.freq_hz = freq_hz or config.BUZZER_FREQ_HZ
        self._buzzer_on = False
        self._pwm = None
        self._last_beep = 0.0

        if self.enabled and _HAS_GPIO:
            try:
                _gpio.setwarnings(False)
                _gpio.setmode(_gpio.BCM)
                _gpio.setup(self.gpio_pin, _gpio.OUT)
                self._pwm = _gpio.PWM(self.gpio_pin, self.freq_hz)
                print(f"[ALERT] Buzzer GPIO {self.gpio_pin} initialisé")
            except Exception as e:
                print(f"[ALERT] GPIO init échoué: {e} — alertes console seulement")
                self._pwm = None

    # ── Déclenchement ────────────────────────────────────────────────
    def trigger(self, level, level_name=""):
        """
        Déclenche l'alerte selon le niveau.
          0 = normal       → buzzer OFF
          1 = avertissement → bip intermittent lent
          2 = alerte        → bip intermittent rapide
          3 = microsommeil  → bip continu
        """
        now = time.time()

        if level == 0:
            self._stop_buzzer()
            return

        # Affichage console
        if now - self._last_beep > 1.0:
            tag = "⚠️" if level == 1 else ("🚨" if level >= 2 else "")
            print(f"[ALERT] {tag} {level_name} (niveau {level})")
            self._last_beep = now

        # Buzzer GPIO
        if self._pwm is not None:
            if level >= 3:
                self._start_buzzer(duty=80)
            elif level >= 2:
                # Bip rapide (toggle ~4 Hz)
                if int(now * 4) % 2 == 0:
                    self._start_buzzer(duty=50)
                else:
                    self._stop_buzzer()
            elif level >= 1:
                # Bip lent (toggle ~1 Hz)
                if int(now) % 2 == 0:
                    self._start_buzzer(duty=30)
                else:
                    self._stop_buzzer()

    # ── Contrôle buzzer ──────────────────────────────────────────────
    def _start_buzzer(self, duty=50):
        if self._pwm and not self._buzzer_on:
            try:
                self._pwm.start(duty)
                self._buzzer_on = True
            except Exception:
                pass

    def _stop_buzzer(self):
        if self._pwm and self._buzzer_on:
            try:
                self._pwm.stop()
                self._buzzer_on = False
            except Exception:
                pass

    # ── Nettoyage ────────────────────────────────────────────────────
    def cleanup(self):
        self._stop_buzzer()
        if _HAS_GPIO:
            try:
                _gpio.cleanup(self.gpio_pin)
            except Exception:
                pass

    def __del__(self):
        self.cleanup()
