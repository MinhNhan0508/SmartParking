"""Camera workers. Each worker owns and releases its VideoCapture handle."""

from collections import Counter, deque
import logging
import sys
import time

import cv2
import numpy as np
from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QImage

logger = logging.getLogger(__name__)


def to_qimage(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, channels = rgb.shape
    return QImage(rgb.data, w, h, w * channels, QImage.Format_RGB888).copy()


class CameraWorker(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    status_signal = pyqtSignal(str)

    def __init__(self, camera_id=0):
        super().__init__()
        self.camera_id = camera_id
        self._is_running = True

    def run(self):
        cap = None
        try:
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.camera_id, backend)
            if not cap.isOpened():
                raise RuntimeError(f"Không mở được camera {self.camera_id}.")
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.capture(cap)
        except Exception as exc:
            logger.exception("Camera worker failed")
            self.status_signal.emit(f"Lỗi camera/AI: {exc}")
        finally:
            if cap is not None:
                cap.release()

    def stop(self):
        self._is_running = False
        if QThread.currentThread() is not self:
            self.wait()


class CameraThread(CameraWorker):
    plate_confirmed_signal = pyqtSignal(str, QImage)

    def capture(self, cap):
        from license_plate_module import recognize_plate_from_image

        votes = deque(maxlen=10)
        frame_count = 0
        while self._is_running:
            started = time.monotonic()
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Không đọc được ảnh từ camera biển số.")
            self.change_pixmap_signal.emit(
                to_qimage(frame).scaled(640, 480, Qt.KeepAspectRatio)
            )
            frame_count += 1
            if frame_count % 3 == 0:
                crop, text = recognize_plate_from_image(frame)
                if crop is not None and text not in (
                    "No Plate",
                    "Unknown",
                    "Error Input",
                    "",
                ):
                    votes.append((text, crop))
                    winner, count = Counter(txt for txt, _ in votes).most_common(1)[0]
                    if count >= 3 and self._is_running:
                        best_crop = next(
                            img for txt, img in reversed(votes) if txt == winner
                        )
                        self.plate_confirmed_signal.emit(winner, to_qimage(best_crop))
                        return
            time.sleep(max(0, 0.03 - (time.monotonic() - started)))


class FaceThread(CameraWorker):
    face_captured_signal = pyqtSignal(np.ndarray)

    def capture(self, cap):
        from mask_detector_module import detect_and_predict_mask

        no_mask_start = None
        last_warning = 0
        frame_count = 0
        locations, predictions = [], []
        while self._is_running:
            started = time.monotonic()
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Không đọc được ảnh từ camera khuôn mặt.")
            frame_count += 1
            if frame_count == 1 or frame_count % 3 == 0:
                locations, predictions = detect_and_predict_mask(frame)
            display = frame.copy()
            unmasked = len(locations) == 1 and len(predictions) == 1
            for (sx, sy, ex, ey), (mask, without_mask) in zip(locations, predictions):
                wearing_mask = mask > without_mask
                unmasked = unmasked and not wearing_mask
                color = (0, 0, 255) if wearing_mask else (0, 255, 0)
                cv2.rectangle(display, (sx, sy), (ex, ey), color, 2)
                cv2.putText(
                    display,
                    "Mask" if wearing_mask else "No Mask",
                    (sx, sy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    2,
                )
                if wearing_mask and time.monotonic() - last_warning > 3:
                    self.status_signal.emit("Vui lòng tháo khẩu trang!")
                    last_warning = time.monotonic()
            if len(locations) > 1 and time.monotonic() - last_warning > 3:
                self.status_signal.emit(
                    "Vui lòng chỉ để một khuôn mặt trong khung hình."
                )
                last_warning = time.monotonic()

            if unmasked:
                if no_mask_start is None:
                    no_mask_start = time.monotonic()
                if time.monotonic() - no_mask_start >= 2:
                    sx, sy, ex, ey = locations[0]
                    h, w = frame.shape[:2]
                    crop = frame[
                        max(0, sy - 40) : min(h, ey + 20),
                        max(0, sx - 20) : min(w, ex + 20),
                    ]
                    if crop.size and self._is_running:
                        self.face_captured_signal.emit(
                            cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                        )
                        return
            else:
                no_mask_start = None
            self.change_pixmap_signal.emit(
                to_qimage(display).scaled(640, 480, Qt.KeepAspectRatio)
            )
            time.sleep(max(0, 0.03 - (time.monotonic() - started)))
