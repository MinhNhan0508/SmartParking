"""Build the canonical STM32 firmware without Eclipse workspace metadata.

Requires GNU Arm Embedded/STM32 toolchain on PATH, or --compiler /path/to/gcc.
Build outputs are placed in the ignored .tools/firmware-build directory.
"""

import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "STM32CubeIDE/workspace_doan2/STMProject"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=shutil.which("arm-none-eabi-gcc"))
    args = parser.parse_args()
    compiler = args.compiler
    if not compiler:
        candidates = sorted(
            Path("C:/ST").glob(
                "*/STM32CubeIDE/plugins/*gnu-tools*/tools/bin/arm-none-eabi-gcc.exe"
            )
        )
        if candidates:
            compiler = str(candidates[-1])
    if not compiler:
        parser.error("Add arm-none-eabi-gcc to PATH or supply --compiler.")
    build = ROOT / ".tools/firmware-build"
    build.mkdir(parents=True, exist_ok=True)
    common = ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"]
    includes = [
        PROJECT / p
        for p in (
            "Core/Inc",
            "Drivers/STM32F4xx_HAL_Driver/Inc",
            "Drivers/STM32F4xx_HAL_Driver/Inc/Legacy",
            "Drivers/CMSIS/Device/ST/STM32F4xx/Include",
            "Drivers/CMSIS/Include",
        )
    ]
    flags = [
        *common,
        "-std=gnu11",
        "-Os",
        "-g3",
        "-Wall",
        "-Wextra",
        "-Wno-unused-parameter",
        "-ffunction-sections",
        "-fdata-sections",
        "-DUSE_HAL_DRIVER",
        "-DSTM32F407xx",
        "--specs=nano.specs",
    ]
    flags.extend(f"-I{path}" for path in includes)
    hal = PROJECT / "Drivers/STM32F4xx_HAL_Driver/Src"
    modules = (
        "hal",
        "hal_cortex",
        "hal_dma",
        "hal_flash",
        "hal_flash_ex",
        "hal_flash_ramfunc",
        "hal_gpio",
        "hal_i2c",
        "hal_pwr",
        "hal_pwr_ex",
        "hal_rcc",
        "hal_rcc_ex",
        "hal_spi",
        "hal_uart",
    )
    sources = sorted((PROJECT / "Core/Src").glob("*.c"))
    sources += [hal / f"stm32f4xx_{module}.c" for module in modules]
    sources += sorted((PROJECT / "Core/Startup").glob("*.s"))
    objects = []
    for source in sources:
        obj = build / f"{source.stem}.o"
        subprocess.run(
            [compiler, *flags, "-c", str(source), "-o", str(obj)], check=True
        )
        objects.append(str(obj))
    target = build / "SmartParking.elf"
    subprocess.run(
        [
            compiler,
            *common,
            "--specs=nano.specs",
            "--specs=nosys.specs",
            f"-T{PROJECT / 'STM32F407VGTX_FLASH.ld'}",
            "-Wl,--gc-sections",
            f"-Wl,-Map={build / 'SmartParking.map'}",
            *objects,
            "-lc",
            "-lm",
            "-o",
            str(target),
        ],
        check=True,
    )
    size = Path(compiler).with_name(Path(compiler).name.replace("gcc", "size"))
    subprocess.run([str(size), str(target)], check=True)
    print(f"Built {target}")


if __name__ == "__main__":
    main()
