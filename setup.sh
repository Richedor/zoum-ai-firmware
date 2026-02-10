#!/bin/bash
# ============================================================
#  setup.sh — Installation complète sur Raspberry Pi Zero 2 W
#  Compatible Bullseye et Bookworm (32-bit / 64-bit)
# ============================================================
set -e

echo "============================================================"
echo "  Setup — Détection de fatigue Pi Zero 2 W + IMX219 IR 160°"
echo "============================================================"

# ── 1. Dépendances système ──────────────────────────────────────────
echo ""
echo "[1/6] Installation des dépendances système..."
sudo apt-get update
sudo apt-get install -y \
    python3-venv python3-pip python3-dev \
    libopencv-dev python3-opencv \
    libatlas-base-dev \
    libhdf5-dev \
    cmake build-essential \
    git wget curl

# ── 2. Activer la caméra ────────────────────────────────────────────
echo ""
echo "[2/6] Vérification de la caméra..."
if ! grep -q "^start_x=1" /boot/config.txt 2>/dev/null; then
    echo "  ⚠ Caméra peut ne pas être activée."
    echo "  Exécutez : sudo raspi-config → Interface Options → Camera → Enable"
    echo "  Ou ajoutez 'start_x=1' et 'gpu_mem=128' dans /boot/config.txt"
fi

# Vérifier si libcamera fonctionne (Pi OS Bullseye+)
if command -v libcamera-hello &>/dev/null; then
    echo "  ✓ libcamera disponible"
elif command -v raspistill &>/dev/null; then
    echo "  ✓ raspistill disponible (legacy)"
else
    echo "  ⚠ Aucun outil caméra détecté. Installez libcamera-apps ou activez la caméra."
fi

# ── 3. Environnement Python ─────────────────────────────────────────
echo ""
echo "[3/6] Création de l'environnement Python..."
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  ✓ venv créé"
else
    echo "  ✓ venv existant"
fi

source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# ── 4. Packages Python ──────────────────────────────────────────────
echo ""
echo "[4/6] Installation des packages Python..."

# OpenCV (utiliser le paquet système si disponible, sinon pip)
pip install numpy

# Essayer le package système python3-opencv d'abord (plus rapide, pré-compilé)
python3 -c "import cv2; print(f'  ✓ OpenCV {cv2.__version__} (système)')" 2>/dev/null || {
    echo "  Installation opencv-python-headless via pip (peut prendre du temps sur Pi)..."
    pip install opencv-python-headless
}

# ncnn Python — essayer d'installer, optionnel
echo "  Tentative d'installation ncnn (optionnel)..."
pip install ncnn 2>/dev/null && echo "  ✓ ncnn installé" || {
    echo "  ⚠ ncnn non disponible via pip, utilisation du fallback OpenCV DNN"
    echo "    Pour compiler ncnn depuis les sources :"
    echo "    git clone https://github.com/Tencent/ncnn.git && cd ncnn"
    echo "    mkdir build && cd build"
    echo "    cmake -DNCNN_BUILD_TOOLS=ON -DNCNN_BUILD_EXAMPLES=OFF .."
    echo "    make -j4 && sudo make install"
    echo "    cd ../python && pip install ."
}

# Picamera2 (optionnel, pour caméra native Pi)
pip install picamera2 2>/dev/null && echo "  ✓ picamera2 installé" || {
    echo "  ⚠ picamera2 non installé (utilisation d'OpenCV VideoCapture)"
}

# ── 5. Téléchargement des modèles ──────────────────────────────────
echo ""
echo "[5/6] Téléchargement des modèles pré-entraînés..."
python download_models.py

# ── 6. Appliquer le profil Pi ──────────────────────────────────────
echo ""
echo "[6/6] Application du profil Pi (config.py)..."
python apply_profile.py pi

echo ""
echo "============================================================"
echo "  ✓ Installation terminée !"
echo ""
echo "  Pour lancer :"
echo "    source .venv/bin/activate"
echo "    python main.py"
echo ""
echo "  Options :"
echo "    python main.py --source video.mp4    # test vidéo"
echo "    python main.py --no-display          # sans écran"
echo "    python main.py --no-buzzer           # sans buzzer"
echo "============================================================"
