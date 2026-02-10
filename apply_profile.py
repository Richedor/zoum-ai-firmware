#!/usr/bin/env python3
"""
apply_profile.py — Bascule config.py entre profil PC et profil Pi.

Usage :
    python apply_profile.py pi     # configurer pour Pi Zero 2 W + IMX219 160°
    python apply_profile.py pc     # configurer pour webcam PC standard

Ce script modifie directement config.py. Aucun impact sur les performances
à l'exécution — il suffit de le lancer une seule fois après le clonage.
"""
import sys
import re
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")

# ─── Profils : paramètre → (valeur_pc, valeur_pi) ───────────────────
PROFILES = {
    "CENTER_CROP_RATIO": ("1.0", "0.65"),
    "FACE_SCORE_THRESHOLD": ("0.50", "0.65"),
    "FACE_MIN_SIZE": ("25", "40"),
}

# Commentaires associés pour chaque profil
COMMENTS = {
    "CENTER_CROP_RATIO": {
        "pc": "# Webcam PC : pas de crop",
        "pi": "# Pi + IMX219 IR 160° : garder 65 % au centre",
    },
}


def apply_profile(profile: str):
    if profile not in ("pc", "pi"):
        print(f"Erreur : profil '{profile}' inconnu. Utilisez 'pc' ou 'pi'.")
        sys.exit(1)

    idx = 0 if profile == "pc" else 1

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    changes = 0
    for param, (val_pc, val_pi) in PROFILES.items():
        target_val = val_pi if profile == "pi" else val_pc
        other_val = val_pc if profile == "pi" else val_pi

        # Regex : PARAM = <nombre>  (avec espaces et commentaire optionnel)
        pattern = rf"^({param}\s*=\s*)[\d.]+(.*)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            old_line = match.group(0)
            new_line = f"{match.group(1)}{target_val}{match.group(2)}"
            if old_line != new_line:
                content = content.replace(old_line, new_line, 1)
                changes += 1
                print(f"  {param} = {target_val}  (était {match.group(0).split('=')[1].split('#')[0].strip()})")
            else:
                print(f"  {param} = {target_val}  (déjà OK)")
        else:
            print(f"  ⚠ {param} non trouvé dans config.py")

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✓ Profil '{profile.upper()}' appliqué ({changes} modification(s)).")
    if profile == "pi":
        print("  → Optimisé pour Pi Zero 2 W + IMX219 IR 160°")
        print("  → CENTER_CROP = 0.65, seuils visage rehaussés")
    else:
        print("  → Optimisé pour webcam PC standard")
        print("  → Pas de crop, seuils visage permissifs")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage : python apply_profile.py <pc|pi>")
        print()
        print("  pc  — Webcam PC standard (pas de crop, seuils bas)")
        print("  pi  — Pi Zero 2 W + IMX219 IR 160° (crop 65%, seuils hauts)")
        print()
        print("Paramètres modifiés :")
        for param, (val_pc, val_pi) in PROFILES.items():
            print(f"  {param:25s}  PC={val_pc:6s}  Pi={val_pi:6s}")
        sys.exit(0)

    apply_profile(sys.argv[1])


if __name__ == "__main__":
    main()
