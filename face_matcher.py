# face_utils.py
import torch
import numpy as np
from PIL import Image
from facenet_pytorch import InceptionResnetV1
from functools import lru_cache

# Chọn thiết bị
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# Load model chỉ một lần
@lru_cache(maxsize=1)
def load_face_model():
    return InceptionResnetV1(pretrained="vggface2").eval().to(DEVICE)


def extract_face_embedding(img_rgb: np.ndarray) -> np.ndarray:
    """
    img_rgb: numpy array H×W×3, dtype=uint8, RGB
    Trả về vector embedding 512‑d.
    """
    # Resize & to tensor
    im = Image.fromarray(img_rgb).resize((160, 160))
    # FaceNet's pretrained model expects fixed image standardization.
    x = (np.array(im).astype(np.float32) - 127.5) / 128.0
    x = torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        emb = load_face_model()(x)
    return emb.squeeze().cpu().numpy()


def compare_faces(e1: np.ndarray, e2: np.ndarray, thresh: float = 0.7) -> bool:
    """
    So sánh 2 embedding bằng Euclid distance.
    Trả về True nếu dist < thresh.
    """
    dist = np.linalg.norm(e1 - e2)
    return dist < thresh
