"""
Module caméra — capture + center-crop (correction FOV 160°).

Supporte :
  1. Picamera2 (natif libcamera, recommandé sur Pi)
  2. OpenCV VideoCapture (fallback universel)
"""
import cv2
import numpy as np
import config

# ─── Tentative d'import Picamera2 ───────────────────────────────────
_PICAMERA2 = False
try:
    from picamera2 import Picamera2  # type: ignore
    _PICAMERA2 = True
except ImportError:
    pass


class Camera:
    """Source vidéo avec center-crop automatique pour objectif grand angle."""

    def __init__(
        self,
        source=None,
        width=None,
        height=None,
        fps=None,
        crop_ratio=None,
    ):
        self.source = source if source is not None else config.CAMERA_INDEX
        self.cap_w = width or config.CAPTURE_WIDTH
        self.cap_h = height or config.CAPTURE_HEIGHT
        self.fps = fps or config.CAPTURE_FPS
        self.crop_ratio = crop_ratio if crop_ratio is not None else config.CENTER_CROP_RATIO
        self._picam = None
        self._cv_cap = None

        if isinstance(self.source, int) and _PICAMERA2:
            self._init_picamera2()
        else:
            self._init_opencv()

    # ── Initialisation Picamera2 ─────────────────────────────────────
    def _init_picamera2(self):
        self._picam = Picamera2()
        cam_config = self._picam.create_preview_configuration(
            main={"format": "RGB888", "size": (self.cap_w, self.cap_h)},
            controls={"FrameRate": self.fps},
        )
        self._picam.configure(cam_config)
        self._picam.start()
        print(f"[CAM] Picamera2 démarrée : {self.cap_w}x{self.cap_h} @ {self.fps} fps")

    # ── Initialisation OpenCV ────────────────────────────────────────
    def _init_opencv(self):
        self._cv_cap = cv2.VideoCapture(self.source)
        if isinstance(self.source, int):
            self._cv_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cap_w)
            self._cv_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cap_h)
            self._cv_cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not self._cv_cap.isOpened():
            raise RuntimeError(f"[CAM] Impossible d'ouvrir la source vidéo : {self.source}")
        actual_w = int(self._cv_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cv_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[CAM] OpenCV capture : {actual_w}x{actual_h}")

    # ── Lecture d'une frame ──────────────────────────────────────────
    def read(self):
        """
        Retourne (ok, frame_bgr) avec le center-crop appliqué.
        frame_bgr est en BGR (convention OpenCV).
        """
        frame = None
        if self._picam is not None:
            frame = self._picam.capture_array()
            # Picamera2 retourne RGB → convertir en BGR pour cohérence OpenCV
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif self._cv_cap is not None:
            ok, frame = self._cv_cap.read()
            if not ok or frame is None:
                return False, None
        else:
            return False, None

        # Center-crop
        if 0.0 < self.crop_ratio < 1.0:
            frame = self._center_crop(frame, self.crop_ratio)

        return True, frame

    # ── Center-crop ──────────────────────────────────────────────────
    @staticmethod
    def _center_crop(image, ratio):
        """Garde `ratio` (0..1) de l'image au centre."""
        h, w = image.shape[:2]
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        x1 = (w - new_w) // 2
        y1 = (h - new_h) // 2
        return image[y1 : y1 + new_h, x1 : x1 + new_w].copy()

    # ── Nettoyage ────────────────────────────────────────────────────
    def release(self):
        if self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                pass
        if self._cv_cap is not None:
            self._cv_cap.release()

    def __del__(self):
        self.release()
