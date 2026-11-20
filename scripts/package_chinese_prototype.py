#!/usr/bin/env python3
"""Validate and package the firmware-only simplified Chinese non-dive prototype."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from check_chinese_glyphs import translation_coverage
from verify_update_package import verify_package


WARNING = """非潜水测试用途 — 严禁用于实际潜水
NON-DIVE TEST PROTOTYPE — NOT FOR DIVING

这是 OSTC4 简体中文显示链路的最小原型，不是正式固件发布。
This is a minimal Simplified Chinese display prototype, not an official firmware release.

当前范围 / Current scope:
- 仅包含主固件；不包含 BootLoader、RTE 或 FontPack 更新。
- 当前翻译：{translations}；包含 {glyph_count} 个汉字字模。
- 其他多语言文本继续回退英文；BootLoader 保持英文。
- 尚未完成真机、升级回滚、潜水环境或减压功能验证。

安全要求 / Safety requirements:
- 不得把此原型作为实际潜水的唯一依赖。
- 刷写前备份配置、校准数据和潜水日志。
- 事先准备官方完整升级包并确认恢复路径。
- 仅在受控台面测试中验证，保持供电稳定。

Firmware version: {version}
Source branch: {branch}
Source commit: {commit}
"""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Firmware-only OSTC4 update BIN")
    parser.add_argument("--firmware-bin", required=True, type=Path, help="Just-built raw firmware BIN")
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("dist"))
    return parser.parse_args()


def main():
    args = parse_args()
    if not re.fullmatch(r"[0-9A-Za-z.-]+", args.version):
        raise SystemExit("Version contains unsafe filename characters")
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.commit):
        raise SystemExit("Commit must be a hexadecimal Git SHA")
    report = verify_package(args.input, "firmware", {"firmware": args.firmware_bin}, True)
    embedded_version = report["components"][0]["version"]
    if args.version != embedded_version:
        raise SystemExit(f"Version mismatch: argument={args.version}, firmware={embedded_version}")

    root = Path(__file__).resolve().parents[1]
    if not (root / "NON_DIVE_TEST_PROTOTYPE").is_file():
        raise SystemExit("NON_DIVE_TEST_PROTOTYPE marker is missing")
    actual_commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual_commit != args.commit:
        raise SystemExit(f"Commit mismatch: argument={args.commit}, source={actual_commit}")
    translated_strings, required_glyphs = translation_coverage()
    raw_firmware = args.firmware_bin.read_bytes()
    missing_strings = [string for string in translated_strings if string.encode("utf-8") not in raw_firmware]
    if missing_strings:
        raise SystemExit(f"Firmware does not contain the expected Chinese strings: {missing_strings}")

    name = f"OSTC4-zh-CN-NON-DIVE-TEST-{args.version}-{args.commit[:7]}"
    output_dir = args.output_root / name
    output_dir.mkdir(parents=True, exist_ok=False)
    binary_name = f"OSTC4update_firmware_{args.version}_ZH-CN_NON-DIVE-TEST.bin"
    binary_path = output_dir / binary_name
    shutil.copyfile(args.input, binary_path)

    warning_path = output_dir / "NON-DIVE-TEST.txt"
    warning_path.write_text(WARNING.format(version=args.version, branch=args.branch, commit=args.commit,
                                           translations="、".join(translated_strings),
                                           glyph_count=len(required_glyphs)), encoding="utf-8")
    report["package"] = binary_name
    manifest = {
        "schema": 1,
        "name": name,
        "not_for_diving": True,
        "prototype": "simplified-chinese-minimal",
        "source": {"branch": args.branch, "commit": args.commit},
        "included_components": ["firmware"],
        "excluded_component_updates": ["bootloader", "rte", "fontpack"],
        "translated_strings": translated_strings,
        "chinese_glyph_count": len(required_glyphs),
        "hardware_tested": False,
        "validation": report,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    files = [binary_path, warning_path, manifest_path]
    checksums_path = output_dir / "SHA256SUMS.txt"
    checksums_path.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="ascii")

    archive_path = args.output_root / f"{name}.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files + [checksums_path]:
            archive.write(path, arcname=f"{name}/{path.name}")

    print(f"Prototype package: {archive_path}")
    print(f"Firmware SHA-256: {sha256(binary_path)}")
    print("Validation passed; artifact is explicitly marked NON-DIVE TEST / 非潜水测试用途.")


if __name__ == "__main__":
    main()
