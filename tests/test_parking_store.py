from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parking_store import add_record, read_records, remove_record


def record(card="AABBCCDD", plate="59A-12345"):
    return dict(
        card_id=card,
        plate=plate,
        date="2026-01-21",
        time="10:00:00",
        plate_path="plates/test.png",
        face_path="faces/test.png",
    )


class ParkingStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data.csv"

    def test_new_store_and_duplicate_card_or_plate(self):
        self.assertEqual(read_records(self.path), [])
        add_record(record(), self.path)
        for duplicate in (record(plate="51B-67890"), record(card="01020304")):
            with self.assertRaises(ValueError):
                add_record(duplicate, self.path)
        self.assertEqual(read_records(self.path), [record()])

    def test_failed_replace_preserves_previous_records(self):
        add_record(record(), self.path)
        before = self.path.read_bytes()
        with patch(
            "parking_store.os.replace", side_effect=PermissionError("file locked")
        ):
            with self.assertRaises(PermissionError):
                add_record(record("01020304", "51B-67890"), self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(".parking-*.tmp")), [])

    def test_deletion_preserves_rows_added_since_search_loaded(self):
        add_record(record(), self.path)
        stale_search = read_records(self.path)
        self.assertEqual(len(stale_search), 1)
        second = record("01020304", "51B-67890")
        add_record(second, self.path)
        self.assertEqual(remove_record("AABBCCDD", self.path), record())
        self.assertEqual(read_records(self.path), [second])

    def test_invalid_header_is_not_overwritten(self):
        self.path.write_text("wrong,columns\na,b\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            add_record(record(), self.path)
        self.assertEqual(self.path.read_text(), "wrong,columns\na,b\n")
