"""
Classificateur yeux ouverts/fermés — OCEC (PINTO0309).

Utilise OpenCV DNN pour charger le modèle ONNX directement (le plus portable).
Fallback vers onnxruntime si disponible.

Modèle : ocec_p.onnx (112 KB) — entrée 24×40, sortie prob_open ∈ [0,1]
Repo   : https://github.com/PINTO0309/OCEC
"""
import cv2
import numpy as np
import config


class EyeClassifier:
    """
    Classification binaire yeux ouverts / fermés.
    prob_open > seuil → ouvert,  sinon → fermé.
    """

    def __init__(self, model_path=None, input_h=None, input_w=None):
        self.model_path = model_path or config.OCEC_ONNX
        self.input_h = input_h or config.OCEC_INPUT_H
        self.input_w = input_w or config.OCEC_INPUT_W
        self.backend = None
        self._net = None

        # Essayer OpenCV DNN d'abord (toujours disponible)
        try:
            self._net = cv2.dnn.readNetFromONNX(self.model_path)
            self.backend = "opencv_dnn"
            print(f"[EYE] Backend OpenCV DNN chargé ({self.model_path})")
        except Exception as e:
            print(f"[EYE] OpenCV DNN échoué: {e}")

        # Fallback onnxruntime
        if self.backend is None:
            try:
                import onnxruntime as ort  # type: ignore
                self._ort_session = ort.InferenceSession(
                    self.model_path,
                    providers=["CPUExecutionProvider"],
                )
                self._ort_input_name = self._ort_session.get_inputs()[0].name
                self.backend = "onnxruntime"
                print(f"[EYE] Backend onnxruntime chargé")
            except Exception as e2:
                raise RuntimeError(
                    f"Impossible de charger OCEC : OpenCV DNN ({e}) / onnxruntime ({e2}). "
                    "Vérifiez que le fichier {self.model_path} existe."
                )

    # ── Prétraitement ────────────────────────────────────────────────
    def _preprocess(self, eye_bgr):
        """BGR crop → float32 NCHW normalisé [0,1]."""
        # Resize à la taille attendue par OCEC
        resized = cv2.resize(eye_bgr, (self.input_w, self.input_h), interpolation=cv2.INTER_LINEAR)
        # BGR → RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # Normaliser [0, 1]
        blob = rgb.astype(np.float32) / 255.0
        # HWC → CHW → NCHW
        blob = blob.transpose(2, 0, 1)[np.newaxis, ...]
        return np.ascontiguousarray(blob, dtype=np.float32)

    # ── Inférence ────────────────────────────────────────────────────
    def classify(self, eye_bgr):
        """
        Classifie un crop d'œil BGR.
        Retourne float prob_open ∈ [0, 1].
        """
        if eye_bgr is None or eye_bgr.size == 0:
            return -1.0  # invalide

        blob = self._preprocess(eye_bgr)

        if self.backend == "opencv_dnn":
            self._net.setInput(blob)
            output = self._net.forward()
            prob_open = float(np.squeeze(output))
        elif self.backend == "onnxruntime":
            outputs = self._ort_session.run(None, {self._ort_input_name: blob})
            prob_open = float(np.squeeze(outputs[0]))
        else:
            return -1.0

        return float(np.clip(prob_open, 0.0, 1.0))

    def is_open(self, prob_open, threshold=None):
        """Retourne True si prob_open dépasse le seuil."""
        threshold = threshold or config.EYE_OPEN_THRESHOLD
        return prob_open >= threshold


def extract_eye_rois(image, face_box):
    """
    Extrait les ROI œil gauche et droit à partir du bbox visage.
    Heuristique sans landmarks : zone haute du visage.

    Args:
        image   : image BGR complète
        face_box: [x1, y1, x2, y2, score] (coordonnées pixel)

    Returns:
        (left_eye_crop, right_eye_crop) — crops BGR, ou None si invalide
    """
    x1, y1, x2, y2 = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
    fw = x2 - x1
    fh = y2 - y1

    if fw < 20 or fh < 20:
        return None, None

    img_h, img_w = image.shape[:2]

    def _crop(rx1, ry1, rx2, ry2):
        """Extrait un crop relatif au bbox visage."""
        cx1 = max(int(x1 + rx1 * fw), 0)
        cy1 = max(int(y1 + ry1 * fh), 0)
        cx2 = min(int(x1 + rx2 * fw), img_w)
        cy2 = min(int(y1 + ry2 * fh), img_h)
        if cx2 <= cx1 or cy2 <= cy1:
            return None
        return image[cy1:cy2, cx1:cx2].copy()

    left_eye = _crop(config.EYE_LEFT_X1, config.EYE_LEFT_Y1,
                      config.EYE_LEFT_X2, config.EYE_LEFT_Y2)
    right_eye = _crop(config.EYE_RIGHT_X1, config.EYE_RIGHT_Y1,
                       config.EYE_RIGHT_X2, config.EYE_RIGHT_Y2)

    return left_eye, right_eye
