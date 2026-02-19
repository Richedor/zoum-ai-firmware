#!/usr/bin/env python3
"""
Téléchargement automatique des modèles pré-entraînés.

Modèles téléchargés :
  1. UltraFace slim-320 (NCNN .param + .bin) — détection visage 1 MB
  2. OCEC ocec_p.onnx — classification yeux ouverts/fermés 112 KB
"""
import os
import sys
import hashlib
import urllib.request

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# ─── URLs des modèles ───────────────────────────────────────────────
MODELS = [
    {
        "name": "UltraFace slim_320.param (NCNN)",
        "url": "https://raw.githubusercontent.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB/master/ncnn/data/version-slim/slim_320.param",
        "filename": "slim_320.param",
    },
    {
        "name": "UltraFace slim_320.bin (NCNN)",
        "url": "https://raw.githubusercontent.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB/master/ncnn/data/version-slim/slim_320.bin",
        "filename": "slim_320.bin",
    },
    {
        "name": "UltraFace version-slim-320.onnx (OpenCV DNN fallback)",
        "url": "https://raw.githubusercontent.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB/master/models/onnx/version-slim-320.onnx",
        "filename": "version-slim-320.onnx",
    },
    {
        "name": "OCEC ocec_p.onnx (yeux ouverts/fermés, 112 KB)",
        "url": "https://github.com/PINTO0309/OCEC/releases/download/onnx/ocec_p.onnx",
        "filename": "ocec_p.onnx",
    },
]

# Modèles OCEC alternatifs (plus gros = plus précis mais plus lent)
OCEC_ALTERNATIVES = {
    "ocec_n": {
        "name": "OCEC nano (176 KB, F1=0.9933)",
        "url": "https://github.com/PINTO0309/OCEC/releases/download/onnx/ocec_n.onnx",
        "filename": "ocec_n.onnx",
    },
    "ocec_s": {
        "name": "OCEC small (494 KB, F1=0.9943)",
        "url": "https://github.com/PINTO0309/OCEC/releases/download/onnx/ocec_s.onnx",
        "filename": "ocec_s.onnx",
    },
    "ocec_c": {
        "name": "OCEC compact (875 KB, F1=0.9947)",
        "url": "https://github.com/PINTO0309/OCEC/releases/download/onnx/ocec_c.onnx",
        "filename": "ocec_c.onnx",
    },
    "ocec_m": {
        "name": "OCEC medium (1.7 MB, F1=0.9949)",
        "url": "https://github.com/PINTO0309/OCEC/releases/download/onnx/ocec_m.onnx",
        "filename": "ocec_m.onnx",
    },
    "ocec_l": {
        "name": "OCEC large (6.4 MB, F1=0.9954)",
        "url": "https://github.com/PINTO0309/OCEC/releases/download/onnx/ocec_l.onnx",
        "filename": "ocec_l.onnx",
    },
}


def download_file(url, dest_path, description=""):
    """Télécharge un fichier avec barre de progression."""
    if os.path.exists(dest_path):
        size = os.path.getsize(dest_path)
        print(f"  ✓ {description} déjà présent ({size:,} bytes)")
        return True

    print(f"  ↓ Téléchargement : {description}")
    print(f"    URL : {url}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            total = response.headers.get("Content-Length")
            total = int(total) if total else None
            downloaded = 0
            chunk_size = 8192
            data = bytearray()

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                data.extend(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 / total
                    bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
                    print(f"\r    [{bar}] {pct:.0f}% ({downloaded:,}/{total:,})", end="", flush=True)
                else:
                    print(f"\r    {downloaded:,} bytes...", end="", flush=True)

            print()

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(data)

            print(f"  ✓ Sauvegardé : {dest_path} ({len(data):,} bytes)")
            return True

    except Exception as e:
        print(f"\n  ✗ Échec : {e}")
        return False


def main():
    print("=" * 60)
    print("  Téléchargement des modèles — Détection de fatigue")
    print("=" * 60)
    print(f"  Dossier : {MODELS_DIR}\n")

    os.makedirs(MODELS_DIR, exist_ok=True)

    # Téléchargement des modèles principaux
    success = 0
    for model in MODELS:
        dest = os.path.join(MODELS_DIR, model["filename"])
        if download_file(model["url"], dest, model["name"]):
            success += 1

    print(f"\n  Résultat : {success}/{len(MODELS)} modèles OK\n")

    # Proposer les alternatives OCEC
    if "--all-ocec" in sys.argv:
        print("  Téléchargement des variantes OCEC additionnelles...\n")
        for key, model in OCEC_ALTERNATIVES.items():
            dest = os.path.join(MODELS_DIR, model["filename"])
            download_file(model["url"], dest, model["name"])

    if success < len(MODELS):
        print("  ⚠ Certains modèles n'ont pas pu être téléchargés.")
        print("    Vérifiez votre connexion Internet et relancez ce script.")
        sys.exit(1)
    else:
        print("  ✓ Tous les modèles sont prêts !")
        print()
        print("  Pour lancer la détection :")
        print("    python main.py")
        print()
        print("  Pour télécharger toutes les variantes OCEC :")
        print("    python download_models.py --all-ocec")


if __name__ == "__main__":
    main()
