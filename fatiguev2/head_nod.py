"""
Head Nod Detector — Détection de hochements de tête (somnolence).

Le conducteur somnolant "pique du nez" : la tête descend rapidement
puis remonte par sursaut. Ce pattern descente+retour est détecté via
le décalage vertical du centre du bbox visage par rapport à la
baseline calibrée, normalisé par la hauteur du visage.

Deux types d'événements :
  • Nod (0.3–3 s)  : descente brève + retour → compteur incrémenté
  • Microsommeil (>3 s) : tête basse prolongée → alerte immédiate

Coût d'inférence : ZÉRO (utilise uniquement le bbox déjà détecté).
"""
import time
import numpy as np
import config


class HeadNodDetector:
    """Machine à 3 états : IDLE → HEAD_DOWN → COOLDOWN."""

    # États
    IDLE      = 0
    HEAD_DOWN = 1
    COOLDOWN  = 2

    def __init__(self):
        self.baseline_y = None       # position Y calibrée ("éveillé")
        self.smoothed_y = None       # position Y lissée courante
        self.state = self.IDLE
        self.down_since = None       # timestamp début descente
        self.cooldown_until = 0.0
        self.nod_events = []         # timestamps des nods confirmés
        self.is_microsleep = False   # tête basse > seuil continu
        self._face_h_avg = 0.15     # hauteur visage moyenne (ratio)
        self._calib_samples = []
        self._no_face_count = 0

    # ── Calibration ──────────────────────────────────────────────────

    def add_calibration_sample(self, face_box, frame_h):
        """Ajoute un échantillon pendant la phase de calibration."""
        if face_box is None:
            return
        cy = (face_box[1] + face_box[3]) / 2.0 / frame_h
        fh = (face_box[3] - face_box[1]) / frame_h
        self._calib_samples.append((cy, fh))

    def finalize_baseline(self):
        """Calcule la baseline à partir des échantillons de calibration."""
        n = len(self._calib_samples)
        if n >= config.CALIBRATION_MIN_SAMPLES:
            ys = [s[0] for s in self._calib_samples]
            fhs = [s[1] for s in self._calib_samples]
            self.baseline_y = float(np.median(ys))
            self._face_h_avg = float(np.median(fhs))
            print(f"[NOD] Baseline Y = {self.baseline_y:.3f}, "
                  f"face_h = {self._face_h_avg:.3f} ({n} échantillons)")
            return True
        else:
            print(f"[NOD] Pas assez d'échantillons ({n}) → head nod désactivé")
            self.baseline_y = None
            return False

    # ── Mise à jour par frame ────────────────────────────────────────

    def update(self, face_box, frame_h):
        """
        Met à jour l'état à partir du bbox visage courant.
        Appeler à chaque frame, même si face_box est None.
        """
        now = time.time()
        self.is_microsleep = False

        # ── Pas de visage ────────────────────────────────────────────
        if face_box is None:
            self._no_face_count += 1
            # Si on était tête basse et qu'on perd le visage → microsommeil
            if self.state == self.HEAD_DOWN and self.down_since:
                dt = now - self.down_since
                if dt > config.NOD_MICROSLEEP_SEC:
                    self.is_microsleep = True
            # Reset après absence prolongée
            if self._no_face_count > 150:  # ~30s @ 5fps
                self._reset_state()
            return

        self._no_face_count = 0

        # Baseline pas encore calibrée
        if self.baseline_y is None:
            return

        # ── Position normalisée + lissage ────────────────────────────
        cy = (face_box[1] + face_box[3]) / 2.0 / frame_h
        face_h = (face_box[3] - face_box[1]) / frame_h
        if face_h < 0.02:
            return

        # Mise à jour moyenne glissante hauteur visage
        self._face_h_avg = 0.95 * self._face_h_avg + 0.05 * face_h

        if self.smoothed_y is None:
            self.smoothed_y = cy
        else:
            a = config.NOD_SMOOTH_ALPHA
            self.smoothed_y = a * cy + (1.0 - a) * self.smoothed_y

        # Déviation normalisée (positif = tête plus basse que baseline)
        deviation = (self.smoothed_y - self.baseline_y) / self._face_h_avg
        head_is_down = deviation > config.NOD_DOWN_THRESHOLD

        # ── Machine à états ──────────────────────────────────────────
        if self.state == self.IDLE:
            if head_is_down:
                self.state = self.HEAD_DOWN
                self.down_since = now

        elif self.state == self.HEAD_DOWN:
            dt = now - self.down_since
            if not head_is_down:
                # Tête remontée → nod si durée dans la plage attendue
                if config.NOD_MIN_DURATION <= dt <= config.NOD_MAX_DURATION:
                    self.nod_events.append(now)
                    print(f"[NOD] Hochement détecté ({dt:.1f}s) "
                          f"— total fenêtre: {self.nod_count}")
                self.state = self.COOLDOWN
                self.cooldown_until = now + config.NOD_COOLDOWN
                self.down_since = None
            else:
                # Tête toujours basse → microsommeil si > seuil
                self.is_microsleep = (dt > config.NOD_MICROSLEEP_SEC)

        elif self.state == self.COOLDOWN:
            if now >= self.cooldown_until:
                self.state = self.IDLE

        # Nettoyer les vieux événements hors fenêtre
        cutoff = now - config.NOD_WINDOW_SEC
        self.nod_events = [t for t in self.nod_events if t > cutoff]

    # ── Propriétés ───────────────────────────────────────────────────

    @property
    def nod_count(self):
        """Nombre de nods dans la fenêtre glissante."""
        cutoff = time.time() - config.NOD_WINDOW_SEC
        return sum(1 for t in self.nod_events if t > cutoff)

    @property
    def head_down_duration(self):
        """Durée de la descente en cours (0 si tête haute)."""
        if self.down_since is None:
            return 0.0
        return time.time() - self.down_since

    @property
    def deviation(self):
        """Déviation normalisée actuelle (pour affichage)."""
        if self.smoothed_y is None or self.baseline_y is None:
            return 0.0
        return (self.smoothed_y - self.baseline_y) / max(self._face_h_avg, 0.01)

    @property
    def state_name(self):
        return {self.IDLE: "IDLE", self.HEAD_DOWN: "DOWN",
                self.COOLDOWN: "COOL"}[self.state]

    def _reset_state(self):
        self.state = self.IDLE
        self.down_since = None
        self.is_microsleep = False
        self.smoothed_y = None

    def reset(self):
        """Reset complet (sans toucher à la baseline)."""
        self.nod_events.clear()
        self._reset_state()
