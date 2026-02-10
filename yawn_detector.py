"""
Détecteur de bâillements — analyse de la zone bouche.

Méthode légère sans modèle supplémentaire :
  1. Extraire le ROI bouche du bbox visage (tiers inférieur, centre)
  2. Mesurer l'intensité moyenne en niveaux de gris
  3. Comparer à la baseline calibrée (bouche fermée)
  4. Si l'intensité chute fortement → bouche ouverte (zone sombre)
  5. Si bouche ouverte > durée min → bâillement confirmé

Utilise l'intensité MOYENNE relative (baseline/courante) :
  ratio > seuil → bouche ouverte.
Robuste aux conditions d'éclairage variables (IR ou visible).
"""
import time
import cv2
import numpy as np
import config


class YawnDetector:
    """Détecte les bâillements par analyse de l'intensité de la zone bouche."""

    def __init__(self):
        # Suivi temporel
        self._mouth_open_start = None
        self._last_yawn_time = 0.0
        self.yawn_count = 0
        self.mouth_open_ratio = 0.0
        self.is_yawning = False

        # Baseline bouche fermée (calibrée au démarrage)
        self._baseline_samples = []
        self._baseline_mean = None
        self._effective_threshold = None  # ratio d'assombrissement

    # ── Extraction ROI bouche ────────────────────────────────────────
    @staticmethod
    def extract_mouth_roi(image, face_box):
        """
        Extrait la zone de la bouche dans le bbox visage.

        Args:
            image   : image BGR complète
            face_box: [x1, y1, x2, y2, score]

        Returns:
            crop BGR de la bouche, ou None
        """
        x1, y1, x2, y2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
        fw = x2 - x1
        fh = y2 - y1
        if fw < 20 or fh < 20:
            return None

        img_h, img_w = image.shape[:2]

        mx1 = max(int(x1 + config.MOUTH_ROI_X1 * fw), 0)
        my1 = max(int(y1 + config.MOUTH_ROI_Y1 * fh), 0)
        mx2 = min(int(x1 + config.MOUTH_ROI_X2 * fw), img_w)
        my2 = min(int(y1 + config.MOUTH_ROI_Y2 * fh), img_h)

        if mx2 <= mx1 or my2 <= my1:
            return None

        return image[my1:my2, mx1:mx2].copy()

    # ── Mesure d'intensité ───────────────────────────────────────────
    @staticmethod
    def _mean_intensity(mouth_bgr):
        """Intensité moyenne en niveaux de gris."""
        if mouth_bgr is None or mouth_bgr.size == 0:
            return -1.0
        gray = cv2.cvtColor(mouth_bgr, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    # ── Calibration baseline ─────────────────────────────────────────
    def update_baseline(self, mouth_bgr):
        """Accumule les intensités bouche fermée pendant la calibration."""
        val = self._mean_intensity(mouth_bgr)
        if val > 0:
            self._baseline_samples.append(val)

    def finalize_baseline(self):
        """Fixe la baseline et le seuil d'ouverture."""
        if len(self._baseline_samples) > 5:
            self._baseline_mean = float(np.median(self._baseline_samples))
            # Bouche ouverte = intensité chute de MOUTH_DROP_RATIO par rapport
            # à la baseline. Ex: baseline=120, ratio=0.30 → seuil à 84.
            self._effective_threshold = self._baseline_mean * (1.0 - config.MOUTH_DROP_RATIO)
            print(f"[YAWN] Baseline bouche : intensité={self._baseline_mean:.1f}, "
                  f"seuil ouverture : <{self._effective_threshold:.1f} "
                  f"(chute de {config.MOUTH_DROP_RATIO:.0%})")
        else:
            self._baseline_mean = None
            self._effective_threshold = None
            print(f"[YAWN] Pas assez d'échantillons ({len(self._baseline_samples)}), "
                  f"bâillements désactivés")
        self._baseline_samples = []  # libérer mémoire

    # ── Mise à jour par frame ────────────────────────────────────────
    def update(self, mouth_bgr, timestamp=None):
        """
        Analyse la zone bouche et détecte les bâillements.

        Args:
            mouth_bgr : crop BGR de la bouche (ou None)
            timestamp : time.time() (auto si omis)

        Returns:
            (is_yawning, yawn_count, mouth_ratio)
        """
        now = timestamp or time.time()
        self.is_yawning = False

        if mouth_bgr is None or self._effective_threshold is None:
            self._mouth_open_start = None
            return False, self.yawn_count, 0.0

        # Mesurer l'intensité courante
        current = self._mean_intensity(mouth_bgr)
        if current < 0:
            self._mouth_open_start = None
            return False, self.yawn_count, 0.0

        # Ratio d'assombrissement relatif (0 = identique à baseline, 1 = noir total)
        if self._baseline_mean > 0:
            self.mouth_open_ratio = max(0.0, 1.0 - current / self._baseline_mean)
        else:
            self.mouth_open_ratio = 0.0

        mouth_open = current < self._effective_threshold

        if mouth_open:
            if self._mouth_open_start is None:
                self._mouth_open_start = now
            duration = now - self._mouth_open_start

            # Bâillement confirmé si durée suffisante + cooldown respecté
            if (duration >= config.YAWN_DURATION_SEC and
                    (now - self._last_yawn_time) >= config.YAWN_COOLDOWN_SEC):
                self.is_yawning = True
                self.yawn_count += 1
                self._last_yawn_time = now
                self._mouth_open_start = None  # reset pour le prochain
                print(f"[YAWN] Bâillement #{self.yawn_count} détecté "
                      f"(intensité={current:.0f}/{self._baseline_mean:.0f}, "
                      f"chute={self.mouth_open_ratio:.0%}, durée={duration:.1f}s)")
        else:
            self._mouth_open_start = None

        return self.is_yawning, self.yawn_count, self.mouth_open_ratio

    def reset(self):
        self._mouth_open_start = None
        self._last_yawn_time = 0.0
        self.yawn_count = 0
        self.mouth_open_ratio = 0.0
        self.is_yawning = False
