"""
Module PERCLOS & détection de fatigue.

PERCLOS = pourcentage de temps où les yeux sont fermés dans une fenêtre glissante.
  - PERCLOS ≥ 25 % → avertissement
  - PERCLOS ≥ 40 % → alerte critique
  - Yeux fermés en continu > 3 s → microsommeil (alerte immédiate)
  - Bâillements fréquents → avertissement complémentaire
  - Baissement de regard prolongé → avertissement ou alerte
"""
import time
from collections import deque
import config


class FatigueMonitor:
    """Suivi de l'état de fatigue basé sur PERCLOS + microsommeil + bâillements."""

    # Niveaux d'alerte
    LEVEL_NORMAL  = 0
    LEVEL_WARNING = 1
    LEVEL_ALERT   = 2
    LEVEL_MICRO   = 3  # microsommeil

    LEVEL_NAMES = {
        LEVEL_NORMAL:  "NORMAL",
        LEVEL_WARNING: "ATTENTION",
        LEVEL_ALERT:   "ALERTE",
        LEVEL_MICRO:   "MICROSOMMEIL",
    }

    def __init__(
        self,
        window_sec=None,
        warn_threshold=None,
        alert_threshold=None,
        microsleep_sec=None,
    ):
        self.window_sec = window_sec or config.PERCLOS_WINDOW_SEC
        self.warn_threshold = warn_threshold or config.PERCLOS_WARN_THRESHOLD
        self.alert_threshold = alert_threshold or config.PERCLOS_ALERT_THRESHOLD
        self.microsleep_sec = microsleep_sec or config.MICROSLEEP_THRESHOLD_SEC

        # Historique : deque de tuples (timestamp, eyes_closed: bool)
        self._history: deque = deque()

        # Suivi de la fermeture continue
        self._last_closed_start = None  # timestamp du début de fermeture continue
        self._current_closure_sec = 0.0

        # Bâillements (suivi externe, mis à jour via update())
        self.yawn_count = 0

        # Baissement de regard (suivi externe)
        self.gaze_down = False
        self.gaze_down_count = 0

        # Stats
        self.perclos = 0.0
        self.level = self.LEVEL_NORMAL
        self.consecutive_closed_sec = 0.0

    # ── Mise à jour ──────────────────────────────────────────────────
    def update(self, eyes_closed: bool, timestamp=None, yawn_count=0,
               gaze_down=False, gaze_down_count=0):
        """
        Appelée à chaque frame.

        Args:
            eyes_closed     : True si les yeux sont fermés
            timestamp        : time.time() (auto si omis)
            yawn_count       : nombre cumulé de bâillements détectés
            gaze_down        : True si le regard est baissé maintenant
            gaze_down_count  : nombre d'épisodes de baissement

        Returns:
            (level, perclos, consecutive_closed_sec)
        """
        now = timestamp or time.time()
        self.yawn_count = yawn_count
        self.gaze_down = gaze_down
        self.gaze_down_count = gaze_down_count

        # Ajouter à l'historique
        self._history.append((now, eyes_closed))

        # Élaguer la fenêtre
        cutoff = now - self.window_sec
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        # ── Calcul PERCLOS ───────────────────────────────────────────
        if len(self._history) > 1:
            total_closed = 0.0
            total_time = 0.0
            prev_t, prev_closed = self._history[0]
            for t, closed in list(self._history)[1:]:
                dt = t - prev_t
                total_time += dt
                if prev_closed:
                    total_closed += dt
                prev_t, prev_closed = t, closed

            self.perclos = total_closed / total_time if total_time > 0 else 0.0
        else:
            self.perclos = 0.0

        # ── Suivi microsommeil (fermeture continue) ──────────────────
        if eyes_closed:
            if self._last_closed_start is None:
                self._last_closed_start = now
            self.consecutive_closed_sec = now - self._last_closed_start
        else:
            self._last_closed_start = None
            self.consecutive_closed_sec = 0.0

        # ── Déterminer le niveau d'alerte ────────────────────────────
        if self.consecutive_closed_sec >= self.microsleep_sec:
            self.level = self.LEVEL_MICRO
        elif self.perclos >= self.alert_threshold:
            self.level = self.LEVEL_ALERT
        elif (self.perclos >= self.warn_threshold or
              self.yawn_count >= config.YAWN_WARN_COUNT or
              self.gaze_down or
              self.gaze_down_count >= config.GAZE_DOWN_WARN_COUNT):
            self.level = self.LEVEL_WARNING
        else:
            self.level = self.LEVEL_NORMAL

        return self.level, self.perclos, self.consecutive_closed_sec

    # ── Utilitaires ──────────────────────────────────────────────────
    @property
    def level_name(self):
        return self.LEVEL_NAMES.get(self.level, "?")

    @property
    def is_fatigued(self):
        return self.level >= self.LEVEL_WARNING

    def reset(self):
        self._history.clear()
        self._last_closed_start = None
        self.perclos = 0.0
        self.level = self.LEVEL_NORMAL
        self.consecutive_closed_sec = 0.0
