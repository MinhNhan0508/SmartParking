"""CSV persistence with duplicate checks and atomic replacement on update.

Run one terminal at a time on a single shared UART/camera. This is a local
prototype store, not a concurrent multi-lane database.
"""

import csv
import os
from pathlib import Path
import tempfile

from app_config import DATA_FILE, FACES_DIR, PLATES_DIR, resolve_data_path

FIELDS = ["card_id", "plate", "date", "time", "plate_path", "face_path"]


def read_records(csv_path=DATA_FILE):
    path = Path(csv_path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError(f"Invalid CSV header in {path.name}; expected {FIELDS}")
        return list(reader)


def _write_records(records, csv_path):
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=".parking-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(records)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def add_record(record, csv_path=DATA_FILE):
    records = read_records(csv_path)
    if any(r["card_id"] == record["card_id"] for r in records):
        raise ValueError("Thẻ đã có xe trong bãi.")
    if any(r["plate"] == record["plate"] for r in records):
        raise ValueError("Biển số đã có xe trong bãi.")
    _write_records([*records, record], csv_path)


def remove_record(card_id, csv_path=DATA_FILE):
    """Read the latest file so a stale search window cannot erase new rows."""
    records = read_records(csv_path)
    removed = next((r for r in records if r["card_id"] == card_id), None)
    if removed is None:
        raise ValueError("Thẻ không còn tồn tại trong dữ liệu.")
    _write_records([r for r in records if r["card_id"] != card_id], csv_path)
    return removed


def delete_record_images(record):
    """Only remove captured files inside this project's runtime folders."""
    for key, folder in (("plate_path", PLATES_DIR), ("face_path", FACES_DIR)):
        if not record.get(key):
            continue
        path = resolve_data_path(record[key]).resolve()
        if path.is_relative_to(folder.resolve()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # The CSV is already committed; an open preview may hold a file.
                pass
