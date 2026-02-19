"""
Vision — Intégration fatigue-lite (caméra + détection fatigue).

Lance le pipeline fatigue-lite dans un thread séparé.
Expose les données de fatigue via read() (thread-safe).

Gère l'isolation du module config : fatigue-lite a son propre config.py
qui ne doit pas écraser le config.py du firmware.
"""
from __future__ import annotations
import os
import sys
import time
import threading

_lock = threading.Lock()
_thread = None
_stop_event = threading.Event()
_fl_dir = None

_data = {
    "fatigue_level": 0,
    "fatigue_level_name": "NORMAL",
    "fatigue_nod_count": 0,
    "fatigue_yawn_count": 0,
    "fatigue_is_microsleep": False,
    "fatigue_head_down_sec": 0.0,
    "fatigue_face_detected": False,
    "fatigue_fps": 0.0,
    "fatigue_ok": False,
}


def init(fatigue_lite_dir: str = None) -> bool:
    """Localise fatigue-lite/. Ne lance pas encore le pipeline."""
    global _fl_dir

    if fatigue_lite_dir is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base, "fatigue-lite"),
            os.path.join(base, "..", "fatigue", "fatigue-lite"),
            os.path.join(os.path.expanduser("~"), "iot", "fatigue", "fatigue-lite"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                fatigue_lite_dir = c
                break

    if fatigue_lite_dir is None or not os.path.isdir(fatigue_lite_dir):
        print("[VISION] fatigue-lite/ non trouvé — désactivé")
        return False

    _fl_dir = fatigue_lite_dir
    print(f"[VISION] fatigue-lite trouvé : {_fl_dir}")
    return True


def start() -> bool:
    """Lance le pipeline dans un thread dédié."""
    global _thread
    if _fl_dir is None:
        return False
    _stop_event.clear()
    _thread = threading.Thread(target=_fatigue_loop, daemon=True, name="fatigue")
    _thread.start()
    print("[VISION] Pipeline fatigue démarré")
    return True


def _fatigue_loop():
    """Thread : caméra → face → nod → yawn → fusion (boucle continue)."""
    global _data
    import importlib.util

    # ── Charger le config de fatigue-lite sans écraser celui du firmware ──
    firmware_config = sys.modules.get("config")

    fl_config_path = os.path.join(_fl_dir, "config.py")
    spec = importlib.util.spec_from_file_location("config", fl_config_path)
    fl_config = importlib.util.module_from_spec(spec)
    sys.modules["config"] = fl_config
    spec.loader.exec_module(fl_config)

    # Ajouter fatigue-lite au path pour les imports
    if _fl_dir not in sys.path:
        sys.path.insert(0, _fl_dir)

    try:
        from camera import Camera
        from face_detector import UltraFaceDetector
        from head_nod import HeadNodDetector
        from yawn_detector import YawnDetector
        from fatigue_fusion import FatigueFusion
    except ImportError as e:
        print(f"[VISION] Import échoué: {e}")
        if firmware_config:
            sys.modules["config"] = firmware_config
        return

    # Restaurer le config firmware pour le reste de l'app
    if firmware_config:
        sys.modules["config"] = firmware_config

    # ── Init pipeline ────────────────────────────────────────────────
    try:
        cam = Camera(source=0)
        detector = UltraFaceDetector()
        nod_det = HeadNodDetector()
        yawn_det = YawnDetector()
        fusion = FatigueFusion()
    except Exception as e:
        print(f"[VISION] Init pipeline échoué: {e}")
        return

    # ── Calibration (5 s) ────────────────────────────────────────────
    print("[VISION] Calibration...")
    t_start = time.time()
    while time.time() - t_start < fl_config.CALIBRATION_SEC:
        if _stop_event.is_set():
            cam.release()
            return
        ok, frame = cam.read()
        if not ok or frame is None:
            continue
        img_h = frame.shape[0]
        dets = detector.detect(frame)
        face_box = UltraFaceDetector.largest_face(dets)
        if face_box is not None:
            nod_det.add_calibration_sample(face_box, img_h)
            mouth = yawn_det.extract_mouth_roi(frame, face_box)
            yawn_det.update_baseline(mouth)

    nod_det.finalize_baseline()
    yawn_det.finalize_baseline()
    print("[VISION] Calibration OK, pipeline actif")

    # ── Boucle détection ─────────────────────────────────────────────
    import cv2
    fps_alpha = 0.9
    fps = 0.0
    frame_count = 0

    while not _stop_event.is_set():
        t0 = time.time()

        ok, frame = cam.read()
        if not ok or frame is None:
            time.sleep(0.1)
            continue

        img_h, img_w = frame.shape[:2]

        # Détection visage
        if img_w > fl_config.DETECT_WIDTH * 1.5:
            scale = fl_config.DETECT_WIDTH / img_w
            det_frame = cv2.resize(frame, None, fx=scale, fy=scale)
        else:
            det_frame = frame
            scale = 1.0

        dets = detector.detect(det_frame)
        if scale != 1.0 and len(dets) > 0:
            dets[:, :4] /= scale

        face_box = UltraFaceDetector.largest_face(dets)
        face_detected = face_box is not None

        # Head nod
        nod_det.update(face_box, img_h)

        # Bâillement
        if face_box is not None:
            mouth = yawn_det.extract_mouth_roi(frame, face_box)
            yawn_det.update(mouth)

        # Fusion
        level, nc, hds = fusion.update(
            nod_det.nod_count,
            nod_det.is_microsleep,
            nod_det.head_down_duration,
            yawn_det.yawn_count,
        )

        # FPS
        dt = time.time() - t0
        ifps = 1.0 / dt if dt > 0 else 0
        fps = fps * fps_alpha + ifps * (1 - fps_alpha) if frame_count > 0 else ifps
        frame_count += 1

        # Mise à jour thread-safe
        with _lock:
            _data = {
                "fatigue_level": level,
                "fatigue_level_name": fusion.level_name,
                "fatigue_nod_count": nod_det.nod_count,
                "fatigue_yawn_count": yawn_det.yawn_count,
                "fatigue_is_microsleep": nod_det.is_microsleep,
                "fatigue_head_down_sec": round(nod_det.head_down_duration, 1),
                "fatigue_face_detected": face_detected,
                "fatigue_fps": round(fps, 1),
                "fatigue_ok": True,
            }

    cam.release()
    print("[VISION] Pipeline fatigue arrêté")


def read() -> dict:
    """Retourne les données fatigue courantes."""
    with _lock:
        return dict(_data)


def stop():
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)


def cleanup():
    stop()
