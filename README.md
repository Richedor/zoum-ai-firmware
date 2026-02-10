# Détection de fatigue embarquée — Pi Zero 2 W

Système de détection de fatigue **plug-and-play** pour véhicule, basé sur :

- **Raspberry Pi Zero 2 W** (4 cœurs ARM Cortex-A53)
- **IMX219 IR** caméra infrarouge, FOV 160°
- **Raspberry Pi OS Legacy 32-bit** (Bullseye)

**Aucun ré-entraînement nécessaire** — modèles pré-entraînés téléchargés automatiquement.

---

## Architecture

```
Caméra IMX219 IR (160°)
         │
    ┌────▼─────┐
    │  Capture  │ 640×480 → center-crop 65% → 416×312
    └────┬─────┘
         │
    ┌────▼──────────────┐
    │ UltraFace (NCNN)  │ 320×240 — détection visage (~1 MB)
    └────┬──────────────┘
         │ bbox visage
    ┌────▼──────────────┐
    │ Heuristique ROI   │ zone haute du visage → 2 crops yeux
    └────┬──────────────┘
         │
    ┌────▼──────────────┐
    │  OCEC (ONNX/DNN)  │ 24×40 — classification ouvert/fermé (112 KB)
    └────┬──────────────┘
         │ prob_open
    ┌────▼──────────────┐
    │ PERCLOS + micro-  │ fenêtre 60s + fermeture continue
    │ sommeil           │
    └────┬──────────────┘
         │
    ┌────▼──────┐
    │  Alerte   │ buzzer GPIO + affichage
    └───────────┘
```

## Modèles utilisés

| Modèle | Taille | Tâche | Source |
|--------|--------|-------|--------|
| **UltraFace slim-320** | ~1 MB | Détection visage | [Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB](https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB) |
| **OCEC P** | 112 KB | Yeux ouverts/fermés | [PINTO0309/OCEC](https://github.com/PINTO0309/OCEC) |

## Performance attendue

Sur Pi Zero 2 W avec `num_threads=4`, center-crop 65%, inférence 320×240 :

- **~6–15 FPS** (UltraFace NCNN + OCEC OpenCV DNN)
- Latence détection : ~35 ms/frame (face) + ~1 ms (yeux)

> **Clé de la performance :** le center-crop du FOV 160° réduit considérablement la zone à traiter et améliore la précision.

---

## Installation rapide

### Sur le Raspberry Pi

```bash
git clone <ce-repo> ~/fatigue
cd ~/fatigue
chmod +x setup.sh
./setup.sh
```

### Installation manuelle

```bash
# 1. Environnement virtuel
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# 2. Dépendances
pip install numpy opencv-python-headless

# 3. NCNN (optionnel mais recommandé — fallback sur OpenCV DNN)
pip install ncnn

# 4. Télécharger les modèles
python download_models.py

# 5. Lancer
python main.py
```

---

## Utilisation

```bash
# Caméra en direct (par défaut)
python main.py

# Fichier vidéo de test
python main.py --source video.mp4

# Mode headless (sans écran, alertes buzzer uniquement)
python main.py --no-display

# Sans buzzer (test sur PC)
python main.py --no-buzzer

# Combiné
python main.py --source 0 --no-display
```

### Raccourcis clavier (mode affichage)

| Touche | Action |
|--------|--------|
| `q` / `Esc` | Quitter |
| `r` | Réinitialiser le PERCLOS |

---

## Configuration

Tous les paramètres sont dans [`config.py`](config.py) :

### Caméra & FOV
```python
CAPTURE_WIDTH     = 640
CAPTURE_HEIGHT    = 480
CENTER_CROP_RATIO = 0.65    # Garder 65% au centre (correction 160° FOV)
```

### Seuils de fatigue
```python
PERCLOS_WINDOW_SEC       = 60.0   # Fenêtre PERCLOS (secondes)
PERCLOS_WARN_THRESHOLD   = 0.15   # ≥15% → avertissement
PERCLOS_ALERT_THRESHOLD  = 0.30   # ≥30% → alerte critique
MICROSLEEP_THRESHOLD_SEC = 1.5    # Yeux fermés >1.5s → microsommeil
EYE_OPEN_THRESHOLD       = 0.45   # prob_open < 0.45 → fermé
```

### Buzzer GPIO
```python
BUZZER_GPIO_PIN = 17    # Pin BCM du buzzer
BUZZER_FREQ_HZ  = 2000  # Fréquence buzzer passif
```

---

## Câblage du buzzer

```
Pi Zero 2 W          Buzzer passif
──────────────        ─────────────
GPIO 17 (pin 11) ──→ + (signal)
GND     (pin 6)  ──→ - (masse)
```

> Pour un buzzer actif, utilisez simplement `GPIO.output(pin, HIGH/LOW)`.
> Le code utilise PWM pour un buzzer passif (contrôle de fréquence).

---

## Structure du projet

```
fatigue/
├── main.py              # Pipeline principal
├── config.py            # Configuration centralisée
├── camera.py            # Capture caméra + center-crop FOV
├── face_detector.py     # UltraFace (NCNN + fallback OpenCV DNN)
├── eye_classifier.py    # OCEC classification yeux (OpenCV DNN)
├── fatigue_monitor.py   # PERCLOS + microsommeil
├── alert.py             # Alertes GPIO buzzer + console
├── download_models.py   # Téléchargement automatique des modèles
├── setup.sh             # Script d'installation complet (Pi)
├── convert_ocec.sh      # Conversion OCEC ONNX → NCNN (optionnel)
├── requirements.txt     # Dépendances Python
├── models/              # Modèles téléchargés
│   ├── slim_320.param   # UltraFace NCNN
│   ├── slim_320.bin     # UltraFace NCNN
│   └── ocec_p.onnx      # OCEC yeux
└── README.md            # Ce fichier
```

---

## Algorithme PERCLOS

Le **PERCLOS** (PERcentage of eye CLOSure) mesure la proportion de temps où les yeux sont fermés sur une fenêtre glissante :

$$\text{PERCLOS} = \frac{\sum \Delta t_{\text{fermé}}}{\text{fenêtre (60s)}}$$

| PERCLOS | État |
|---------|------|
| < 15% | Normal |
| 15–30% | Somnolence légère (avertissement) |
| ≥ 30% | Fatigue sévère (alerte) |

En parallèle, la **fermeture continue** > 1.5s déclenche une alerte **microsommeil** immédiate.

---

## Conversion OCEC ONNX → NCNN (optionnel)

Si vous voulez exécuter OCEC aussi via NCNN (au lieu d'OpenCV DNN) :

```bash
# 1. Compiler ncnn avec les outils
git clone https://github.com/Tencent/ncnn.git
cd ncnn && mkdir build && cd build
cmake -DNCNN_BUILD_TOOLS=ON -DNCNN_BUILD_EXAMPLES=OFF ..
make -j4

# 2. Convertir
./tools/onnx/onnx2ncnn ../../fatigue/models/ocec_p.onnx \
                        ../../fatigue/models/ocec_p.param \
                        ../../fatigue/models/ocec_p.bin
```

---

## Variantes OCEC disponibles

Pour télécharger toutes les variantes (du plus léger au plus précis) :

```bash
python download_models.py --all-ocec
```

| Variante | Taille | F1 Score | Latence (ref) |
|----------|--------|----------|---------------|
| **P** (défaut) | 112 KB | 0.9924 | 0.16 ms |
| N | 176 KB | 0.9933 | 0.25 ms |
| S | 494 KB | 0.9943 | 0.41 ms |
| C | 875 KB | 0.9947 | 0.49 ms |
| M | 1.7 MB | 0.9949 | 0.57 ms |
| L | 6.4 MB | 0.9954 | 0.80 ms |

Pour utiliser une autre variante, modifiez `config.py` :
```python
OCEC_ONNX = os.path.join(MODELS_DIR, "ocec_n.onnx")  # ou ocec_s, ocec_c, etc.
```

---

## Backends supportés

| Composant | Primaire | Fallback |
|-----------|----------|----------|
| Détection visage | **ncnn** (PyPI) | OpenCV DNN (ONNX) |
| Classification yeux | **OpenCV DNN** (ONNX) | onnxruntime |
| Capture caméra | **Picamera2** (libcamera) | OpenCV VideoCapture |
| Alertes | **RPi.GPIO** (buzzer) | Console |

Le système détecte automatiquement les backends disponibles et utilise le meilleur.

---

## Dépannage

### La caméra ne démarre pas
```bash
# Vérifier la détection
vcgencmd get_camera
# ou
libcamera-hello --timeout 1000
```

### FPS trop bas
- Vérifiez que `CENTER_CROP_RATIO` est bien < 1.0 (0.65 recommandé)
- Réduisez `CAPTURE_WIDTH` à 640 (pas de 720p/1080p)
- Utilisez le backend NCNN (plus rapide que OpenCV DNN)
- Vérifiez `NUM_THREADS = 4` dans config.py

### ncnn ne s'installe pas via pip
```bash
# Alternative : compiler depuis les sources
git clone https://github.com/Tencent/ncnn.git
cd ncnn && mkdir build && cd build
cmake -DNCNN_BUILD_TOOLS=ON ..
make -j4 && sudo make install
cd ../python && pip install .
```

### Fausses alertes
- Augmentez `EYE_OPEN_THRESHOLD` (ex: 0.50 → 0.55)
- Augmentez `PERCLOS_WARN_THRESHOLD` (ex: 0.15 → 0.20)
- Augmentez `MICROSLEEP_THRESHOLD_SEC` (ex: 1.5 → 2.0)

---

## Licences

- UltraFace : [MIT License](https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB/blob/master/LICENSE)
- OCEC : [MIT License](https://github.com/PINTO0309/OCEC/blob/main/LICENSE)
- ncnn : [BSD 3-Clause](https://github.com/Tencent/ncnn/blob/master/LICENSE.txt)
