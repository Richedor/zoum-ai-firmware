#!/usr/bin/env python3
"""
main.py — Pipeline Fatigue Lite (Head Nod + Bâillements).

Version allégée sans classification des yeux (OCEC) ni PERCLOS.
Détecte la fatigue via :
  1. Head nods : hochements de tête caractéristiques du microsommeil
  2. Bâillements : chute d'intensité dans la zone bouche
  3. Fusion temporelle → niveaux d'alerte (NORMAL / ATTENTION / ALERTE)

Pipeline par frame :
  1. Capture caméra + center-crop (correction FOV 160°)
  2. UltraFace → détection visage
  3. Head nod tracking (zéro coût, bbox uniquement)
  4. Extraction ROI bouche → bâillements
  5. Fusion → niveau d'alerte → buzzer GPIO

Cible : Pi Zero 2 W + IMX219 IR 160° @ 8-10 FPS

Usage :
    python3 main.py                    # caméra par défaut
    python3 main.py --no-display --stream   # headless + MJPEG
    python3 main.py --source video.mp4
"""
import sys
import os

# ── Import path : fatiguev2/ d'abord, parent ensuite ────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_DIR)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
if _PARENT not in sys.path:
    sys.path.insert(1, _PARENT)

import argparse
import time
import cv2
import numpy as np

import config
from camera import Camera
from face_detector import UltraFaceDetector
from yawn_detector import YawnDetector
from head_nod import HeadNodDetector
from fatigue_fusion import FatigueFusion
from alert import AlertManager
import stream_server


# ─── Couleurs ────────────────────────────────────────────────────────
GREEN  = (0, 255, 0)
RED    = (0, 0, 255)
ORANGE = (0, 165, 255)
CYAN   = (255, 255, 0)
WHITE  = (255, 255, 255)
YELLOW = (0, 255, 255)

LEVEL_COLORS = {
    FatigueFusion.LEVEL_NORMAL:  GREEN,
    FatigueFusion.LEVEL_WARNING: ORANGE,
    FatigueFusion.LEVEL_ALERT:   RED,
}


# ─── Overlay ─────────────────────────────────────────────────────────
def draw_overlay(frame, face_box, nod, yawn, fusion, fps):
    """Dessine les informations de debug sur la frame."""
    h, w = frame.shape[:2]
    color = LEVEL_COLORS.get(fusion.level, GREEN)

    # ── Bandeau statut en haut ───────────────────────────────────────
    cv2.rectangle(frame, (0, 0), (w, 58), (0, 0, 0), -1)

    # Ligne 1 : FPS + niveau
    cv2.putText(frame, f"FPS:{fps:.1f}", (8, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
    label = f"[{fusion.level_name}]"
    lw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0][0]
    cv2.putText(frame, label, (w - lw - 8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # Ligne 2 : nods + yawns + head
    nod_txt = f"Nods:{nod.nod_count}/{config.NOD_WINDOW_SEC/60:.0f}min"
    yawn_txt = f"Baill:{yawn.yawn_count}"
    dev_txt = f"Head:{nod.deviation:+.2f} [{nod.state_name}]"
    info = f"{nod_txt}  {yawn_txt}  {dev_txt}"
    cv2.putText(frame, info, (8, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, CYAN, 1)

    # Ligne 3 : durée tête basse (si > 0)
    if nod.head_down_duration > 0.1:
        down_txt = f"Tete basse: {nod.head_down_duration:.1f}s"
        dc = RED if nod.is_microsleep else ORANGE
        cv2.putText(frame, down_txt, (8, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, dc, 1)

    # ── Face bbox ────────────────────────────────────────────────────
    if face_box is not None and config.DRAW_FACE_BOX:
        x1, y1, x2, y2 = int(face_box[0]), int(face_box[1]), \
                          int(face_box[2]), int(face_box[3])
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Score visage
        score = face_box[4] if len(face_box) > 4 else 0
        cv2.putText(frame, f"{score:.0%}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Jauge de déviation (barre verticale à droite du bbox)
        bar_x = x2 + 8
        bar_top = y1
        bar_bot = y2
        bar_mid = int((bar_top + bar_bot) / 2)
        cv2.line(frame, (bar_x, bar_top), (bar_x, bar_bot), WHITE, 1)
        # Marqueur baseline
        cv2.line(frame, (bar_x - 4, bar_mid), (bar_x + 4, bar_mid), GREEN, 2)
        # Marqueur position actuelle
        face_h = y2 - y1
        pos_y = int(bar_mid + nod.deviation * face_h)
        pos_y = max(bar_top, min(bar_bot, pos_y))
        marker_color = RED if nod.state == HeadNodDetector.HEAD_DOWN else YELLOW
        cv2.circle(frame, (bar_x, pos_y), 4, marker_color, -1)

        # Indicateur bouche
        if config.DRAW_MOUTH_ROI:
            fw, fh = x2 - x1, y2 - y1
            mx1 = int(x1 + config.MOUTH_ROI_X1 * fw)
            my1 = int(y1 + config.MOUTH_ROI_Y1 * fh)
            mx2 = int(x1 + config.MOUTH_ROI_X2 * fw)
            my2 = int(y1 + config.MOUTH_ROI_Y2 * fh)
            mc = ORANGE if yawn.is_yawning else GREEN
            cv2.rectangle(frame, (mx1, my1), (mx2, my2), mc, 1)

    # ── Alerte full-screen ───────────────────────────────────────────
    if fusion.level == FatigueFusion.LEVEL_ALERT:
        cv2.rectangle(frame, (0, h - 30), (w, h), RED, -1)
        cv2.putText(frame, "!!! ALERTE FATIGUE !!!", (w // 2 - 120, h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2)


# ─── Calibration ─────────────────────────────────────────────────────
def run_calibration(cam, detector, nod_det, yawn_det, show):
    """Phase de calibration (position de base tête + bouche fermée)."""
    print(f"[CALIB] Calibration {config.CALIBRATION_SEC}s "
          f"— gardez la tête droite et la bouche fermée...")

    t_start = time.time()
    while time.time() - t_start < config.CALIBRATION_SEC:
        ok, frame = cam.read()
        if not ok or frame is None:
            continue

        img_h, img_w = frame.shape[:2]
        dets = detector.detect(frame)
        face_box = UltraFaceDetector.largest_face(dets)

        if face_box is not None:
            nod_det.add_calibration_sample(face_box, img_h)
            mouth = yawn_det.extract_mouth_roi(frame, face_box)
            yawn_det.update_baseline(mouth)

        if show:
            elapsed = time.time() - t_start
            cv2.putText(frame, f"CALIBRATION {elapsed:.1f}/{config.CALIBRATION_SEC:.0f}s",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, YELLOW, 2)
            cv2.imshow("Fatigue Lite", frame)
            cv2.waitKey(1)

    nod_ok = nod_det.finalize_baseline()
    yawn_det.finalize_baseline()
    return nod_ok


# ─── Boucle principale ───────────────────────────────────────────────
def run(args):
    print("=" * 60)
    print("  Fatigue Lite — Head Nod + Bâillements")
    pi_str = "Pi Zero 2 W + IMX219 IR" if config._IS_PI else "PC"
    print(f"  Plateforme : {pi_str}")
    print("=" * 60)

    # Init
    source = int(args.source) if args.source.isdigit() else args.source
    cam = Camera(source=source)
    detector = UltraFaceDetector()
    nod_det = HeadNodDetector()
    yawn_det = YawnDetector()
    fusion = FatigueFusion()
    alert_mgr = AlertManager(enabled=not args.no_buzzer)

    show = args.display and config.SHOW_PREVIEW

    # Streaming MJPEG
    mjpeg_srv = None
    if args.stream:
        mjpeg_srv = stream_server.start(port=args.stream_port)

    # Calibration
    if args.calibration:
        nod_ok = run_calibration(cam, detector, nod_det, yawn_det, show)
    else:
        nod_ok = True
        nod_det.baseline_y = 0.5  # défaut centré
        yawn_det.finalize_baseline()
        print("[MAIN] Calibration désactivée, valeurs par défaut.")

    # FPS
    fps_alpha = 0.9
    fps = 0.0
    frame_count = 0

    print(f"[MAIN] Pipeline démarré (affichage: {show}, stream: {mjpeg_srv is not None})")
    print(f"[MAIN] Crop: {config.CENTER_CROP_RATIO:.0%} | "
          f"Face seuil: {config.FACE_SCORE_THRESHOLD}")
    print(f"[MAIN] Nod: descente>{config.NOD_DOWN_THRESHOLD:.0%} face_h, "
          f"microsommeil>{config.NOD_MICROSLEEP_SEC}s")
    print("-" * 60)

    try:
        while True:
            t0 = time.time()

            # 1. Capture
            ok, frame = cam.read()
            if not ok or frame is None:
                if isinstance(source, str):
                    print("[MAIN] Fin de la vidéo.")
                    break
                continue

            img_h, img_w = frame.shape[:2]

            # 2. Détection visage
            if img_w > config.DETECT_WIDTH * 1.5:
                scale = config.DETECT_WIDTH / img_w
                det_frame = cv2.resize(frame, None, fx=scale, fy=scale)
            else:
                det_frame = frame
                scale = 1.0

            dets = detector.detect(det_frame)
            if scale != 1.0 and len(dets) > 0:
                dets[:, :4] /= scale

            face_box = UltraFaceDetector.largest_face(dets)

            # Debug : afficher les scores si aucun visage retenu
            if face_box is None and len(dets) > 0 and frame_count % 50 == 0:
                scores = dets[:, 4] if dets.shape[1] > 4 else []
                print(f"[DEBUG] {len(dets)} détection(s) rejetée(s), "
                      f"scores={[f'{s:.2f}' for s in scores]}, "
                      f"min_size={config.FACE_MIN_SIZE}")

            # 3. Head nod
            nod_det.update(face_box, img_h)

            # 4. Bâillement
            if face_box is not None:
                mouth = yawn_det.extract_mouth_roi(frame, face_box)
                yawn_det.update(mouth)

            # 5. Fusion → alerte
            level, nc, hds = fusion.update(
                nod_det.nod_count,
                nod_det.is_microsleep,
                nod_det.head_down_duration,
                yawn_det.yawn_count,
            )
            alert_mgr.trigger(level, fusion.level_name)

            # 6. FPS
            dt = time.time() - t0
            ifps = 1.0 / dt if dt > 0 else 0
            fps = fps * fps_alpha + ifps * (1 - fps_alpha) if frame_count > 0 else ifps
            frame_count += 1

            # 7. Affichage
            if show:
                draw_overlay(frame, face_box, nod_det, yawn_det, fusion, fps)
                cv2.imshow("Fatigue Lite", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    break
                elif key == ord('r'):
                    nod_det.reset()
                    yawn_det.reset()
                    fusion.reset()
                    print("[MAIN] Reset.")
                elif key == ord('c'):
                    run_calibration(cam, detector, nod_det, yawn_det, show)
                    fusion.reset()

            # 8. Stream MJPEG
            if mjpeg_srv is not None:
                if show:
                    stream_server.update_frame(frame)
                else:
                    overlay = frame.copy()
                    draw_overlay(overlay, face_box, nod_det, yawn_det, fusion, fps)
                    stream_server.update_frame(overlay)

            # 9. Log console
            if frame_count % max(int(fps * 2), 10) == 0 and config.PRINT_FPS:
                ystr = f"  Baill={yawn_det.yawn_count}" if yawn_det.yawn_count else ""
                nstr = f"  Nods={nod_det.nod_count}" if nod_det.nod_count else ""
                dstr = f"  Down={nod_det.head_down_duration:.1f}s" if nod_det.head_down_duration > 0.1 else ""
                print(f"  FPS={fps:.1f}{nstr}{dstr}{ystr}  [{fusion.level_name}]")

    except KeyboardInterrupt:
        print("\n[MAIN] Interruption clavier.")
    finally:
        if mjpeg_srv:
            stream_server.stop(mjpeg_srv)
        alert_mgr.cleanup()
        cam.release()
        if show:
            cv2.destroyAllWindows()
        print("[MAIN] Pipeline arrêté.")


def main():
    parser = argparse.ArgumentParser(
        description="Fatigue Lite — Head Nod + Bâillements (Pi Zero 2 W)"
    )
    parser.add_argument("--source", "-s", default=str(config.CAMERA_INDEX),
                        help="Source vidéo (index caméra ou fichier)")
    parser.add_argument("--no-display", dest="display", action="store_false",
                        help="Mode headless (pas de fenêtre OpenCV)")
    parser.add_argument("--no-buzzer", action="store_true",
                        help="Désactiver le buzzer GPIO")
    parser.add_argument("--no-calibration", dest="calibration",
                        action="store_false",
                        help="Désactiver la calibration au démarrage")
    parser.add_argument("--stream", action="store_true",
                        help="Activer le streaming MJPEG (http://<ip>:8080)")
    parser.add_argument("--stream-port", type=int, default=8080,
                        help="Port du serveur MJPEG (défaut: 8080)")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
