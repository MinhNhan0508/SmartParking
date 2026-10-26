import os
import cv2
import numpy as np
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.models import load_model
from facenet_pytorch import MTCNN
import torch
from functools import lru_cache

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASK_MODEL_PATH = os.path.join(BASE_DIR, "face_mask_detection", "mask_detector.h5")


@lru_cache(maxsize=1)
def load_mask_models():
    if not os.path.isfile(MASK_MODEL_PATH):
        raise FileNotFoundError(f"Missing model: {MASK_MODEL_PATH}")
    # Optimizer state from training is not needed for inference.
    mask_net = load_model(MASK_MODEL_PATH, compile=False)
    detector = MTCNN(image_size=224, margin=0, keep_all=True, device=DEVICE)
    return mask_net, detector


def detect_and_predict_mask(frame):
    maskNet, mtcnn = load_mask_models()
    # Giữ nguyên tỷ lệ, chỉ giảm chiều ngang xuống 400px
    (h, w) = frame.shape[:2]
    new_w = 400
    r = new_w / float(w)
    dim = (new_w, int(h * r))
    resized_frame = cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)

    # 2. Detect Face trên ảnh nhỏ
    rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
    boxes, _ = mtcnn.detect(rgb)

    faces = []
    locs = []

    if boxes is not None:
        for box in boxes:
            # Scale tọa độ box từ ảnh nhỏ về ảnh gốc
            (startX, startY, endX, endY) = (box / r).astype(int)

            startX, startY = max(0, startX), max(0, startY)
            endX, endY = min(w - 1, endX), min(h - 1, endY)

            face = frame[startY:endY, startX:endX]
            if face.size == 0:
                continue

            face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            face = cv2.resize(face, (224, 224))
            face = img_to_array(face)
            face = preprocess_input(face)

            faces.append(face)
            locs.append((startX, startY, endX, endY))

    preds = []
    if len(faces) > 0:
        faces = np.array(faces, dtype="float32")
        preds = maskNet.predict(faces, batch_size=32, verbose=0)

    return locs, preds
