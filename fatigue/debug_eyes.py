#!/usr/bin/env python3
"""
debug_eyes.py — Diagnostic visuel de la détection yeux.
Affiche en temps réel les crops yeux + probabilités OCEC.
"""
import cv2
import numpy as np
import config
from camera import Camera
from face_detector import UltraFaceDetector
from eye_classifier import EyeClassifier, extract_eye_rois

cam = Camera()
detector = UltraFaceDetector()
classifier = EyeClassifier()

print("Appuyez sur 'q' pour quitter.")
print("Regardez la fenêtre : les crops yeux et valeurs prob_open s'affichent.\n")

while True:
    ok, frame = cam.read()
    if not ok:
        break

    img_h, img_w = frame.shape[:2]
    detections = detector.detect(frame)
    face = UltraFaceDetector.largest_face(detections, min_size=20)

    debug = frame.copy()

    if face is not None:
        x1, y1, x2, y2, score = int(face[0]), int(face[1]), int(face[2]), int(face[3]), face[4]
        fw, fh = x2 - x1, y2 - y1
        cv2.rectangle(debug, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(debug, f"Face {score:.2f} ({fw}x{fh}px)", (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        left_eye, right_eye = extract_eye_rois(frame, face)

        # Dessiner les ROI yeux sur la frame
        for label, rx1, ry1, rx2, ry2 in [
            ("G", config.EYE_LEFT_X1, config.EYE_LEFT_Y1, config.EYE_LEFT_X2, config.EYE_LEFT_Y2),
            ("D", config.EYE_RIGHT_X1, config.EYE_RIGHT_Y1, config.EYE_RIGHT_X2, config.EYE_RIGHT_Y2),
        ]:
            ex1 = int(x1 + rx1 * fw)
            ey1 = int(y1 + ry1 * fh)
            ex2 = int(x1 + rx2 * fw)
            ey2 = int(y1 + ry2 * fh)
            cv2.rectangle(debug, (ex1, ey1), (ex2, ey2), (0, 255, 0), 1)
            cv2.putText(debug, label, (ex1, ey1 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        # Classifier chaque oeil et afficher les valeurs brutes
        crops = []
        for i, (eye_crop, label) in enumerate([(left_eye, "GAUCHE"), (right_eye, "DROIT")]):
            if eye_crop is not None and eye_crop.size > 0:
                prob = classifier.classify(eye_crop)
                state = "OUVERT" if prob >= config.EYE_OPEN_THRESHOLD else "FERME"
                color = (0, 255, 0) if prob >= config.EYE_OPEN_THRESHOLD else (0, 0, 255)

                # Afficher la prob sur la frame
                y_pos = 30 + i * 25
                cv2.putText(debug, f"{label}: prob_open={prob:.4f} -> {state}",
                            (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

                # Agrandir le crop pour l'affichage
                eye_show = cv2.resize(eye_crop, (120, 72), interpolation=cv2.INTER_NEAREST)
                cv2.putText(eye_show, f"{prob:.3f}", (5, 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                crops.append(eye_show)

                print(f"  {label}: prob_open={prob:.4f}  ({state})"
                      f"  crop_size={eye_crop.shape[1]}x{eye_crop.shape[0]}", end="")
            else:
                print(f"  {label}: PAS DE CROP", end="")

        print()

        # Coller les crops agrandis en bas de la frame
        if crops:
            strip = np.hstack(crops) if len(crops) > 1 else crops[0]
            sh, sw = strip.shape[:2]
            dh, dw = debug.shape[:2]
            if sw <= dw and sh <= dh:
                debug[dh - sh:dh, 0:sw] = strip
    else:
        cv2.putText(debug, "PAS DE VISAGE", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        print("  Pas de visage détecté")

    cv2.imshow("Debug Yeux", debug)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()
