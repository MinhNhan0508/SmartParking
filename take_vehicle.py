import sys
import os
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

from camera_thread import CameraThread, FaceThread
from face_matcher import extract_face_embedding, compare_faces
from search_window import SearchWindow

from app_config import (
    DATA_FILE,
    PLATES_DIR,
    FACES_DIR,
    CAM_ID,
    SERIAL_PORT,
    BAUD_RATE,
    resolve_data_path,
)
from parking_store import read_records, remove_record, delete_record_images
from serial_protocol import SerialLineBuffer, parse_card_event

APP_MODE = "OUT"


class SmartParkingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lấy Xe (Exit Terminal)")
        self.setGeometry(100, 100, 1300, 750)

        # Khởi tạo các biến
        self.plate_thread = None
        self.face_thread = None
        self.face_captured = None
        self.current_plate_crop = None
        self.current_card_id = None

        # Dictionary lưu dữ liệu
        self.records_by_id = {}
        self.records_by_plate = {}
        self.embB = {}

        # Records are loaded when a card is scanned.

        # Kết nối Serial
        self.ser = None
        self.serial_buffer = SerialLineBuffer()
        self._init_serial_connection()

        # Timer đọc Serial
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
            self._load_records()
            rec = self.records_by_id.get(card_id)
            if rec is None:
                self.status_box.append("Thẻ chưa có xe trong bãi.")
                self.send_to_stm32("CMD:ERROR:The Chua Gui")
                return
            self.display_record_info(rec)
        except Exception as exc:
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

    def _load_records(self):
        records_by_id, records_by_plate, embeddings = {}, {}, {}
        for record in read_records():
            card_id, plate = record["card_id"], record["plate"]
            records_by_id[card_id] = record
            records_by_plate[plate] = record
            path = resolve_data_path(record["face_path"])
            if path.is_file():
                image = cv2.imdecode(
                    np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if image is not None:
                    embeddings[card_id] = extract_face_embedding(
                        cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    )
        self.records_by_id = records_by_id
        self.records_by_plate = records_by_plate
        self.embB = embeddings

    def _reload_records(self):
        try:
            self._load_records()
        except Exception as exc:
            self.status_box.append(f"Lỗi tải dữ liệu: {exc}")

    def display_record_info(self, rec):
        """Hiển thị thông tin bản ghi"""
        fp = str(resolve_data_path(rec["face_path"]))
        if os.path.exists(fp):
            pm = QPixmap(fp).scaled(
                self.camera_b_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.camera_b_label.setPixmap(pm)
            self.camera_b_label.setStyleSheet(
                "background: #e0e0e0; border: 1px solid #999;"
            )
        else:
            self.camera_b_label.setText("Ảnh lỗi")

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

        # Nút điều khiển Camera 1
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

        # Camera 2 (Khuôn mặt + ảnh lưu)
        cam2_layout = QVBoxLayout()
        inner_cam2_layout = QHBoxLayout()

        self.camera_a_label = QLabel("Camera 2 (Khuôn mặt)")
        self.camera_a_label.setFixedSize(360, 360)
        self.camera_a_label.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #999;"
        )
        self.camera_a_label.setAlignment(Qt.AlignCenter)

        self.camera_b_label = QLabel("Dữ liệu được lưu")
        self.camera_b_label.setFixedSize(165, 230)
        self.camera_b_label.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #999;"
        )
        self.camera_b_label.setAlignment(Qt.AlignCenter)

        inner_cam2_layout.addWidget(self.camera_a_label)
        inner_cam2_layout.addSpacing(10)
        inner_cam2_layout.addWidget(self.camera_b_label)

        # Nút điều khiển Camera 2
        cam2_buttons = QHBoxLayout()
        self.open_face_btn = QPushButton("Bật Camera Mặt")
        self.open_face_btn.setFixedSize(150, 30)

        cam2_buttons.addStretch()
        cam2_buttons.addWidget(self.open_face_btn)
        cam2_buttons.addStretch()

        cam2_layout.addLayout(inner_cam2_layout)
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
        self.plate_input.setPlaceholderText("Plate")

        self.date_input = QLineEdit()
        self.date_input.setReadOnly(True)
        self.date_input.setFixedSize(180, 30)
        self.date_input.setPlaceholderText("Date")

        self.time_input = QLineEdit()
        self.time_input.setReadOnly(True)
        self.time_input.setFixedSize(180, 30)
        self.time_input.setPlaceholderText("Time")

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

        self.save_btn = QPushButton("Xác nhận")
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
        self.save_btn.clicked.connect(self.confirm_take_vehicle)
        self.search_btn.clicked.connect(self.open_search_window)

    def toggle_plate_camera(self):
        """Bật/tắt camera biển số (chức năng quét lại)"""
        # 1. Chặn nếu chưa có thẻ
        if self.current_card_id is None:
            QMessageBox.warning(self, "Lỗi", "Vui lòng QUẸT THẺ trước!")
            return

        # 2. Logic Bật/Tắt để quét lại
        if self.plate_thread:
            # Nếu đang bật -> Tắt
            self.plate_thread.stop()
            self.plate_thread.wait()  # <--- THÊM WAIT
            self.plate_thread = None
            self.btn_cam_plate.setText("Bật/Quét lại Camera")
            self.status_box.append("🛑 Đã dừng cam.")
        else:
            # Nếu đang tắt -> Bật lại để quét lại
            self.send_to_stm32("CMD:SCAN_PLATE")
            self._start_plate_camera_internal()

    def _start_plate_camera_internal(self):
        """Khởi động camera biển số"""
        self.face_start_timer.stop()
        self.face_captured = None
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread = None
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()  # <--- THÊM WAIT
            self.face_thread = None
            self.camera_a_label.setText("Camera 2 (Khuôn mặt)")

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

        # Dừng các thread camera
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()  # <--- ĐÃ CÓ (OK)
            self.face_thread = None

        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread.wait()  # <--- ĐÃ CÓ (OK)
            self.plate_thread = None
            self.btn_cam_plate.setText("Bật/Quét lại Camera")

        # Xóa dữ liệu hiển thị
        self.plate_input.clear()
        self.date_input.clear()
        self.time_input.clear()

        self.plate_crop_label.clear()
        self.plate_crop_label.setText("Crop")

        self.camera1_label.clear()
        self.camera1_label.setText("Camera 1")

        self.camera_a_label.clear()
        self.camera_a_label.setText("Camera 2")

        self.camera_b_label.clear()
        self.camera_b_label.setText("Dữ liệu lưu")
        self.camera_b_label.setStyleSheet(
            "background: #e0e0e0; border: 1px solid #999;"
        )

        # Reset biến
        self.face_captured = None
        self.current_card_id = None  # <-- Xóa thẻ

        # Bật lại nút Save
        self.save_btn.setEnabled(True)

        self.status_box.append("✅ Sẵn sàng nhận thẻ mới.")

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
        self.plate_input.setText(plate_text)

        now = QDateTime.currentDateTime()
        self.date_input.setText(now.toString("yyyy-MM-dd"))
        self.time_input.setText(now.toString("HH:mm:ss"))

        self.status_box.append(f"✅ Biển số: {plate_text}")

        self.send_to_stm32(f"CMD:PLATE:{plate_text}")

        self.current_plate_crop = crop_img.copy()
        self.plate_crop_label.setPixmap(
            QPixmap.fromImage(crop_img).scaled(
                200, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

        # Dừng camera biển số
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread.wait()  # <--- THÊM WAIT
            self.plate_thread = None
            self.btn_cam_plate.setText("Bật/Quét lại Camera")

        # LOGIC SO SÁNH (Hiển thị cảnh báo nếu sai, cho phép quét lại)
        if self.current_card_id:
            rec = self.records_by_id.get(self.current_card_id)
            if rec and rec["plate"] == plate_text:
                self.status_box.append("✅ Biển số KHỚP! Chuyển sang quét mặt...")
                self.face_start_timer.start(500)
            else:
                self.status_box.append("⚠️ SAI BIỂN SỐ!")
                self.status_box.append("👉 Nhấn nút 'Quét lại' để thử lại.")
                self.send_to_stm32("CMD:ERROR:Sai Bien So")
                # Không chặn cứng, cho phép user nhấn nút Rescan

    def open_face_camera(self):
        """Mở camera mặt thủ công"""
        # Chặn nếu chưa có biển số
        if not self.plate_input.text().strip():
            QMessageBox.warning(self, "Sai quy trình", "Vui lòng quét BIỂN SỐ trước!")
            return
        self._start_face_camera_internal()

    def open_face_camera_auto(self):
        """Tự động mở camera mặt"""
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
            self.face_thread.wait()  # <--- THÊM WAIT
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
        self.camera_a_label.setPixmap(QPixmap.fromImage(qt_img))

    @pyqtSlot(str)
    def update_status(self, msg):
        """Cập nhật trạng thái"""
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

        self.camera_a_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.camera_a_label.size(), Qt.KeepAspectRatio
            )
        )

        self.face_captured = rgb_img
        self.status_box.append("✅ Đã chụp mặt! Bấm 'Xác nhận' để đối chiếu.")

        self.send_to_stm32("CMD:FACE_OK")
        if self.face_thread:
            self.face_thread.stop()
            self.face_thread = None

    def confirm_take_vehicle(self):
        """Xác nhận lấy xe và kiểm tra thông tin"""
        # KHÓA NÚT NGAY TRÁNH SPAM
        self.save_btn.setEnabled(False)

        plate = self.plate_input.text().strip()
        card_id = self.current_card_id

        # CHỐT CHẶN CUỐI
        if not plate:
            self.status_box.append("❌ Chưa có biển số.")
            self.save_btn.setEnabled(True)
            return

        if self.face_captured is None:
            self.status_box.append("❌ Chưa chụp mặt.")
            self.save_btn.setEnabled(True)
            return

        if not card_id:
            self.status_box.append("❌ Chưa quẹt thẻ!")
            self.save_btn.setEnabled(True)
            return

        rec = self.records_by_id.get(card_id)
        if not rec:
            self.send_to_stm32("CMD:ERROR:The la")
            self.status_box.append("❌ Thẻ không tồn tại!")
            self.save_btn.setEnabled(True)
            return

        if rec["plate"] != plate:
            self.status_box.append(f"❌ SAI BIỂN SỐ! Gốc: {rec['plate']}")
            self.send_to_stm32("CMD:ERROR:Sai Bien So")
            QMessageBox.warning(self, "Cảnh báo", "Biển số không khớp!")
            self.save_btn.setEnabled(True)
            return

        embB = self.embB.get(card_id)
        if embB is None:
            self.status_box.append("❌ Không có dữ liệu mặt gốc.")
            self.save_btn.setEnabled(True)
            return

        self.status_box.append("⏳ Đang so sánh...")
        QApplication.processEvents()

        try:
            embA = extract_face_embedding(self.face_captured)
            if compare_faces(embA, embB):
                self.status_box.append("✅ MATCH")
                self._delete_record(card_id)
                self.send_to_stm32("CMD:SUCCESS")
                QMessageBox.information(self, "Thành công", f"Xe {plate} ra cổng.")

                # RESET TOÀN BỘ SAU 2 GIÂY
                self.reset_timer.start(3000)
            else:
                self.status_box.append("❌ MISMATCH: Khuôn mặt không khớp!")
                self.send_to_stm32("CMD:ERROR:Sai Khuon Mat")
                QMessageBox.warning(self, "Cảnh báo", "Khuôn mặt không khớp!")
                self.save_btn.setEnabled(True)

        except Exception as e:
            self.status_box.append(f"❌ Lỗi so sánh: {e}")
            self.save_btn.setEnabled(True)

    def _delete_record(self, card_id):
        removed = remove_record(card_id)
        delete_record_images(removed)
        self.records_by_id.pop(card_id, None)
        self.records_by_plate.pop(removed["plate"], None)
        self.embB.pop(card_id, None)

    def open_search_window(self):
        """Mở cửa sổ tìm kiếm"""
        self.search_win = SearchWindow(str(DATA_FILE), str(PLATES_DIR), str(FACES_DIR))

        # KẾT NỐI TÍN HIỆU
        self.search_win.data_changed_signal.connect(self._reload_records)

        self.search_win.show()

    def closeEvent(self, event):
        """Xử lý khi đóng ứng dụng"""
        self.serial_timer.stop()
        self.face_start_timer.stop()
        self.reset_timer.stop()
        self.send_to_stm32("CMD:RESET")
        if self.plate_thread:
            self.plate_thread.stop()
            self.plate_thread.wait()

        if self.face_thread:
            self.face_thread.stop()
            self.face_thread.wait()

        if self.ser and self.ser.is_open:
            self.ser.close()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SmartParkingApp()
    win.show()
    sys.exit(app.exec_())
