"""
Configuration — Fatigue Detection Lite (Head Nod + Yawn).

Version allégée : pas d'OCEC, pas de PERCLOS.
Auto-détecte Pi vs PC → plus besoin d'apply_profile.py.

Réutilise les modèles et modules partagés du répertoire parent :
  camera.py, face_detector.py, yawn_detector.py, alert.py, stream_server.py
"""
import os
import platform

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
MODELS_DIR = os.path.join(PARENT_DIR, "models")

# ─── Auto-détection plateforme ──────────────────────────────────────
_IS_PI = platform.machine() in ("armv6l", "armv7l", "aarch64")

# ─── Chemins modèles (partagés avec v1) ─────────────────────────────
ULTRAFACE_PARAM = os.path.join(MODELS_DIR, "slim_320.param")
ULTRAFACE_BIN   = os.path.join(MODELS_DIR, "slim_320.bin")

# ─── Caméra ─────────────────────────────────────────────────────────
CAMERA_INDEX   = 0
CAPTURE_WIDTH  = 640
CAPTURE_HEIGHT = 480
CAPTURE_FPS    = 30

# ─── IMX219 IR (auto sur Pi) ────────────────────────────────────────
IR_CAMERA        = _IS_PI
IR_AWB_MODE      = 0
IR_COLOUR_GAINS  = (1.4, 2.2)
IR_EXPOSURE_TIME = 30000        # µs
IR_ANALOGUE_GAIN = 4.0

# ─── Correction FOV 160° ────────────────────────────────────────────
CENTER_CROP_RATIO = 0.65 if _IS_PI else 1.0

# ─── Inférence visage ───────────────────────────────────────────────
DETECT_WIDTH         = 320
DETECT_HEIGHT        = 240
FACE_SCORE_THRESHOLD = 0.55 if _IS_PI else 0.50
FACE_IOU_THRESHOLD   = 0.3
FACE_MIN_SIZE        = 35 if _IS_PI else 25
NUM_THREADS          = 4

# ─── Head Nod (hochement de tête / microsommeil) ────────────────────
# Le conducteur somnolant "pique du nez" : la tête descend rapidement
# puis remonte (sursaut). C'est un événement dynamique détecté via
# le décalage vertical du bbox visage par rapport à la baseline.
NOD_SMOOTH_ALPHA   = 0.35       # Lissage EMA position Y (0=lent, 1=brut)
NOD_DOWN_THRESHOLD = 0.12       # Déviation min (× hauteur visage) → "tête basse"
NOD_MIN_DURATION   = 0.3        # Durée min descente pour compter comme nod (s)
NOD_MAX_DURATION   = 3.0        # Au-delà = microsommeil, pas un nod
NOD_COOLDOWN       = 2.0        # Pause entre 2 nods (s)
NOD_MICROSLEEP_SEC = 3.0        # Tête basse continue > 3s → alerte immédiate
NOD_WINDOW_SEC     = 300.0      # Fenêtre glissante comptage nods (5 min)

# ─── Calibration ────────────────────────────────────────────────────
CALIBRATION_SEC    = 5.0        # Durée phase calibration (s)
CALIBRATION_MIN_SAMPLES = 10    # Échantillons min pour valider

# ─── Bâillements (même méthode que v1) ──────────────────────────────
MOUTH_ROI_X1       = 0.20
MOUTH_ROI_X2       = 0.80
MOUTH_ROI_Y1       = 0.62
MOUTH_ROI_Y2       = 0.95
MOUTH_DROP_RATIO   = 0.30       # Chute intensité ≥ 30% → bouche ouverte
YAWN_DURATION_SEC  = 2.5        # Bouche ouverte > 2.5s = bâillement
YAWN_COOLDOWN_SEC  = 10.0
YAWN_WARN_COUNT    = 3          # 3 bâillements → warning

# ─── Fusion / alertes ───────────────────────────────────────────────
NOD_WARN_COUNT     = 2          # Nods en fenêtre → warning
NOD_ALERT_COUNT    = 4          # Nods en fenêtre → alerte

# ─── Alerte GPIO ────────────────────────────────────────────────────
BUZZER_ENABLED     = True
BUZZER_GPIO_PIN    = 17
BUZZER_FREQ_HZ     = 2000

# ─── Affichage / debug ──────────────────────────────────────────────
SHOW_PREVIEW       = True
PRINT_FPS          = True
DRAW_FACE_BOX      = True
DRAW_MOUTH_ROI     = True
