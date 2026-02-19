#!/usr/bin/env python3
"""
main.py — Pipeline de détection de fatigue embarqué.

Séquence par frame :
  1. Capture caméra + center-crop (correction FOV 160°)
  2. UltraFace → détection visage (ncnn / OpenCV DNN)
  3. Extraction ROI yeux (heuristique, pas de landmarks)
  4. OCEC → classification ouvert/fermé par œil
  5. Extraction ROI bouche → détection bâillements
  6. PERCLOS + microsommeil + bâillements → niveau d'alerte
  7. Alerte buzzer GPIO + affichage

Phase de calibration automatique (5 s) au démarrage :
  - Mesure CHAQUE OEIL séparément (baseline gauche/droite)
  - Calcule un seuil de fermeture propre à chaque œil
  - Détecte et désactive automatiquement un ROI désaligné
  - Calibre aussi la baseline de la bouche fermée

Indicateurs :
  - PERCLOS : % du temps yeux fermés sur les 60 dernières secondes
    (norme ISO : > 30 % = somnolence, > 50 % = danger)
  - Fermeture : durée de fermeture continue des yeux
    (> 3.5 s = microsommeil → alerte immédiate)

Cible : Raspberry Pi Zero 2 W + IMX219 IR (160°)

Usage :
    python main.py                   # caméra par défaut
    python main.py --source video.mp4
    python main.py --source 0 --no-display
    python main.py --no-calibration  # désactiver la calibration
"""
import argparse
import time
import sys
import cv2
import numpy as np

import config
from camera import Camera
from face_detector import UltraFaceDetector
from eye_classifier import EyeClassifier, extract_eye_rois
from yawn_detector import YawnDetector
from gaze_monitor import GazeMonitor
from fatigue_monitor import FatigueMonitor
from alert import AlertManager
import stream_server


# ─── Couleurs affichage ─────────────────────────────────────────────
COLOR_GREEN  = (0, 255, 0)
COLOR_RED    = (0, 0, 255)
COLOR_ORANGE = (0, 165, 255)
COLOR_CYAN   = (255, 255, 0)
COLOR_WHITE  = (255, 255, 255)
COLOR_YELLOW = (0, 255, 255)

LEVEL_COLORS = {
    FatigueMonitor.LEVEL_NORMAL:  COLOR_GREEN,
    FatigueMonitor.LEVEL_WARNING: COLOR_ORANGE,
    FatigueMonitor.LEVEL_ALERT:   COLOR_RED,
    FatigueMonitor.LEVEL_MICRO:   COLOR_RED,
}


def draw_overlay(frame, face_box, prob_left, prob_right, calib_info,
                 fatigue, yawn_det, gaze_mon, fps):
    """Dessine les informations de debug sur la frame."""
    h, w = frame.shape[:2]
    level_color = LEVEL_COLORS.get(fatigue.level, COLOR_WHITE)
    thr_l, thr_r, use_l, use_r = calib_info

    # Bounding box visage
    if face_box is not None and config.DRAW_FACE_BOX:
        x1, y1, x2, y2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
        cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_CYAN, 2)
        cv2.putText(frame, f"{face_box[4]:.2f}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOR_CYAN, 1)

    # ROI yeux
    if config.DRAW_EYE_ROIS and face_box is not None:
        fx1, fy1, fx2, fy2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
        fw, fh = fx2 - fx1, fy2 - fy1
        for idx, (rx1, ry1, rx2, ry2) in enumerate([
            (config.EYE_LEFT_X1, config.EYE_LEFT_Y1, config.EYE_LEFT_X2, config.EYE_LEFT_Y2),
            (config.EYE_RIGHT_X1, config.EYE_RIGHT_Y1, config.EYE_RIGHT_X2, config.EYE_RIGHT_Y2),
        ]):
            active = use_l if idx == 0 else use_r
            ex1 = int(fx1 + rx1 * fw)
            ey1 = int(fy1 + ry1 * fh)
            ex2 = int(fx1 + rx2 * fw)
            ey2 = int(fy1 + ry2 * fh)
            color = COLOR_GREEN if active else (80, 80, 80)  # grisé si désactivé
            cv2.rectangle(frame, (ex1, ey1), (ex2, ey2), color, 1)

    # ROI bouche
    if getattr(config, 'DRAW_MOUTH_ROI', False) and face_box is not None:
        fx1, fy1, fx2, fy2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
        fw, fh = fx2 - fx1, fy2 - fy1
        mx1 = int(fx1 + config.MOUTH_ROI_X1 * fw)
        my1 = int(fy1 + config.MOUTH_ROI_Y1 * fh)
        mx2 = int(fx1 + config.MOUTH_ROI_X2 * fw)
        my2 = int(fy1 + config.MOUTH_ROI_Y2 * fh)
        color = COLOR_YELLOW if yawn_det.is_yawning else COLOR_GREEN
        cv2.rectangle(frame, (mx1, my1), (mx2, my2), color, 1)

    # Probabilités yeux
    y_text = 25
    if prob_left >= 0:
        tag_l = "" if use_l else " [OFF]"
        state_l = "Ouvert" if prob_left >= thr_l else "Ferme"
        cv2.putText(frame, f"G: {prob_left:.2f} ({state_l}){tag_l}", (10, y_text),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_WHITE if use_l else (120, 120, 120), 1)
        y_text += 20
    if prob_right >= 0:
        tag_r = "" if use_r else " [OFF]"
        state_r = "Ouvert" if prob_right >= thr_r else "Ferme"
        cv2.putText(frame, f"D: {prob_right:.2f} ({state_r}){tag_r}", (10, y_text),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_WHITE if use_r else (120, 120, 120), 1)
        y_text += 20

    # Seuils calibrés
    cv2.putText(frame, f"Seuils: G={thr_l:.2f} D={thr_r:.2f}", (10, y_text),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, COLOR_CYAN, 1)
    y_text += 20

    # PERCLOS & état
    cv2.putText(frame, f"PERCLOS: {fatigue.perclos:.1%}", (10, y_text),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, level_color, 1 if fatigue.level == 0 else 2)
    y_text += 22

    cv2.putText(frame, f"Ferme: {fatigue.consecutive_closed_sec:.1f}s", (10, y_text),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, level_color, 1)
    y_text += 22

    # Bâillements
    yawn_color = COLOR_YELLOW if yawn_det.is_yawning else COLOR_WHITE
    cv2.putText(frame, f"Baill: {yawn_det.yawn_count}  M:{yawn_det.mouth_open_ratio:.2f}",
                (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.45, yawn_color, 1)
    y_text += 22

    # Baissement de regard
    if getattr(config, 'DRAW_GAZE_INFO', False) and gaze_mon.baseline_y is not None:
        gaze_color = COLOR_RED if gaze_mon.is_looking_down else (
            COLOR_ORANGE if gaze_mon.down_duration > 0.5 else COLOR_WHITE)
        gaze_tag = " \u25bc BAS" if gaze_mon.is_looking_down else ""
        cv2.putText(frame, f"Regard: {gaze_mon.deviation:+.2f}  {gaze_mon.down_count}x{gaze_tag}",
                    (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.45, gaze_color, 1)
        y_text += 22

    # Bandeau d'alerte
    if fatigue.level >= FatigueMonitor.LEVEL_WARNING:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - 50), (w, h), level_color, -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        label = fatigue.level_name
        if yawn_det.is_yawning:
            label += " + BAILLEMENT"
        if gaze_mon.is_looking_down:
            label += " + REGARD BAS"
        cv2.putText(frame, f"  {label}  ", (w // 2 - 120, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_WHITE, 2)

    # FPS
    if config.PRINT_FPS:
        cv2.putText(frame, f"{fps:.1f} FPS", (w - 100, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_GREEN, 1)


# ─── Phase de calibration ───────────────────────────────────────────
def run_calibration(cam, detector, classifier, yawn_det, gaze_mon, show=True):
    """
    Phase de calibration (N secondes) :
    - Mesure CHAQUE OEIL séparément (baseline gauche / droite)
    - Calcule un seuil propre à chaque œil
    - Détecte un ROI désaligné (baseline trop basse → désactivé)
    - Calibre la baseline bouche fermée
    - Calibre la position verticale normale (regard droit)

    Returns:
        (thresh_left, thresh_right, use_left, use_right)
    """
    calib_sec = config.CALIBRATION_SEC
    print(f"[CALIB] Calibration {calib_sec:.0f}s — gardez les yeux ouverts et la bouche fermée...")

    left_samples = []
    right_samples = []
    t_start = time.time()

    while time.time() - t_start < calib_sec:
        ok, frame = cam.read()
        if not ok or frame is None:
            continue

        # Détection visage
        img_h, img_w = frame.shape[:2]
        if img_w > config.DETECT_WIDTH * 1.5:
            scale = config.DETECT_WIDTH / img_w
            detect_frame = cv2.resize(frame, None, fx=scale, fy=scale)
        else:
            detect_frame = frame
            scale = 1.0

        detections = detector.detect(detect_frame)
        if scale != 1.0 and len(detections) > 0:
            detections[:, :4] /= scale

        face_box = UltraFaceDetector.largest_face(detections)

        if face_box is not None:
            left_eye, right_eye = extract_eye_rois(frame, face_box)
            if left_eye is not None:
                p = classifier.classify(left_eye)
                if p >= 0:
                    left_samples.append(p)
            if right_eye is not None:
                p = classifier.classify(right_eye)
                if p >= 0:
                    right_samples.append(p)

            # Calibration bouche
            mouth = yawn_det.extract_mouth_roi(frame, face_box)
            if mouth is not None:
                yawn_det.update_baseline(mouth)

            # Calibration regard (position Y)
            gaze_mon.update_baseline(face_box, img_h)

        # Affichage calibration
        if show:
            elapsed = time.time() - t_start
            remaining = max(0, calib_sec - elapsed)
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (0, 0), (w, 55), (50, 50, 50), -1)
            cv2.putText(frame, f"CALIBRATION - yeux ouverts, bouche fermee ({remaining:.0f}s)",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_YELLOW, 2)
            # Barre de progression
            pct = elapsed / calib_sec
            cv2.rectangle(frame, (10, 42), (int(10 + (w - 20) * pct), 50), COLOR_CYAN, -1)

            cv2.imshow("Fatigue Detection", frame)
            cv2.waitKey(1)

    # Finaliser baseline bouche
    yawn_det.finalize_baseline()

    # Finaliser baseline regard
    gaze_mon.finalize_baseline()

    # ── Calibration par oeil ─────────────────────────────────────────
    def _compute_eye(name, samples):
        if len(samples) < 5:
            print(f"[CALIB] {name}: pas assez d'échantillons ({len(samples)}) → désactivé")
            return config.EYE_OPEN_THRESHOLD, False
        baseline = float(np.median(samples))
        if baseline < 0.20:
            # Baseline trop basse = ROI probablement désaligné
            print(f"[CALIB] {name}: baseline={baseline:.3f} trop basse → désactivé")
            return config.EYE_OPEN_THRESHOLD, False
        threshold = baseline * config.CALIBRATION_RATIO
        threshold = float(np.clip(threshold, config.CALIBRATION_MIN_THR, config.CALIBRATION_MAX_THR))
        print(f"[CALIB] {name}: baseline={baseline:.3f} ({len(samples)} éch.) "
              f"→ seuil={threshold:.3f}")
        return threshold, True

    thr_l, use_l = _compute_eye("Oeil G", left_samples)
    thr_r, use_r = _compute_eye("Oeil D", right_samples)

    if not use_l and not use_r:
        # Aucun oeil fiable, utiliser les deux avec seuil par défaut
        thr_l = thr_r = config.EYE_OPEN_THRESHOLD
        use_l = use_r = True
        print(f"[CALIB] Aucun œil fiable, seuil par défaut : {config.EYE_OPEN_THRESHOLD:.2f}")

    active = []
    if use_l:
        active.append("G")
    if use_r:
        active.append("D")
    print(f"[CALIB] Yeux actifs : {'+'.join(active)}")

    return thr_l, thr_r, use_l, use_r


def run(args):
    """Boucle principale du pipeline."""
    print("=" * 60)
    print("  Détection de fatigue — Pi Zero 2 W + IMX219 IR 160°")
    print("  PERCLOS + Bâillements + Calibration par œil")
    print("=" * 60)

    # ── Initialisation ───────────────────────────────────────────────
    source = int(args.source) if args.source.isdigit() else args.source
    cam = Camera(source=source)
    detector = UltraFaceDetector()
    classifier = EyeClassifier()
    yawn_det = YawnDetector()
    gaze_mon = GazeMonitor()
    fatigue = FatigueMonitor()
    alert_mgr = AlertManager(enabled=not args.no_buzzer)

    show = args.display and config.SHOW_PREVIEW

    # ── Serveur MJPEG (streaming vidéo distant) ──────────────────
    mjpeg_srv = None
    if args.stream:
        mjpeg_srv = stream_server.start(port=args.stream_port)

    # ── Calibration automatique (par œil) ────────────────────────────
    if args.calibration:
        thr_l, thr_r, use_l, use_r = run_calibration(
            cam, detector, classifier, yawn_det, gaze_mon, show)
    else:
        thr_l = thr_r = config.EYE_OPEN_THRESHOLD
        use_l = use_r = True
        yawn_det.finalize_baseline()
        gaze_mon.finalize_baseline()
        print(f"[MAIN] Calibration désactivée, seuil par défaut : {thr_l:.2f}")

    calib_info = (thr_l, thr_r, use_l, use_r)

    # Compteur FPS (moyenne glissante)
    fps_alpha = 0.9
    fps = 0.0
    frame_count = 0
    no_face_count = 0
    closed_streak = 0  # lissage temporel : frames consécutives "fermé"

    print(f"[MAIN] Démarrage pipeline... (affichage: {show})")
    print(f"[MAIN] Center-crop: {config.CENTER_CROP_RATIO:.0%} | "
          f"Détect: {config.DETECT_WIDTH}x{config.DETECT_HEIGHT} | "
          f"PERCLOS fenêtre: {config.PERCLOS_WINDOW_SEC}s")
    print(f"[MAIN] Seuils PERCLOS — attention: {config.PERCLOS_WARN_THRESHOLD:.0%} | "
          f"alerte: {config.PERCLOS_ALERT_THRESHOLD:.0%} | "
          f"microsommeil: {config.MICROSLEEP_THRESHOLD_SEC}s")
    print("-" * 60)

    try:
        while True:
            t_start = time.time()

            # 1. Capture + center-crop
            ok, frame = cam.read()
            if not ok or frame is None:
                if isinstance(source, str):
                    print("[MAIN] Fin de la vidéo.")
                    break
                continue

            # 2. Resize pour inférence (optionnel si déjà petit)
            img_h, img_w = frame.shape[:2]
            if img_w > config.DETECT_WIDTH * 1.5:
                scale = config.DETECT_WIDTH / img_w
                detect_frame = cv2.resize(frame, None, fx=scale, fy=scale)
            else:
                detect_frame = frame
                scale = 1.0

            # 3. Détection visage
            detections = detector.detect(detect_frame)

            # Remettre à l'échelle de la frame originale si redimensionnée
            if scale != 1.0 and len(detections) > 0:
                detections[:, :4] /= scale

            face_box = UltraFaceDetector.largest_face(detections)

            # 4. Classification yeux
            prob_left = -1.0
            prob_right = -1.0
            raw_closed = False
            eyes_closed = False

            if face_box is not None:
                no_face_count = 0
                left_eye, right_eye = extract_eye_rois(frame, face_box)

                if left_eye is not None:
                    prob_left = classifier.classify(left_eye)
                if right_eye is not None:
                    prob_right = classifier.classify(right_eye)

                # Décision par œil avec seuils indépendants.
                # Logique OR : si UN SEUL œil actif dit "fermé", on considère
                # les yeux fermés. Un ROI désaligné (use=False) est ignoré.
                # En fatigue réelle, les deux yeux se ferment ensemble.
                # Lissage temporel (3 frames) évite les faux positifs.
                votes_closed = 0
                votes_total = 0
                if use_l and prob_left >= 0:
                    votes_total += 1
                    if prob_left < thr_l:
                        votes_closed += 1
                if use_r and prob_right >= 0:
                    votes_total += 1
                    if prob_right < thr_r:
                        votes_closed += 1

                # Fermé si au moins un œil actif vote fermé
                raw_closed = votes_total > 0 and votes_closed > 0

                # Lissage : 3 frames consécutives pour confirmer
                if raw_closed:
                    closed_streak += 1
                else:
                    closed_streak = 0
                eyes_closed = closed_streak >= 3

                # 5. Détection bâillements
                mouth = yawn_det.extract_mouth_roi(frame, face_box)
                yawn_det.update(mouth)

                # 6. Baissement de regard
                gaze_mon.update(face_box, img_h)

            else:
                no_face_count += 1
                closed_streak = 0
                if no_face_count > 30:
                    eyes_closed = False
                gaze_mon.update(None, img_h)

            # 7. Mise à jour PERCLOS + fatigue (avec bâillements + regard)
            level, perclos, closed_sec = fatigue.update(
                eyes_closed, yawn_count=yawn_det.yawn_count,
                gaze_down=gaze_mon.is_looking_down,
                gaze_down_count=gaze_mon.down_count
            )

            # 8. Alerte
            alert_mgr.trigger(level, fatigue.level_name)

            # 9. Affichage
            t_end = time.time()
            dt = t_end - t_start
            instant_fps = 1.0 / dt if dt > 0 else 0
            fps = fps * fps_alpha + instant_fps * (1 - fps_alpha) if frame_count > 0 else instant_fps
            frame_count += 1

            if show:
                draw_overlay(frame, face_box, prob_left, prob_right,
                             calib_info, fatigue, yawn_det, gaze_mon, fps)
                cv2.imshow("Fatigue Detection", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    print("[MAIN] Arrêt demandé.")
                    break
                elif key == ord('r'):
                    fatigue.reset()
                    yawn_det.reset()
                    gaze_mon.reset()
                    print("[MAIN] PERCLOS + bâillements + regard réinitialisés.")
                elif key == ord('c'):
                    thr_l, thr_r, use_l, use_r = run_calibration(
                        cam, detector, classifier, yawn_det, gaze_mon, show)
                    calib_info = (thr_l, thr_r, use_l, use_r)
                    fatigue.reset()
                    closed_streak = 0
                    gaze_mon.reset()
                    print("[MAIN] Recalibration effectuée.")

            # 10. Streaming MJPEG
            if mjpeg_srv is not None:
                if show:
                    stream_server.update_frame(frame)
                else:
                    overlay = frame.copy()
                    draw_overlay(overlay, face_box, prob_left, prob_right,
                                 calib_info, fatigue, yawn_det, gaze_mon, fps)
                    stream_server.update_frame(overlay)

            # Log périodique console (toutes les 2s environ)
            if frame_count % max(int(fps * 2), 10) == 0 and config.PRINT_FPS:
                yawn_str = f"  Baill={yawn_det.yawn_count}" if yawn_det.yawn_count > 0 else ""
                print(f"  FPS={fps:.1f}  PERCLOS={perclos:.1%}  "
                      f"Fermeture={closed_sec:.1f}s{yawn_str}  [{fatigue.level_name}]")

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
        description="Détection de fatigue embarquée — Pi Zero 2 W + IMX219 IR 160°"
    )
    parser.add_argument(
        "--source", "-s", default=str(config.CAMERA_INDEX),
        help="Source vidéo : index caméra (0) ou fichier vidéo (video.mp4)",
    )
    parser.add_argument(
        "--no-display", dest="display", action="store_false",
        help="Désactiver l'affichage OpenCV (mode headless)",
    )
    parser.add_argument(
        "--no-buzzer", action="store_true",
        help="Désactiver le buzzer GPIO",
    )
    parser.add_argument(
        "--no-calibration", dest="calibration", action="store_false",
        help="Désactiver la calibration automatique au démarrage",
    )
    parser.add_argument(
        "--stream", action="store_true",
        help="Activer le streaming MJPEG (http://<ip>:8080)",
    )
    parser.add_argument(
        "--stream-port", type=int, default=8080,
        help="Port du serveur MJPEG (défaut: 8080)",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
