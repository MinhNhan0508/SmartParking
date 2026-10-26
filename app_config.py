"""Shared paths and environment configuration for both parking terminals."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.csv"
PLATES_DIR = BASE_DIR / "plates"
FACES_DIR = BASE_DIR / "faces"
SERIAL_PORT = os.getenv("PARKING_SERIAL_PORT", "COM11")
BAUD_RATE = int(os.getenv("PARKING_BAUD_RATE", "115200"))
CAM_ID = int(os.getenv("PARKING_CAMERA_ID", "0"))


def resolve_data_path(path):
    """Resolve portable CSV image paths relative to this repository."""
    value = Path(path)
    return value if value.is_absolute() else BASE_DIR / value
