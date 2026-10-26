"""Load bundled models and run synthetic inference without a camera or board.

Use --face to also load FaceNet; its pretrained weights download on first use.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--face", action="store_true")
    args = parser.parse_args()
    import numpy as np
    from license_plate_module import load_plate_models
    from mask_detector_module import load_mask_models

    for model in load_plate_models():
        model(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False)
        print(f"YOLO OK: {len(model.names)} classes")
    mask, detector = load_mask_models()
    result = mask.predict(np.zeros((1, 224, 224, 3), dtype=np.float32), verbose=0)
    assert result.shape == (1, 2) and np.isfinite(result).all()
    print(
        f"Mask classifier OK: output {result.shape}; MTCNN loaded on {detector.device}"
    )
    if args.face:
        from face_matcher import extract_face_embedding, compare_faces

        embedding = extract_face_embedding(np.zeros((160, 160, 3), dtype=np.uint8))
        assert embedding.shape == (512,) and np.isfinite(embedding).all()
        assert compare_faces(embedding, embedding)
        print("FaceNet OK: 512-dimensional embedding")


if __name__ == "__main__":
    main()
