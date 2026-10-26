# Components and model attribution

This academic project integrates the following components. Their upstream terms remain applicable; bundling them here does not replace their original licenses.

| Component | Use / source |
| --- | --- |
| STM32 HAL | Peripheral drivers from STM32Cube F4 V1.28.0; `Drivers/STM32F4xx_HAL_Driver/LICENSE.txt` |
| Arm CMSIS and STM32 device support | Cortex-M4/device headers; license files under `Drivers/CMSIS/` |
| MFRC522 and HD44780 helper drivers | Existing custom drivers retained from the supplied project in `Core/Src/` and `Core/Inc/`; original headers preserved |
| Ultralytics YOLO | Plate and character inference; https://github.com/ultralytics/ultralytics |
| facenet-pytorch | MTCNN and InceptionResnetV1/VGGFace2 pretrained weights; https://github.com/timesler/facenet-pytorch |
| TensorFlow / Keras | MobileNetV2 mask classifier and training notebook; https://www.tensorflow.org/ |
| OpenCV | Camera access and image processing; https://opencv.org/ |
| PyQt5 | Desktop interface; https://www.riverbankcomputing.com/software/pyqt/ |

`license_plate_detector.pt`, `character_detector.pt`, and `face_mask_detection/mask_detector.h5` are the supplied project model artifacts. The mask training notebook is included. The original plate training datasets, full training configuration and dataset licenses are not included; no additional provenance or redistribution rights are claimed here.

The original report, schematic, and screenshots are supplied project materials. A project-wide open-source license for the authors' own code and materials has not been selected.
