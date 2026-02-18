"""
Fusion temporelle — combine head nods + bâillements en niveaux d'alerte.

Logique de fusion :
  NORMAL  : rien à signaler
  WARNING : nods ≥ 2 (en 5 min) OU bâillements ≥ 3
  ALERTE  : microsommeil OU nods ≥ 4 OU (nods ≥ 1 + bâillements ≥ 3)
"""
import config


class FatigueFusion:
    LEVEL_NORMAL  = 0
    LEVEL_WARNING = 1
    LEVEL_ALERT   = 2

    LEVEL_NAMES = {0: "NORMAL", 1: "ATTENTION", 2: "ALERTE"}

    def __init__(self):
        self.level = self.LEVEL_NORMAL
        self.level_name = "NORMAL"

    def update(self, nod_count, is_microsleep, head_down_sec, yawn_count):
        """
        Calcule le niveau d'alerte courant.

        Args:
            nod_count      : nombre de nods dans la fenêtre glissante
            is_microsleep  : True si tête basse depuis > NOD_MICROSLEEP_SEC
            head_down_sec  : durée de la descente en cours (s)
            yawn_count     : nombre total de bâillements

        Returns:
            (level, nod_count, head_down_sec)
        """
        level = self.LEVEL_NORMAL

        # ── Microsommeil → alerte immédiate ──────────────────────────
        if is_microsleep:
            level = self.LEVEL_ALERT

        # ── Nods accumulés ───────────────────────────────────────────
        elif nod_count >= config.NOD_ALERT_COUNT:
            level = self.LEVEL_ALERT
        elif nod_count >= config.NOD_WARN_COUNT:
            level = max(level, self.LEVEL_WARNING)

        # ── Bâillements ──────────────────────────────────────────────
        if yawn_count >= config.YAWN_WARN_COUNT:
            level = max(level, self.LEVEL_WARNING)
            # Combo nods + bâillements → alerte
            if nod_count >= 1:
                level = self.LEVEL_ALERT

        self.level = level
        self.level_name = self.LEVEL_NAMES[level]
        return level, nod_count, head_down_sec

    def reset(self):
        self.level = self.LEVEL_NORMAL
        self.level_name = "NORMAL"
