#!/bin/bash
# ============================================================
#  convert_ocec.sh — Conversion OCEC ONNX → NCNN
#
#  Prérequis : ncnn compilé avec les outils (onnx2ncnn)
#  Si vous n'avez pas onnx2ncnn, installez ncnn depuis les sources :
#    git clone https://github.com/Tencent/ncnn.git
#    cd ncnn && mkdir build && cd build
#    cmake -DNCNN_BUILD_TOOLS=ON ..
#    make -j4
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/models"

# Chercher onnx2ncnn
ONNX2NCNN=""
if command -v onnx2ncnn &>/dev/null; then
    ONNX2NCNN="onnx2ncnn"
elif [ -f "${HOME}/ncnn/build/tools/onnx/onnx2ncnn" ]; then
    ONNX2NCNN="${HOME}/ncnn/build/tools/onnx/onnx2ncnn"
elif [ -f "/usr/local/bin/onnx2ncnn" ]; then
    ONNX2NCNN="/usr/local/bin/onnx2ncnn"
else
    echo "❌ onnx2ncnn non trouvé !"
    echo ""
    echo "Pour compiler ncnn avec les outils de conversion :"
    echo "  git clone https://github.com/Tencent/ncnn.git"
    echo "  cd ncnn && mkdir build && cd build"
    echo "  cmake -DNCNN_BUILD_TOOLS=ON -DNCNN_BUILD_EXAMPLES=OFF .."
    echo "  make -j4"
    echo ""
    echo "Puis relancez ce script."
    exit 1
fi

echo "Outil trouvé : ${ONNX2NCNN}"
echo ""

# Convertir tous les modèles OCEC ONNX présents
for onnx_file in "${MODELS_DIR}"/ocec_*.onnx; do
    if [ ! -f "$onnx_file" ]; then
        echo "Aucun fichier OCEC ONNX trouvé dans ${MODELS_DIR}"
        echo "Lancez d'abord : python download_models.py"
        exit 1
    fi

    base=$(basename "$onnx_file" .onnx)
    param_file="${MODELS_DIR}/${base}.param"
    bin_file="${MODELS_DIR}/${base}.bin"

    if [ -f "$param_file" ] && [ -f "$bin_file" ]; then
        echo "✓ ${base} déjà converti"
        continue
    fi

    echo "→ Conversion ${base}.onnx → NCNN..."
    "${ONNX2NCNN}" "$onnx_file" "$param_file" "$bin_file"
    echo "✓ ${param_file}"
    echo "✓ ${bin_file}"
    echo ""
done

echo ""
echo "✓ Conversion terminée !"
echo ""
echo "Pour utiliser OCEC via NCNN au lieu d'OpenCV DNN :"
echo "  Modifiez config.py → OCEC_ONNX → chemin vers .param/.bin"
echo "  (nécessite d'adapter eye_classifier.py pour le backend ncnn)"
