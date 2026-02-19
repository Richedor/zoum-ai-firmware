"""
Détecteur de visages UltraFace — backend NCNN (primaire) + OpenCV DNN (fallback).

Modèle : Ultra-Light-Fast-Generic-Face-Detector-1MB (version-slim 320×240)
Repo   : https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB
"""
import numpy as np
import cv2
import config

# ─── Tentative import ncnn ──────────────────────────────────────────
_HAS_NCNN = False
try:
    import ncnn  # type: ignore
    _HAS_NCNN = True
except ImportError:
    pass


class UltraFaceDetector:
    """
    Détection de visages ultra-légère.
    Input  : 320×240 RGB normalisé
    Output : liste de [x1, y1, x2, y2, score] en coordonnées image originale.
    """

    # ── Constantes du modèle ─────────────────────────────────────────
    STRIDES  = [8.0, 16.0, 32.0, 64.0]
    MIN_BOXES = [
        [10.0, 16.0, 24.0],
        [32.0, 48.0],
        [64.0, 96.0],
        [128.0, 192.0, 256.0],
    ]
    CENTER_VARIANCE = 0.1
    SIZE_VARIANCE   = 0.2
    MEAN_VALS = [127.0, 127.0, 127.0]
    NORM_VALS = [1.0 / 128.0, 1.0 / 128.0, 1.0 / 128.0]

    def __init__(
        self,
        param_path=None,
        bin_path=None,
        input_w=None,
        input_h=None,
        score_threshold=None,
        iou_threshold=None,
        num_threads=None,
    ):
        self.param_path = param_path or config.ULTRAFACE_PARAM
        self.bin_path = bin_path or config.ULTRAFACE_BIN
        self.input_w = input_w or config.DETECT_WIDTH
        self.input_h = input_h or config.DETECT_HEIGHT
        self.score_threshold = score_threshold or config.FACE_SCORE_THRESHOLD
        self.iou_threshold = iou_threshold or config.FACE_IOU_THRESHOLD
        self.num_threads = num_threads or config.NUM_THREADS

        # Générer les ancres a priori
        self.priors = self._generate_priors()

        # Charger le modèle
        self.backend = None
        self._net = None

        if _HAS_NCNN:
            try:
                self._load_ncnn()
                self.backend = "ncnn"
                print(f"[FACE] Backend NCNN chargé ({self.param_path})")
            except Exception as e:
                print(f"[FACE] NCNN échoué: {e}, bascule OpenCV DNN")

        if self.backend is None:
            self._load_opencv_dnn()
            print(f"[FACE] Backend OpenCV DNN chargé")

    # ── Chargement NCNN ──────────────────────────────────────────────
    def _load_ncnn(self):
        net = ncnn.Net()
        net.opt.use_vulkan_compute = False
        net.opt.num_threads = self.num_threads
        net.load_param(self.param_path)
        net.load_model(self.bin_path)
        self._net = net

    # ── Chargement OpenCV DNN (fallback avec le .onnx slim) ──────────
    def _load_opencv_dnn(self):
        import os
        # Chercher un fichier ONNX à côté des fichiers ncnn
        onnx_candidates = [
            os.path.join(config.MODELS_DIR, "version-slim-320.onnx"),
            os.path.join(config.MODELS_DIR, "slim_320.onnx"),
            os.path.join(config.MODELS_DIR, "version-RFB-320.onnx"),
        ]
        onnx_path = None
        for p in onnx_candidates:
            if os.path.isfile(p):
                onnx_path = p
                break
        if onnx_path is None:
            raise FileNotFoundError(
                "Aucun modèle UltraFace trouvé. Lancez download_models.py d'abord."
            )
        self._net = cv2.dnn.readNetFromONNX(onnx_path)
        self.backend = "opencv_dnn"

    # ── Génération des ancres ────────────────────────────────────────
    def _generate_priors(self):
        w, h = self.input_w, self.input_h
        featuremap_w = [int(np.ceil(w / s)) for s in self.STRIDES]
        featuremap_h = [int(np.ceil(h / s)) for s in self.STRIDES]

        priors = []
        for idx in range(len(self.STRIDES)):
            scale_w = w / self.STRIDES[idx]
            scale_h = h / self.STRIDES[idx]
            for j in range(featuremap_h[idx]):
                for i in range(featuremap_w[idx]):
                    x_center = (i + 0.5) / scale_w
                    y_center = (j + 0.5) / scale_h
                    for min_box in self.MIN_BOXES[idx]:
                        bw = min_box / w
                        bh = min_box / h
                        priors.append([
                            np.clip(x_center, 0, 1),
                            np.clip(y_center, 0, 1),
                            np.clip(bw, 0, 1),
                            np.clip(bh, 0, 1),
                        ])
        return np.array(priors, dtype=np.float32)

    # ── Détection principale ─────────────────────────────────────────
    def detect(self, image):
        """
        Détecte les visages dans `image` (BGR, n'importe quelle taille).
        Retourne np.ndarray de forme (N, 5) : [x1, y1, x2, y2, score]
        en coordonnées pixel de l'image originale.
        """
        img_h, img_w = image.shape[:2]

        if self.backend == "ncnn":
            return self._detect_ncnn(image, img_w, img_h)
        else:
            return self._detect_opencv(image, img_w, img_h)

    # ── Inférence NCNN ───────────────────────────────────────────────
    def _detect_ncnn(self, image, img_w, img_h):
        # Préparer l'entrée : BGR→RGB, resize, normaliser
        img = np.ascontiguousarray(image, dtype=np.uint8)
        mat_in = ncnn.Mat.from_pixels_resize(
            img,
            ncnn.Mat.PixelType.PIXEL_BGR2RGB,
            img_w, img_h,
            self.input_w, self.input_h,
        )
        mat_in.substract_mean_normalize(self.MEAN_VALS, self.NORM_VALS)

        ex = self._net.create_extractor()
        ex.set_num_threads(self.num_threads)
        ex.input("input", mat_in)

        _, mat_scores = ex.extract("scores")
        _, mat_boxes = ex.extract("boxes")

        scores = np.array(mat_scores).reshape(-1, 2)
        boxes = np.array(mat_boxes).reshape(-1, 4)

        return self._decode_and_nms(scores, boxes, img_w, img_h)

    # ── Inférence OpenCV DNN ─────────────────────────────────────────
    def _detect_opencv(self, image, img_w, img_h):
        blob = cv2.dnn.blobFromImage(
            image,
            scalefactor=1.0 / 128.0,
            size=(self.input_w, self.input_h),
            mean=(127, 127, 127),
            swapRB=True,
            crop=False,
        )
        self._net.setInput(blob)
        output_names = self._net.getUnconnectedOutLayersNames()
        outputs = self._net.forward(output_names)

        # UltraFace ONNX : sorties nommées 'boxes' (N,4) et 'scores' (N,2)
        # L'ordre dépend du graphe : on identifie par la forme
        boxes_raw = None
        scores_raw = None
        for name, out in zip(output_names, outputs):
            out = out.squeeze(0)  # retirer batch dim
            if name == "boxes" or out.shape[-1] == 4:
                boxes_raw = out.reshape(-1, 4)
            elif name == "scores" or out.shape[-1] == 2:
                scores_raw = out.reshape(-1, 2)

        if boxes_raw is None or scores_raw is None:
            return np.empty((0, 5), dtype=np.float32)

        return self._decode_and_nms(scores_raw, boxes_raw, img_w, img_h)

    # ── Décodage + NMS ───────────────────────────────────────────────
    def _decode_and_nms(self, scores, boxes, img_w, img_h):
        face_scores = scores[:, 1]

        # Filtrage par score
        mask = face_scores > self.score_threshold
        if not np.any(mask):
            return np.empty((0, 5), dtype=np.float32)

        face_scores = face_scores[mask]
        boxes = boxes[mask]
        priors = self.priors[mask]

        # Décodage SSD
        cx = boxes[:, 0] * self.CENTER_VARIANCE * priors[:, 2] + priors[:, 0]
        cy = boxes[:, 1] * self.CENTER_VARIANCE * priors[:, 3] + priors[:, 1]
        w = np.exp(boxes[:, 2] * self.SIZE_VARIANCE) * priors[:, 2]
        h = np.exp(boxes[:, 3] * self.SIZE_VARIANCE) * priors[:, 3]

        x1 = np.clip(cx - w / 2.0, 0, 1) * img_w
        y1 = np.clip(cy - h / 2.0, 0, 1) * img_h
        x2 = np.clip(cx + w / 2.0, 0, 1) * img_w
        y2 = np.clip(cy + h / 2.0, 0, 1) * img_h

        dets = np.stack([x1, y1, x2, y2, face_scores], axis=1)

        # NMS
        keep = self._nms(dets, self.iou_threshold)
        return dets[keep]

    # ── NMS classique ────────────────────────────────────────────────
    @staticmethod
    def _nms(dets, threshold):
        x1 = dets[:, 0]
        y1 = dets[:, 1]
        x2 = dets[:, 2]
        y2 = dets[:, 3]
        scores = dets[:, 4]

        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)

            inds = np.where(ovr <= threshold)[0]
            order = order[inds + 1]

        return keep

    # ── Utilitaire : plus grand visage ───────────────────────────────
    @staticmethod
    def largest_face(detections, min_size=None):
        """Retourne la détection avec la plus grande surface, ou None."""
        min_size = min_size or config.FACE_MIN_SIZE
        if len(detections) == 0:
            return None
        areas = (detections[:, 2] - detections[:, 0]) * (detections[:, 3] - detections[:, 1])
        # Filtrer les visages trop petits
        widths = detections[:, 2] - detections[:, 0]
        heights = detections[:, 3] - detections[:, 1]
        size_mask = (widths >= min_size) & (heights >= min_size)
        if not np.any(size_mask):
            return None
        areas = areas * size_mask
        idx = np.argmax(areas)
        return detections[idx]
