"""
Module de surveillance du baissement de regard.

Principe (sans modèle supplémentaire) :
  - Pendant la calibration, on enregistre la position Y normale
    du centre du visage et sa hauteur (en coordonnées normalisées).
  - En fonctionnement, on mesure le décalage vertical du centre
    du visage par rapport à la baseline.
  - Un décalage vers le bas > seuil (en % de la hauteur de visage)
    maintenu pendant plus de N secondes → baissement de regard.

Indicateurs :
  - Baissement prolongé = signe de somnolence (tête qui tombe)
  - Baissements fréquents = signe de distraction (téléphone, etc.)

Avantages :
  - Aucun modèle supplémentaire requis
  - Utilise uniquement les coordonnées de la bbox visage
  - Très léger en calcul
"""
import time
import numpy as np

import config


class GazeMonitor:
    """Détection du baissement de regard via position verticale du visage."""

    def __init__(self):
        # Baseline calibrée (coordonnées normalisées [0..1])
        self.baseline_y = None       # centre Y normal du visage
        self.baseline_h = None       # hauteur normale du visage

        # Tampons de calibration
        self._cal_y = []
        self._cal_h = []

        # État courant
        self._down_start = None      # timestamp début du baissement
        self.is_looking_down = False
        self.down_duration = 0.0     # durée du baissement actuel (s)
        self.down_count = 0          # nombre d'épisodes détectés
        self.deviation = 0.0         # déviation actuelle (pour affichage)

        # Lissage (moyenne glissante sur N frames)
        self._history_y = []
        self._smooth_n = 5

    # ── Calibration ──────────────────────────────────────────────────
    def update_baseline(self, face_box, frame_h):
        """Collecte un échantillon de position pendant la calibration.

        Args:
            face_box : détection visage [x1, y1, x2, y2, score]
            frame_h  : hauteur de la frame en pixels
        """
        cy = (face_box[1] + face_box[3]) / 2.0 / frame_h
        fh = (face_box[3] - face_box[1]) / frame_h
        self._cal_y.append(cy)
        self._cal_h.append(fh)

    def finalize_baseline(self):
        """Calcule la baseline à partir des échantillons collectés."""
        if len(self._cal_y) >= 5:
            self.baseline_y = float(np.median(self._cal_y))
            self.baseline_h = float(np.median(self._cal_h))
            print(f"[GAZE] Baseline regard : Y={self.baseline_y:.3f}  "
                  f"H={self.baseline_h:.3f} ({len(self._cal_y)} éch.)")
        else:
            self.baseline_y = None
            self.baseline_h = None
            print(f"[GAZE] Pas assez d'échantillons ({len(self._cal_y)}) "
                  f"→ baissement désactivé")
        self._cal_y.clear()
        self._cal_h.clear()

    # ── Mise à jour par frame ────────────────────────────────────────
    def update(self, face_box, frame_h):
        """Met à jour la détection de baissement de regard.

        Args:
            face_box : détection visage [x1, y1, x2, y2, score] ou None
            frame_h  : hauteur de la frame en pixels

        Returns:
            (is_looking_down, down_duration)
        """
        # Pas de baseline → pas de surveillance
        if self.baseline_y is None or self.baseline_h is None:
            return False, 0.0

        # Pas de visage → reset temporaire
        if face_box is None:
            self._down_start = None
            self.is_looking_down = False
            self.down_duration = 0.0
            self._history_y.clear()
            return False, 0.0

        # Position Y courante normalisée
        cy = (face_box[1] + face_box[3]) / 2.0 / frame_h

        # Lissage sur N frames pour robustesse
        self._history_y.append(cy)
        if len(self._history_y) > self._smooth_n:
            self._history_y.pop(0)
        cy_smooth = sum(self._history_y) / len(self._history_y)

        # Déviation normalisée par la hauteur de visage
        # > 0 = regard/tête a baissé, < 0 = monté
        self.deviation = (cy_smooth - self.baseline_y) / self.baseline_h \
            if self.baseline_h > 0 else 0.0

        now = time.time()
        threshold = config.GAZE_DOWN_THRESHOLD

        if self.deviation > threshold:
            # Le regard est en bas
            if self._down_start is None:
                self._down_start = now
            self.down_duration = now - self._down_start

            # Confirmer un épisode de baissement prolongé
            if (self.down_duration >= config.GAZE_DOWN_DURATION_SEC
                    and not self.is_looking_down):
                self.is_looking_down = True
                self.down_count += 1
                print(f"[GAZE] Baissement #{self.down_count} détecté "
                      f"(dév={self.deviation:.2f}, durée={self.down_duration:.1f}s)")
        else:
            # Regard normal
            self._down_start = None
            self.is_looking_down = False
            self.down_duration = 0.0

        return self.is_looking_down, self.down_duration

    # ── Reset ────────────────────────────────────────────────────────
    def reset(self):
        """Réinitialise les compteurs (garde la baseline)."""
        self._down_start = None
        self.is_looking_down = False
        self.down_duration = 0.0
        self.down_count = 0
        self.deviation = 0.0
        self._history_y.clear()
