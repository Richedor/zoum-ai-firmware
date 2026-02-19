"""
Configuration pour le système de détection de fatigue embarqué.
Cible : Raspberry Pi Zero 2 W + IMX219 IR (FOV 160°)
"""
import os

# ─── Chemins modèles ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# UltraFace (NCNN) — détection de visage
ULTRAFACE_PARAM = os.path.join(MODELS_DIR, "slim_320.param")
ULTRAFACE_BIN   = os.path.join(MODELS_DIR, "slim_320.bin")

# OCEC — classification yeux ouverts/fermés (ONNX, chargé via OpenCV DNN)
OCEC_ONNX       = os.path.join(MODELS_DIR, "ocec_p.onnx")

# ─── Paramètres caméra ──────────────────────────────────────────────
CAMERA_INDEX      = 0            # /dev/video0 ou index caméra
CAPTURE_WIDTH     = 640          # Résolution de capture
CAPTURE_HEIGHT    = 480
CAPTURE_FPS       = 30
# ─── Réglages IMX219 IR (sans filtre IR) ─────────────────────────
# L'IMX219 IR n'a pas de filtre infrarouge → image rouge/rose.
# On corrige via le white balance manuel et les gains de couleur.
# Désactivé sur PC (IR_CAMERA = False).
IR_CAMERA         = True        # ◄ Pi 160° : True
IR_AWB_MODE       = 0            # 0 = AWB manuel (Custom)
IR_COLOUR_GAINS   = (1.4, 2.2)   # (rouge, bleu) — ajuster selon éclairage
IR_EXPOSURE_TIME   = 15000       # Temps d'exposition en µs (30ms)
IR_ANALOGUE_GAIN   = 8.0         # Gain analogique
# ─── Correction FOV 160° ────────────────────────────────────────────
# Center-crop pour réduire la distorsion barrel du grand angle.
#   Webcam PC standard  → 1.0  (pas de crop)
#   Pi + IMX219 IR 160° → 0.65 (garder 65 % au centre)
CENTER_CROP_RATIO = 0.65          # ◄ Pi 160° : 0.65

# ─── Résolution d'inférence ─────────────────────────────────────────
DETECT_WIDTH  = 320              # Input UltraFace
DETECT_HEIGHT = 240

# ─── Détection de visage ────────────────────────────────────────────
FACE_SCORE_THRESHOLD = 0.65      # ◄ Pi 160° : 0.65
FACE_IOU_THRESHOLD   = 0.3       # NMS IoU
FACE_MIN_SIZE        = 40        # ◄ Pi 160° : 40
NUM_THREADS          = 4         # Threads ncnn (4 cœurs du Zero 2 W)

# ─── Classification yeux (OCEC) ─────────────────────────────────────
OCEC_INPUT_H = 24                # Hauteur entrée OCEC
OCEC_INPUT_W = 40                # Largeur entrée OCEC
EYE_OPEN_THRESHOLD = 0.45        # prob_open < seuil → yeux fermés (par défaut)

# ─── Calibration automatique (paupières naturellement basses) ───────
# Au démarrage, mesure pendant N secondes l'ouverture naturelle du
# conducteur et adapte le seuil : seuil = baseline × RATIO.
# Cela évite les faux positifs pour les personnes au regard tombant.
CALIBRATION_SEC      = 5.0       # Durée de calibration (secondes)
CALIBRATION_RATIO    = 0.40      # Seuil = baseline × ce ratio (tolérant)
CALIBRATION_MIN_THR  = 0.12      # Seuil plancher (sécurité)
CALIBRATION_MAX_THR  = 0.38      # Seuil plafond

# ─── Heuristique ROI yeux (sans landmarks) ──────────────────────────
# Coordonnées relatives dans le bounding box du visage [0..1]
# Resserré sur la zone oculaire — évite de capturer sourcils/tempes.
# Œil gauche (du point de vue de la caméra = œil droit de la personne)
EYE_LEFT_X1  = 0.08
EYE_LEFT_X2  = 0.48
EYE_LEFT_Y1  = 0.22
EYE_LEFT_Y2  = 0.48

# Œil droit (du point de vue de la caméra = œil gauche de la personne)
EYE_RIGHT_X1 = 0.52
EYE_RIGHT_X2 = 0.92
EYE_RIGHT_Y1 = 0.22
EYE_RIGHT_Y2 = 0.48

# ─── Détection bâillements (sans modèle supplémentaire) ─────────────
# Analyse de la chute d'intensité dans la zone bouche.
# Bouche ouverte = zone sombre → intensité moyenne chute.
# Calibré automatiquement au démarrage (baseline bouche fermée).
MOUTH_ROI_X1 = 0.20             # Zone bouche relative au bbox visage
MOUTH_ROI_X2 = 0.80
MOUTH_ROI_Y1 = 0.62
MOUTH_ROI_Y2 = 0.95
MOUTH_DROP_RATIO     = 0.30     # Chute d'intensité ≥ 30 % → bouche ouverte
YAWN_DURATION_SEC    = 2.5      # Bouche ouverte > 2.5 s = bâillement
YAWN_COOLDOWN_SEC    = 10.0     # Pause minimale entre 2 bâillements
YAWN_WARN_COUNT      = 3        # Nombre de bâillements → avertissement

# ─── Baissement de regard (sans modèle supplémentaire) ──────────────
# Détecte quand la tête/regard du conducteur baisse durablement.
# Utilise uniquement le décalage vertical du centre de la bbox visage
# par rapport à la position calibrée, normalisé par la hauteur du visage.
# Ex : déviation 0.15 = le centre du visage a baissé de 15 % de sa hauteur.
GAZE_DOWN_THRESHOLD   = 0.15    # Déviation minimale pour "regard bas"
GAZE_DOWN_DURATION_SEC = 3.0    # Durée continue (s) avant alerte
GAZE_DOWN_WARN_COUNT  = 3       # Nb épisodes → avertissement complémentaire
DRAW_GAZE_INFO        = True    # Afficher la déviation sur l'overlay

# ─── PERCLOS & alertes fatigue ──────────────────────────────────────
PERCLOS_WINDOW_SEC       = 60.0  # Fenêtre glissante PERCLOS (secondes)
PERCLOS_WARN_THRESHOLD   = 0.30  # PERCLOS ≥ 30 % → avertissement
PERCLOS_ALERT_THRESHOLD  = 0.50  # PERCLOS ≥ 50 % → alerte critique

# Microsommeil : yeux fermés en continu > X secondes
MICROSLEEP_THRESHOLD_SEC = 3.5   # 3.5 s yeux fermés → alerte immédiate

# ─── Alerte matérielle (GPIO buzzer) ────────────────────────────────
BUZZER_ENABLED  = True
BUZZER_GPIO_PIN = 17             # BCM pin
BUZZER_FREQ_HZ  = 2000          # Fréquence buzzer passif

# ─── Affichage / debug ──────────────────────────────────────────────
SHOW_PREVIEW     = True          # Afficher la fenêtre OpenCV (False en headless)
DRAW_FACE_BOX    = True
DRAW_EYE_ROIS    = True
DRAW_MOUTH_ROI   = True
PRINT_FPS        = True
LOG_FILE         = os.path.join(BASE_DIR, "fatigue.log")
