import base64
import cv2
import numpy as np
from insightface.app import FaceAnalysis

class Helpers:
    def __init__(self, face_app: FaceAnalysis):
        self.face_app = face_app

    def base64_to_cv2(self, b64_str: str):
        try:
            if "," in b64_str:
                b64_str = b64_str.split(",")[1]
            img_bytes = base64.b64decode(b64_str)
            arr = np.frombuffer(img_bytes, np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def get_embedding(self, img) -> np.ndarray | None:
        faces = self.face_app.get(img)
        if not faces:
            return None
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
        return face.normed_embedding

    @staticmethod
    def embedding_to_list(emb: np.ndarray) -> list:
        return emb.tolist()

    @staticmethod
    def list_to_embedding(lst: list) -> np.ndarray:
        return np.array(lst, dtype=np.float32)