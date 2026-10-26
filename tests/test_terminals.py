"""Exercise the desktop flow using a fake serial port and temporary records.

AI matching is stubbed here; model loading is checked by tools/check_models.py.
"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import cv2
    import numpy as np
    from PyQt5.QtGui import QImage
    from PyQt5.QtWidgets import QApplication, QMessageBox
    import send_vehicle
    import take_vehicle
except ImportError:
    QApplication = None

from parking_store import add_record, read_records, remove_record


@unittest.skipIf(QApplication is None, "Install requirements.txt for desktop tests")
class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "data.csv"
        self.port = MagicMock()
        self.port.is_open = True
        self.port.in_waiting = 0
        patcher = patch("serial.Serial", return_value=self.port)
        patcher.start()
        self.addCleanup(patcher.stop)

    def window(self, module):
        window = module.SmartParkingApp()
        self.addCleanup(window.close)
        window.serial_timer.stop()
        return window

    def test_entry_saves_images_and_csv_before_signalling_success(self):
        window = self.window(send_vehicle)
        window.current_card_id = "AABBCCDD"
        window.plate_input.setText("59A-12345")
        window.date_input.setText("2026-01-21")
        window.time_input.setText("10:00:00")
        window.face_captured = np.zeros((160, 160, 3), dtype=np.uint8)
        window.current_plate_crop_qimage = QImage(120, 60, QImage.Format_RGB888)
        window.current_plate_crop_qimage.fill(0)
        with (
            patch.multiple(
                send_vehicle,
                BASE_DIR=self.root,
                PLATES_DIR=self.root / "plates",
                FACES_DIR=self.root / "faces",
            ),
            patch.object(
                send_vehicle,
                "add_record",
                side_effect=lambda r: add_record(r, self.csv),
            ),
        ):
            window.save_data()
        saved = read_records(self.csv)
        self.assertEqual(saved[0]["card_id"], "AABBCCDD")
        self.assertTrue((self.root / saved[0]["face_path"]).is_file())
        self.assertTrue((self.root / saved[0]["plate_path"]).is_file())
        self.port.write.assert_any_call(b"CMD:SUCCESS\n")

    def test_exit_refreshes_records_and_removes_only_after_face_match(self):
        window = self.window(take_vehicle)
        face = self.root / "face.png"
        cv2.imencode(".png", np.zeros((160, 160, 3), dtype=np.uint8))[1].tofile(
            str(face)
        )
        row = dict(
            card_id="AABBCCDD",
            plate="59A-12345",
            date="2026-01-21",
            time="10:00:00",
            plate_path="plates/test.png",
            face_path=str(face),
        )
        # Window already exists when a new entry is written.
        add_record(row, self.csv)
        embedding = np.zeros(512)
        with (
            patch.object(
                take_vehicle, "read_records", side_effect=lambda: read_records(self.csv)
            ),
            patch.object(
                take_vehicle, "extract_face_embedding", return_value=embedding
            ),
            patch.object(window, "_start_plate_camera_internal"),
        ):
            window._handle_serial_line("UID:AABBCCDD|MODE:OUT")
        self.assertEqual(window.current_card_id, "AABBCCDD")
        self.assertIn("AABBCCDD", window.embB)
        window.plate_input.setText("59A-12345")
        window.face_captured = np.zeros((160, 160, 3), dtype=np.uint8)
        with (
            patch.object(
                take_vehicle, "extract_face_embedding", return_value=embedding
            ),
            patch.object(
                take_vehicle,
                "remove_record",
                side_effect=lambda uid: remove_record(uid, self.csv),
            ),
            patch.object(take_vehicle, "delete_record_images"),
            patch.object(QMessageBox, "information"),
        ):
            window.confirm_take_vehicle()
        self.assertEqual(read_records(self.csv), [])
        self.port.write.assert_any_call(b"CMD:SUCCESS\n")

    def test_failed_exit_storage_never_signals_success(self):
        window = self.window(take_vehicle)
        window.current_card_id = "AABBCCDD"
        window.plate_input.setText("59A-12345")
        window.face_captured = np.zeros((160, 160, 3), dtype=np.uint8)
        window.records_by_id["AABBCCDD"] = {"plate": "59A-12345"}
        window.embB["AABBCCDD"] = np.zeros(512)
        with (
            patch.object(
                take_vehicle, "extract_face_embedding", return_value=np.zeros(512)
            ),
            patch.object(
                window, "_delete_record", side_effect=PermissionError("locked")
            ),
        ):
            window.confirm_take_vehicle()
        self.assertNotIn(
            unittest.mock.call(b"CMD:SUCCESS\n"), self.port.write.call_args_list
        )
        self.assertTrue(window.save_btn.isEnabled())

    def test_reset_cancels_deferred_camera_and_clears_card(self):
        window = self.window(send_vehicle)
        window.current_card_id = "AABBCCDD"
        window.face_start_timer.start(500)
        window.reset_timer.start(3000)
        window.reset_system()
        self.assertFalse(window.face_start_timer.isActive())
        self.assertFalse(window.reset_timer.isActive())
        self.assertIsNone(window.current_card_id)
        self.port.write.assert_any_call(b"CMD:RESET\n")
