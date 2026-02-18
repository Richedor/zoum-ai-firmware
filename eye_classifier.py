"""
Classificateur yeux ouverts/fermés — OCEC (PINTO0309).

Utilise OpenCV DNN pour charger le modèle ONNX directement (le plus portable).
Fallback vers onnxruntime si disponible.
Auto-patch du modèle pour OpenCV < 4.7 (opérateur Squeeze opset 13).

Modèle : ocec_p.onnx (112 KB) — entrée 24×40, sortie prob_open ∈ [0,1]
Repo   : https://github.com/PINTO0309/OCEC
"""
import os
import cv2
import numpy as np
import config


def _patch_onnx_squeeze(model_path: str) -> bool:
    """
    Corrige les nœuds Squeeze à 2 entrées (opset ≥ 13) pour les rendre
    compatibles avec OpenCV DNN < 4.7 (qui attend axes en attribut).
    Modifie le fichier sur disque ; ne tourne qu'une seule fois.
    Nécessite le paquet python3-onnx (``sudo apt install python3-onnx``).
    """
    try:
        import onnx                          # type: ignore
        from onnx import numpy_helper, helper  # type: ignore
    except ImportError:
        print("[EYE] Paquet 'onnx' absent — impossible de patcher le modèle.")
        print("      → sudo apt-get install -y python3-onnx")
        return False

    try:
        model = onnx.load(model_path)
        modified = False
        for node in model.graph.node:
            if node.op_type == "Squeeze" and len(node.input) == 2:
                axes_name = node.input[1]
                axes_vals = None
                for init in model.graph.initializer:
                    if init.name == axes_name:
                        axes_vals = list(numpy_helper.to_array(init).flatten())
                        break
                if axes_vals is not None:
                    del node.input[1]
                    node.attribute.append(
                        helper.make_attribute("axes", axes_vals)
                    )
                    modified = True

        if modified:
            # Sauvegarder le modèle patché
            backup = model_path + ".bak"
            if not os.path.exists(backup):
                os.replace(model_path, backup)
            onnx.save(model, model_path)
            print(f"[EYE] Modèle patché pour OpenCV ≤ 4.6 → {model_path}")
        return modified
    except Exception as ex:
        print(f"[EYE] Échec du patch Squeeze : {ex}")
        return False


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

        dnn_error = None   # conserver le message pour le rapport final

        # ─── Essayer OpenCV DNN d'abord ─────────────────────────────
        try:
            self._net = cv2.dnn.readNetFromONNX(self.model_path)
            self.backend = "opencv_dnn"
            print(f"[EYE] Backend OpenCV DNN chargé ({self.model_path})")
        except Exception as e:
            dnn_error = str(e)
            print(f"[EYE] OpenCV DNN échoué: {e}")

        # ─── Si échec : patcher le modèle puis réessayer ────────────
        if self.backend is None:
            if _patch_onnx_squeeze(self.model_path):
                try:
                    self._net = cv2.dnn.readNetFromONNX(self.model_path)
                    self.backend = "opencv_dnn"
                    print("[EYE] Backend OpenCV DNN chargé (après patch)")
                except Exception as e:
                    dnn_error = str(e)
                    print(f"[EYE] OpenCV DNN toujours échoué après patch: {e}")

        # ─── Fallback onnxruntime ───────────────────────────────────
        if self.backend is None:
            try:
                import onnxruntime as ort  # type: ignore
                self._ort_session = ort.InferenceSession(
                    self.model_path,
                    providers=["CPUExecutionProvider"],
                )
                self._ort_input_name = self._ort_session.get_inputs()[0].name
                self.backend = "onnxruntime"
                print("[EYE] Backend onnxruntime chargé")
            except Exception as e2:
                raise RuntimeError(
                    f"Impossible de charger OCEC :\n"
                    f"  • OpenCV DNN : {dnn_error}\n"
                    f"  • onnxruntime : {e2}\n"
                    f"Vérifiez que {self.model_path} existe.\n"
                    f"Pour patcher le modèle : sudo apt install python3-onnx"
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
