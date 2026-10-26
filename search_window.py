from app_config import resolve_data_path
from parking_store import read_records, remove_record, delete_record_images
import os
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QCheckBox,
    QMessageBox,
    QHeaderView,
    QFrame,
    QStyledItemDelegate,
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt, pyqtSignal  # <--- Thêm pyqtSignal


class ElidedItemDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.textElideMode = Qt.ElideRight


class SearchWindow(QWidget):
    # Tín hiệu báo dữ liệu thay đổi để take_vehicle cập nhật
    data_changed_signal = pyqtSignal()

    def __init__(self, csv_path, plates_dir, faces_dir):
        super().__init__()
        self.setWindowTitle("License Plate Search")
        self.setGeometry(200, 100, 1200, 600)

        self.csv_path = csv_path
        self.plates_dir = plates_dir
        self.faces_dir = faces_dir
        self.data = []

        # Layout
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

        # Filters
        filter_layout = QHBoxLayout()

        checkbox_layout = QVBoxLayout()
        self.plate_checkbox = QCheckBox("Lookup by plate number")
        self.date_checkbox = QCheckBox("Lookup by date")
        self.plate_checkbox.setChecked(True)
        checkbox_layout.addWidget(self.plate_checkbox)
        checkbox_layout.addWidget(self.date_checkbox)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(
            "border: 1px dashed gray; margin-left: 10px; margin-right: 10px;"
        )

        right_filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nhập từ khóa tìm kiếm...")
        self.search_btn = QPushButton("Search")
        self.reload_btn = QPushButton("Reload")
        self.delete_btn = QPushButton("Delete")

        right_filter_layout.addWidget(self.search_input, stretch=1)
        right_filter_layout.addWidget(self.search_btn)
        right_filter_layout.addWidget(self.reload_btn)
        right_filter_layout.addWidget(self.delete_btn)

        filter_layout.addLayout(checkbox_layout)
        filter_layout.addWidget(line)
        filter_layout.addLayout(right_filter_layout)

        self.table = QTableWidget()
        self.table.setItemDelegate(ElidedItemDelegate())

        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Card ID", "Plate", "Date", "Time", "Plate Img", "Face Img"]
        )

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        left_layout.addWidget(line)
        left_layout.addLayout(filter_layout)
        left_layout.addWidget(self.table)

        preview_font = QFont("Arial", 11, QFont.Bold)

        self.plate_label = QLabel("Plate Preview")
        self.plate_label.setFont(preview_font)
        self.plate_pix = QLabel()
        self.plate_pix.setFixedSize(170, 120)
        self.plate_pix.setStyleSheet(
            "background-color: lightgray; border: 1px solid black;"
        )
        self.plate_pix.setAlignment(Qt.AlignCenter)

        self.face_label = QLabel("Face Preview")
        self.face_label.setFont(preview_font)
        self.face_pix = QLabel()
        self.face_pix.setFixedSize(165, 230)
        self.face_pix.setStyleSheet(
            "background-color: lightgray; border: 1px solid black;"
        )
        self.face_pix.setAlignment(Qt.AlignCenter)

        self.info_id = QLineEdit()
        self.info_id.setReadOnly(True)
        self.info_id.setPlaceholderText("Card ID")

        self.info_plate = QLineEdit()
        self.info_plate.setReadOnly(True)
        self.info_plate.setPlaceholderText("Number Plate")
        self.info_date = QLineEdit()
        self.info_date.setReadOnly(True)
        self.info_date.setPlaceholderText("Date")
        self.info_time = QLineEdit()
        self.info_time.setReadOnly(True)
        self.info_time.setPlaceholderText("Time")

        for box in (self.info_id, self.info_plate, self.info_date, self.info_time):
            box.setFixedWidth(240)

        right_layout.addWidget(self.plate_label)
        right_layout.addWidget(self.plate_pix)
        right_layout.addSpacing(10)
        right_layout.addWidget(self.face_label)
        right_layout.addWidget(self.face_pix)
        right_layout.addSpacing(10)
        right_layout.addWidget(self.info_id)
        right_layout.addWidget(self.info_plate)
        right_layout.addWidget(self.info_date)
        right_layout.addWidget(self.info_time)

        main_layout.addLayout(left_layout)
        main_layout.addSpacing(20)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        self.search_btn.clicked.connect(self.apply_filter)
        self.reload_btn.clicked.connect(self.load_csv)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.table.cellClicked.connect(self.show_preview)

        self.load_csv()

    def load_csv(self):
        try:
            self.data = read_records(self.csv_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Lỗi dữ liệu", str(exc))
            return
        self.apply_filter()

    def apply_filter(self):
        self.table.setRowCount(0)
        keyword = self.search_input.text().lower().strip()
        by_plate = self.plate_checkbox.isChecked()
        by_date = self.date_checkbox.isChecked()

        for row in self.data:
            card_id = row.get("card_id", "N/A")
            plate = row.get("plate", "")
            date = row.get("date", "")
            time_ = row.get("time", "")
            plate_path = row.get("plate_path", "")
            face_path = row.get("face_path", "")

            show = False
            if keyword == "":
                show = True
            elif by_plate and keyword in plate.lower():
                show = True
            elif by_date and keyword in date.lower():
                show = True
            elif keyword in card_id.lower():
                show = True

            if show:
                i = self.table.rowCount()
                self.table.insertRow(i)

                self.table.setItem(i, 0, QTableWidgetItem(card_id))
                self.table.setItem(i, 1, QTableWidgetItem(plate))
                self.table.setItem(i, 2, QTableWidgetItem(self.format_date(date)))
                self.table.setItem(i, 3, QTableWidgetItem(time_))

                item_plate = QTableWidgetItem(plate_path)
                item_face = QTableWidgetItem(face_path)
                item_plate.setToolTip(plate_path)
                item_face.setToolTip(face_path)

                self.table.setItem(i, 4, item_plate)
                self.table.setItem(i, 5, item_face)

    def format_date(self, d):
        try:
            parts = d.split("-")
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
        except:
            pass
        return d

    def show_preview(self, row, _):
        card_id = self.table.item(row, 0).text()
        plate = self.table.item(row, 1).text()
        date = self.table.item(row, 2).text()
        time = self.table.item(row, 3).text()
        plate_path = str(resolve_data_path(self.table.item(row, 4).text()))
        face_path = str(resolve_data_path(self.table.item(row, 5).text()))

        if os.path.exists(plate_path):
            self.plate_pix.setPixmap(
                QPixmap(plate_path).scaled(
                    self.plate_pix.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        else:
            self.plate_pix.clear()
            self.plate_pix.setText("Ảnh lỗi")

        if os.path.exists(face_path):
            self.face_pix.setPixmap(
                QPixmap(face_path).scaled(
                    self.face_pix.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        else:
            self.face_pix.clear()
            self.face_pix.setText("Ảnh lỗi")

        self.info_id.setText(card_id)
        self.info_plate.setText(plate)
        self.info_date.setText(date)
        self.info_time.setText(time)

    def delete_selected(self):
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(
                self, "Chưa chọn dữ liệu", "Vui lòng chọn một dòng để xóa."
            )
            return
        card_id = self.table.item(selected, 0).text()
        if (
            QMessageBox.question(
                self,
                "Xác nhận",
                "Xóa bản ghi và ảnh đã chọn?",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            removed = remove_record(card_id, self.csv_path)
            delete_record_images(removed)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Lỗi", str(exc))
            return
        self.load_csv()
        for widget in (
            self.plate_pix,
            self.face_pix,
            self.info_id,
            self.info_plate,
            self.info_date,
            self.info_time,
        ):
            widget.clear()
        self.data_changed_signal.emit()

    # Thêm sự kiện khi đóng cửa sổ thì cũng báo cập nhật lại cho chắc
    def closeEvent(self, event):
        self.data_changed_signal.emit()
        event.accept()
