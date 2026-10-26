# Maintenance validation

Validation performed on 26 October 2026, separately from the original report's January 2026 demonstration.

## Automated checks

- A clean Python 3.10 virtual environment resolves and installs `requirements.txt`; the installed packages pass the dependency compatibility check.
- Twelve unit/desktop tests cover UART fragmentation, multiple incoming lines, malformed/overlong messages, duplicate records, atomic-write failure, stale search deletion, entry image/CSV persistence, fresh check-out records, failed check-out persistence, and cancellation of deferred camera/reset actions.
- Desktop flow tests use a mocked serial port and synthetic images in temporary directories. They do not operate the physical prototype and do not measure identity accuracy.
- The bundled plate model (one class), character model (32 classes), and mask classifier (two outputs) load and execute synthetic inference. MTCNN initializes on the CPU.
- FaceNet's VGGFace2 weights download into the local cache and produce a finite 512-dimensional embedding; comparing the embedding with itself succeeds. This checks model operation, not identity discrimination.
- The canonical firmware compiles and links with GNU Tools for STM32 14.3.rel1, using the supplied HAL/CMSIS drivers. The maintained build uses approximately 15 KB of flash and 3.4 KB of static RAM; `tools/build_firmware.py` prints the exact sizes for the installed compiler.

## Changes requiring a physical retest

The original report's images are retained as historical demonstration evidence. The maintained firmware/application should be retested together on the board:

1. Verify the pin map, LCD address, HSE oscillator, adapter COM port and camera index.
2. Flash `STMProject`, confirm IN is selected, and check that holding PA0 changes mode only once.
3. In the check-in terminal, scan a card, recognize a plate, capture one unmasked face and save. Confirm CSV/images and the yellow LED/LCD result.
4. Close check-in, select OUT and open check-out. Verify that the same card/plate/person succeeds and removes the active record/images.
5. Repeat with an unknown card, wrong mode, wrong plate, masked face and different person; confirm rejection and red LED/buzzer where applicable.
6. Reset during plate/face capture and disconnect/reconnect the UART to verify recovery.

Face preprocessing now follows the pretrained FaceNet model's fixed image standardization, `(pixel - 127.5) / 128`. Stored face images are re-embedded when records load. Recalibrate the Euclidean-distance threshold (default `0.7`) with representative matching and nonmatching samples before relying on the identity decision. No new false-accept/false-reject rate is claimed.
