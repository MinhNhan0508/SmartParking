import cv2
import numpy as np
from functools import lru_cache
from ultralytics import YOLO
from app_config import BASE_DIR

# --- 1. CẤU HÌNH & LOAD MODEL ---
PLATE_MODEL_PATH = BASE_DIR / "license_plate_detector.pt"
CHAR_MODEL_PATH = BASE_DIR / "character_detector.pt"


@lru_cache(maxsize=1)
def load_plate_models():
    for path in (PLATE_MODEL_PATH, CHAR_MODEL_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Missing model: {path}")
    return YOLO(str(PLATE_MODEL_PATH)), YOLO(str(CHAR_MODEL_PATH))


# --- 2. TỪ ĐIỂN SỬA LỖI ---
DICT_CHAR_TO_NUM = {
    "D": "0",
    "Q": "0",
    "U": "0",
    "O": "0",
    "C": "0",
    "Z": "2",
    "R": "2",
    "J": "1",
    "I": "1",
    "A": "4",
    "S": "5",
    "G": "6",
    "T": "1",
    "B": "8",
    "E": "6",
}
DICT_NUM_TO_CHAR = {"0": "D", "2": "Z", "4": "A", "5": "S", "6": "G", "8": "B"}


def force_number(char):
    return DICT_CHAR_TO_NUM.get(char, char)


def force_char(char):
    return DICT_NUM_TO_CHAR.get(char, char)


# --- 3. XỬ LÝ ẢNH THÔNG MINH (AUTO-ADJUST C) ---


def get_adaptive_c(image):
    """
    Hàm đo độ nét của ảnh và trả về hệ số c phù hợp.
    Dùng phương pháp Variance of Laplacian.
    """
    # Chuyển sang ảnh xám để tính toán
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Tính phương sai Laplacian (Điểm càng cao ảnh càng nét)
    score = cv2.Laplacian(gray, cv2.CV_64F).var()

    # --- LOGIC TỰ ĐỘNG CHỈNH C ---
    if score < 100:
        c = -1.0  # Ảnh quá mờ -> Làm nét mạnh tay
        # print(f"Blur Score: {score:.1f} -> Mode: MẠNH (c={c})")
    elif score < 300:
        c = -0.7  # Ảnh hơi mờ -> Làm nét vừa
        # print(f"Blur Score: {score:.1f} -> Mode: VỪA (c={c})")
    else:
        c = -0.3  # Ảnh đã nét -> Làm nét nhẹ thôi kẻo nhiễu
        # print(f"Blur Score: {score:.1f} -> Mode: NHẸ (c={c})")

    return c


def sharpen_laplacian(image):
    """Làm nét ảnh với hệ số c tự động"""
    # 1. Tính hệ số c tự động dựa trên độ mờ
    c = get_adaptive_c(image)

    img_float = image.astype(np.float32)
    laplacian = cv2.Laplacian(img_float, cv2.CV_32F, ksize=3)

    # 2. Áp dụng công thức
    g_image = img_float + (c * laplacian)
    g_image = np.clip(g_image, 0, 255).astype(np.uint8)

    return g_image


def preprocess_final(crop_img):
    if crop_img is None or crop_img.size == 0:
        return None
    # 1. Phóng to 2x trước
    upscaled = cv2.resize(crop_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    # 2. Làm nét tự động
    final_img = sharpen_laplacian(upscaled)
    return final_img


def calculate_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    union = boxAArea + boxBArea - interArea
    return interArea / float(union) if union > 0 else 0.0


def clean_overlapping_boxes(chars):
    if len(chars) == 0:
        return []
    chars = sorted(chars, key=lambda x: x[5], reverse=True)
    keep = []
    while len(chars) > 0:
        current = chars.pop(0)
        keep.append(current)
        rest = []
        for item in chars:
            iou = calculate_iou(current[1:5], item[1:5])
            area_item = (item[3] - item[1]) * (item[4] - item[2])
            inter_area = max(
                0, min(current[3], item[3]) - max(current[1], item[1])
            ) * max(0, min(current[4], item[4]) - max(current[2], item[2]))
            ratio_inside = inter_area / area_item if area_item > 0 else 0

            if iou < 0.4 and ratio_inside < 0.8:  # IOU 0.4 là chuẩn
                rest.append(item)
        chars = rest
    return keep


# --- 4. CÁC HÀM NHẬN DIỆN CHÍNH ---


def detect_plate_yolo(frame):
    plate_model, _ = load_plate_models()
    results = plate_model(frame, conf=0.4, imgsz=640, verbose=False)[0]
    if len(results.boxes) == 0:
        return None
    areas = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        areas.append((x2 - x1) * (y2 - y1))
    best_box = results.boxes[np.argmax(areas)]
    x1, y1, x2, y2 = map(int, best_box.xyxy[0])

    h_img, w_img = frame.shape[:2]
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w_img, x2)
    y2 = min(h_img, y2)

    plate_crop = frame[y1:y2, x1:x2]
    return plate_crop if plate_crop.size else None


def read_characters_yolo(plate_img):
    if plate_img is None or plate_img.size == 0:
        return ""
    _, char_model = load_plate_models()
    class_names = char_model.names
    plate_enhanced = preprocess_final(plate_img)
    results = char_model(plate_enhanced, conf=0.35, imgsz=640, verbose=False)[0]
    h_plate, w_plate = plate_enhanced.shape[:2]
    raw_chars = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        label = class_names[cls_id]
        char_h = y2 - y1
        char_w = x2 - x1
        if char_w <= 0 or char_h <= 0:
            continue
        aspect_ratio = char_h / char_w
        if char_h < (h_plate * 0.35):
            continue
        if aspect_ratio < 1.0 or aspect_ratio > 5.0:
            continue
        raw_chars.append((label, x1, y1, x2, y2, conf))

    clean_chars = clean_overlapping_boxes(raw_chars)
    if len(clean_chars) == 0:
        return "Unknown"
    clean_chars.sort(key=lambda k: k[2])
    ys = [c[2] for c in clean_chars]
    mean_y = sum(ys) / len(ys)
    std_y = np.std(ys)

    final_text = ""
    # Biển 2 dòng
    if std_y > (h_plate * 0.15):
        line1 = [c for c in clean_chars if c[2] < mean_y]
        line2 = [c for c in clean_chars if c[2] >= mean_y]
        line1.sort(key=lambda k: k[1])
        line2.sort(key=lambda k: k[1])
        text1 = ""
        for i, item in enumerate(line1):
            char = item[0]
            if i < 2:
                char = force_number(char)
            elif i == 2:
                char = force_char(char)
            text1 += char
        text2 = ""
        for item in line2:
            char = item[0]
            char = force_number(char)
            text2 += char
        final_text = text1 + "-" + text2
    # Biển 1 dòng
    else:
        clean_chars.sort(key=lambda k: k[1])
        text_list = []
        total = len(clean_chars)
        for i, item in enumerate(clean_chars):
            char = item[0]
            if i < 2:
                char = force_number(char)
            elif i == 2:
                char = force_char(char)
            elif i >= (total - 5):
                char = force_number(char)
            text_list.append(char)
        text_full = "".join(text_list)
        if len(text_full) > 3:
            final_text = text_full[:3] + "-" + text_full[3:]
        else:
            final_text = text_full

    return final_text


def recognize_plate_from_image(image_input):
    if isinstance(image_input, str):
        with open(image_input, "rb") as stream:
            numpyarray = np.frombuffer(stream.read(), dtype=np.uint8)
        frame = cv2.imdecode(numpyarray, cv2.IMREAD_UNCHANGED)
    else:
        frame = image_input

    if frame is None:
        return None, "Error Input"

    plate_crop = detect_plate_yolo(frame)
    if plate_crop is None:
        return None, "No Plate"

    plate_text = read_characters_yolo(plate_crop)
    if len(plate_text) < 4:
        return plate_crop, "Unknown"

    return plate_crop, plate_text
