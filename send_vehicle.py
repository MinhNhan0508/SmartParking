import sys
import os
import datetime
import cv2
import numpy as np
import serial

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QWidget,
    QMessageBox,
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer, QDateTime, pyqtSlot

from search_window import SearchWindow
from camera_thread import CameraThread, FaceThread

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


from app_config import (
    BASE_DIR,
    DATA_FILE,
    PLATES_DIR,
    FACES_DIR,
    CAM_ID,
    SERIAL_PORT,
    BAUD_RATE,
)
from parking_store import read_records, add_record
from serial_protocol import SerialLineBuffer, parse_card_event

APP_MODE = "IN"


class SmartParkingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gửi Xe (Entry Terminal)")
        self.setGeometry(100, 100, 1300, 750)

        # Khởi tạo các biến
        self.plate_thread = None
        self.face_thread = None
        self.face_captured = None
        self.current_plate_crop_qimage = None
        self.current_card_id = None

        # Kết nối Serial
        self.ser = None
        self.serial_buffer = SerialLineBuffer()
        self._init_serial_connection()

        # Timer đọc Serial (50ms để phản hồi nhanh)
        self.serial_timer = QTimer(self)
        self.serial_timer.timeout.connect(self.check_serial_data)
        self.serial_timer.start(50)

        self.init_ui()
        self.face_start_timer = QTimer(self)
        self.face_start_timer.setSingleShot(True)
        self.face_start_timer.timeout.connect(self.open_face_camera_auto)
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.reset_system)

    def _init_serial_connection(self):
        """Khởi tạo kết nối Serial với STM32"""
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
            print(f"✅ Đã kết nối STM32 qua {SERIAL_PORT}")
        except Exception as e:
            print(f"❌ Lỗi kết nối Serial: {e}")

    def send_to_stm32(self, command):
        """Gửi lệnh xuống STM32"""
        if self.ser and self.ser.is_open:
            try:
                cmd_str = command + "\n"
                self.ser.write(cmd_str.encode())
                print(f"📤 Sent: {command}")
            except Exception as e:
                print(f"❌ Send Error: {e}")

    def is_card_duplicate(self, card_id):
        return any(row["card_id"] == card_id for row in read_records())

    def _handle_serial_line(self, line):
        event = parse_card_event(line)
        if event is None:
            return
        card_id, hw_mode = event
        if self.current_card_id is not None:
            return
        if hw_mode != APP_MODE:
            self.status_box.append(
                f"Sai chế độ: phần cứng {hw_mode}, ứng dụng {APP_MODE}."
            )
            self.send_to_stm32("CMD:ERROR:Sai Che Do")
            return
        try:
            if self.is_card_duplicate(card_id):
                self.status_box.append("Thẻ đã có xe trong bãi.")
                self.send_to_stm32("CMD:ERROR:Xe Da Ton Tai")
                return
        except (OSError, ValueError) as exc:
            self.status_box.append(f"Lỗi đọc dữ liệu: {exc}")
            self.send_to_stm32("CMD:ERROR:Loi Du Lieu")
            return
        self.current_card_id = card_id
        self.status_box.append(f"Đã nhận thẻ: {card_id}")
        self.send_to_stm32("CMD:SCAN_PLATE")
        self._start_plate_camera_internal()

    def check_serial_data(self):
        if not self.ser or not self.ser.is_open:
            return
        try:
            for line in self.serial_buffer.feed(self.ser.read(self.ser.in_waiting)):
                self._handle_serial_line(line)
        except (serial.SerialException, OSError) as exc:
            self.serial_timer.stop()
            self.status_box.append(
                f"Lỗi Serial: {exc}. Kiểm tra kết nối và mở lại ứng dụng."
            )

    def init_ui(self):
        """Khởi tạo giao diện người dùng"""
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # CSS cho ứng dụng
        main_widget.setStyleSheet("""
            QWidget { background-color: #f5f5f5; font-family: Arial; }
            QLabel { font-size: 14px; }
            QPushButton { background-color: #4CAF50; color: white; border-radius: 5px; padding: 5px; font-size: 14px; }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #cccccc; color: #666666; }
            QPushButton#RetryBtn { background-color: #FF9800; } 
            QPushButton#RetryBtn:hover { background-color: #F57C00; }
            QLineEdit, QTextEdit { border: 1px solid #ccc; border-radius: 5px; padding: 5px; background-color: white; }
        """)

        # --- LAYOUT CAMERA ---
        top_layout = QHBoxLayout()

        # Camera 1 (Biển số)
        cam1_layout = QVBoxLayout()
        self.camera1_label = QLabel("Camera 1 (Biển số)")
        self.camera1_label.setFixedSize(480, 360)
        self.camera1_label.setStyleSheet("background: #e0e0e0; border: 1px solid #999;")
        self.camera1_label.setAlignment(Qt.AlignCenter)

        # Nút điều khiển Camera 1 (Kiêm chức năng Quét lại)
        cam1_buttons = QHBoxLayout()
        self.btn_cam_plate = QPushButton("Bật/Quét lại Camera")
        self.btn_cam_plate.setFixedSize(150, 30)

        self.btn_retry = QPushButton("Reset Toàn Bộ")
        self.btn_retry.setObjectName("RetryBtn")
        self.btn_retry.setFixedSize(120, 30)

        cam1_buttons.addStretch()
        cam1_buttons.addWidget(self.btn_cam_plate)
        cam1_buttons.addSpacing(10)
        cam1_buttons.addWidget(self.btn_retry)
        cam1_buttons.addStretch()

        cam1_layout.addWidget(self.camera1_label)
        cam1_layout.addSpacing(10)
        cam1_layout.addLayout(cam1_buttons)

        # Camera 2 (Khuôn mặt)
        cam2_layout = QVBoxLayout()
        self.camera2_label = QLabel("Camera 2 (Khuôn mặt)")
        self.camera2_label.setFixedSize(480, 360)
        self.camera2_label.setStyleSheet("background: #e0e0e0; border: 1px solid #999;")
        self.camera2_label.setAlignment(Qt.AlignCenter)

        # Nút điều khiển Camera 2 (Bỏ nút Chọn ảnh)
        cam2_buttons = QHBoxLayout()
        self.open_face_btn = QPushButton("Bật Camera Mặt")
        self.open_face_btn.setFixedSize(150, 30)

        cam2_buttons.addStretch()
        cam2_buttons.addWidget(self.open_face_btn)
        cam2_buttons.addStretch()

        cam2_layout.addWidget(self.camera2_label)
        cam2_layout.addSpacing(10)
        cam2_layout.addLayout(cam2_buttons)

        # Thêm camera layouts vào top layout
        top_layout.addStretch()
        top_layout.addLayout(cam1_layout)
        top_layout.addSpacing(20)
        top_layout.addLayout(cam2_layout)
        top_layout.addStretch()

        main_layout.addLayout(top_layout)

        # --- LAYOUT THÔNG TIN ---
        mid_layout = QHBoxLayout()
        mid_layout.addStretch()

        # Bên trái: Ảnh crop và thông tin cơ bản
        left_mid_layout = QHBoxLayout()

        self.plate_crop_label = QLabel("Crop")
        self.plate_crop_label.setFixedSize(200, 150)
        self.plate_crop_label.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #999;"
        )
        self.plate_crop_label.setAlignment(Qt.AlignCenter)

        info_layout = QVBoxLayout()

        self.plate_input = QLineEdit()
        self.plate_input.setReadOnly(True)
        self.plate_input.setFixedSize(180, 30)

        self.date_input = QLineEdit()
        self.date_input.setReadOnly(True)
        self.date_input.setFixedSize(180, 30)

        self.time_input = QLineEdit()
        self.time_input.setReadOnly(True)
        self.time_input.setFixedSize(180, 30)

        info_layout.addWidget(self.plate_input)
        info_layout.addSpacing(5)
        info_layout.addWidget(self.date_input)
        info_layout.addSpacing(5)
        info_layout.addWidget(self.time_input)

        left_mid_layout.addWidget(self.plate_crop_label)
        left_mid_layout.addSpacing(20)
        left_mid_layout.addLayout(info_layout)

        # Bên phải: Status box
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setFixedSize(450, 150)

        mid_layout.addLayout(left_mid_layout)
        mid_layout.addSpacing(30)
        mid_layout.addWidget(self.status_box)
        mid_layout.addStretch()

        main_layout.addLayout(mid_layout)

        # --- LAYOUT NÚT CHỨC NĂNG ---
        bottom_layout = QHBoxLayout()

        self.save_btn = QPushButton("Xác nhận & Lưu")
        self.search_btn = QPushButton("Tìm kiếm")

        self.save_btn.setFixedSize(180, 40)
        self.search_btn.setFixedSize(180, 40)

        bottom_layout.addStretch()
        bottom_layout.addWidget(self.save_btn)
        bottom_layout.addSpacing(50)
        bottom_layout.addWidget(self.search_btn)
        bottom_layout.addStretch()

        main_layout.addSpacing(20)
        main_layout.addLayout(bottom_layout)

        # Kết nối sự kiện
        self._connect_events()

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def _connect_events(self):
        """Kết nối tín hiệu với slot"""
        self.btn_cam_plate.clicked.connect(self.toggle_plate_camera)
        self.btn_retry.clicked.connect(self.reset_system)
        self.open_face_btn.clicked.connect(self.open_face_camera)
        self.save_btn.clicked.connect(self.save_data)
        self.search_btn.clicked.connect(self.open_search_window)

    def toggle_plate_camera(self):
        """Bật/tắt camera biển số (chức năng quét lại)"""
        # CHỐT CHẶN: Kiểm tra đã quét thẻ chưa
        if self.current_card_id is None:
            QMessageBox.warning(self, "Lỗi", "Vui lòng QUẸT THẺ trước!")
            return

        # Logic bật/tắt camera
        if self.plate_thread:
            # Đang bật -> tắt
            self.plate_thread.stop()
            self.plate_thread.wait()  # Chờ tắt hẳn
            self.plate_thread = None
            self.btn_cam_plate.setText("Bật/Quét lại Camera")
            self.status_box.append("🛑 Đã dừng cam biển số.")
        else:
            # Đang tắt -> bật lại (quét lại)
            self.send_to_stm32("CMD:SCAN_PLATE")
            self._start_plate_camera_internal()

    def _start_plate_camera_internal(self):
        """Khởi động camera biển số"""
        self.face_start_timer.stop()
        self.face_captured = None
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread = None
        # Dừng camera mặt nếu đang chạy
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()  # Chờ tắt hẳn
            self.face_thread = None
            self.camera2_label.setText("Camera 2 (Khuôn mặt)")

        self.status_box.append("📷 Đang quét biển số...")

        self.plate_thread = CameraThread(camera_id=CAM_ID)
        self.plate_thread.change_pixmap_signal.connect(self.update_plate_image)
        self.plate_thread.plate_confirmed_signal.connect(self.update_plate_confirmed)
        self.plate_thread.status_signal.connect(self.update_status)
        self.plate_thread.start()

        self.btn_cam_plate.setText("Dừng Camera")

    def reset_system(self):
        """Reset toàn bộ hệ thống về trạng thái ban đầu"""
        self.status_box.append("🔄 Reset hệ thống...")
        self.face_start_timer.stop()
        self.reset_timer.stop()
        self.send_to_stm32("CMD:RESET")

        # Dừng các thread camera (QUAN TRỌNG: CÓ .WAIT())
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()
            self.face_thread = None

        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread.wait()
            self.plate_thread = None
            self.btn_cam_plate.setText("Bật Camera")

        # Xóa dữ liệu hiển thị
        self.plate_input.clear()
        self.date_input.clear()
        self.time_input.clear()

        self.plate_crop_label.clear()
        self.plate_crop_label.setText("Crop")

        self.camera1_label.clear()
        self.camera1_label.setText("Camera 1")

        self.camera2_label.clear()
        self.camera2_label.setText("Camera 2")

        # Reset biến
        self.current_plate_crop_qimage = None
        self.face_captured = None
        self.current_card_id = None

        # Bật lại nút Save
        self.save_btn.setEnabled(True)

        self.status_box.append("✅ Sẵn sàng.")

    @pyqtSlot(QImage)
    def update_plate_image(self, qt_img):
        """Cập nhật hình ảnh từ camera biển số"""
        if self.sender() is not None and self.sender() is not self.plate_thread:
            return
        self.camera1_label.setPixmap(QPixmap.fromImage(qt_img))

    @pyqtSlot(str, QImage)
    def update_plate_confirmed(self, plate_text, crop_img):
        """Xử lý khi nhận diện xong biển số"""
        if self.sender() is not None and self.sender() is not self.plate_thread:
            return
        # Cập nhật thông tin biển số
        self.plate_input.setText(plate_text)

        now = QDateTime.currentDateTime()
        self.date_input.setText(now.toString("yyyy-MM-dd"))
        self.time_input.setText(now.toString("HH:mm:ss"))

        self.status_box.append(f"✅ Biển số: {plate_text}")

        # Gửi biển số xuống STM32
        self.send_to_stm32(f"CMD:PLATE:{plate_text}")

        # Lưu ảnh crop
        self.current_plate_crop_qimage = crop_img.copy()
        self.plate_crop_label.setPixmap(
            QPixmap.fromImage(crop_img).scaled(
                200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

        # Dừng camera biển số
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread.wait()  # Chờ tắt hẳn
            self.plate_thread = None
            self.btn_cam_plate.setText("Quét lại Biển số")

        # Tự động bật camera mặt (auto mode)
        self.face_start_timer.start(500)

    def open_face_camera_auto(self):
        """Tự động mở camera mặt (dùng trong auto mode)"""
        self._start_face_camera_internal()

    def open_face_camera(self):
        """Mở camera mặt thủ công"""
        # CHỐT CHẶN: Phải có biển số
        if not self.plate_input.text().strip():
            QMessageBox.warning(self, "Lỗi", "Vui lòng quét BIỂN SỐ trước!")
            return
        self._start_face_camera_internal()

    def _start_face_camera_internal(self):
        if self.current_card_id is None or not self.plate_input.text().strip():
            return
        self.face_start_timer.stop()
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread = None
        """Khởi động camera mặt"""
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()  # Chờ tắt hẳn
            self.face_thread = None

        self.face_captured = None
        self.status_box.append("📷 Đang bật Cam Mặt...")

        self.send_to_stm32("CMD:SCAN_FACE")

        self.face_thread = FaceThread(camera_id=CAM_ID)
        self.face_thread.change_pixmap_signal.connect(self.update_face_image)
        self.face_thread.face_captured_signal.connect(self.on_face_captured)
        self.face_thread.status_signal.connect(self.update_status)
        self.face_thread.start()

    @pyqtSlot(QImage)
    def update_face_image(self, qt_img):
        """Cập nhật hình ảnh từ camera mặt"""
        if self.sender() is not None and self.sender() is not self.face_thread:
            return
        self.camera2_label.setPixmap(QPixmap.fromImage(qt_img))

    @pyqtSlot(str)
    def update_status(self, msg):
        if self.sender() is not None and self.sender() not in (
            self.plate_thread,
            self.face_thread,
        ):
            return
        self.status_box.append(msg)
        if "khẩu trang" in msg.lower():
            self.send_to_stm32("CMD:MASK_WARN")

    @pyqtSlot(np.ndarray)
    def on_face_captured(self, rgb_img):
        """Xử lý khi chụp được khuôn mặt"""
        if self.sender() is not None and self.sender() is not self.face_thread:
            return
        h, w, ch = rgb_img.shape
        qimg = QImage(rgb_img.data, w, h, w * ch, QImage.Format_RGB888)

        self.camera2_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.camera2_label.size(), Qt.KeepAspectRatio
            )
        )

        self.face_captured = rgb_img
        self.status_box.append("✅ Đã chụp mặt! Bấm 'Xác nhận' để lưu.")

        self.send_to_stm32("CMD:FACE_OK")
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread = None

    def save_data(self):
        self.save_btn.setEnabled(False)
        plate = self.plate_input.text().strip()
        card_id = self.current_card_id
        if (
            not card_id
            or not plate
            or self.face_captured is None
            or self.current_plate_crop_qimage is None
        ):
            QMessageBox.warning(
                self, "Thiếu dữ liệu", "Cần thẻ RFID, biển số và ảnh mặt trước khi lưu."
            )
            self.save_btn.setEnabled(True)
            return
        plate_path = face_path = None
        try:
            PLATES_DIR.mkdir(exist_ok=True)
            FACES_DIR.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            plate_path = PLATES_DIR / f"plate_{card_id}_{timestamp}.png"
            face_path = FACES_DIR / f"face_{card_id}_{timestamp}.png"
            if not self.current_plate_crop_qimage.save(str(plate_path), "PNG"):
                raise OSError("Không lưu được ảnh biển số.")
            ok, encoded = cv2.imencode(
                ".png", cv2.cvtColor(self.face_captured, cv2.COLOR_RGB2BGR)
            )
            if not ok:
                raise OSError("Không mã hóa được ảnh mặt.")
            encoded.tofile(str(face_path))
            add_record(
                {
                    "card_id": card_id,
                    "plate": plate,
                    "date": self.date_input.text(),
                    "time": self.time_input.text(),
                    "plate_path": plate_path.relative_to(BASE_DIR).as_posix(),
                    "face_path": face_path.relative_to(BASE_DIR).as_posix(),
                }
            )
        except (OSError, ValueError, cv2.error) as exc:
            for path in (plate_path, face_path):
                if path is not None:
                    path.unlink(missing_ok=True)
            self.status_box.append(f"Lưu thất bại: {exc}")
            self.send_to_stm32("CMD:ERROR:Loi Luu Du Lieu")
            self.save_btn.setEnabled(True)
            return
        self.send_to_stm32("CMD:SUCCESS")
        self.status_box.append("Đã lưu dữ liệu. WELCOME!")
        self.reset_timer.start(3000)

    def open_search_window(self):
        """Mở cửa sổ tìm kiếm"""
        self.search_win = SearchWindow(str(DATA_FILE), str(PLATES_DIR), str(FACES_DIR))
        self.search_win.show()

    def closeEvent(self, event):
        """Xử lý khi đóng ứng dụng"""
        self.serial_timer.stop()
        self.face_start_timer.stop()
        self.reset_timer.stop()
        self.send_to_stm32("CMD:RESET")
        # SỬA LỖI DESTROYED: THÊM .WAIT()
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread.wait()  # Chờ tắt hẳn

        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()  # Chờ tắt hẳn

        if self.ser and self.ser.is_open:
            self.ser.close()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SmartParkingApp()
    win.show()
    sys.exit(app.exec_())
