#!/usr/bin/env python3
"""Independently validate an OSTC4 update package without modifying it."""

import argparse
import json
import struct
from pathlib import Path


PACKAGE_TYPES = {
    "all": (("firmware", "fontpack", "rte"),),
    "rte": (("firmware", "rte"),),
    "fontpack": (("firmware", "fontpack"),),
    "firmware": (("firmware",),),
    "bootloader": (("firmware", "bootloader"), ("bootloader",)),
    "rteonly": (("rte",),),
    "fontpackonly": (("fontpack",),),
}

COMPONENTS = {
    "firmware": {
        "marker": 0xFF004857,
        "base": 0x08040000,
        "version_offset": 0x10000,
        "magic": 0xEE,
        "max_payload": 768000,
    },
    "fontpack": {
        "marker": 0x10000320,
        "base": 0x08132000,
        "version_offset": 0x00000,
        "magic": 0xF0,
        "max_payload": 0x081E0000 - 0x08132000,
    },
    "rte": {
        "marker": 0xFE525445,
        "base": 0x08000000,
        "version_offset": 0x05000,
        "magic": 0xE2,
        "max_payload": 0x080000,
    },
    "bootloader": {
        "marker": 0x10000000,
        "base": 0x08000000,
        "version_offset": 0x0A000,
        "magic": 0xEE,
        "max_payload": 0x20000,
    },
}


class PackageValidationError(ValueError):
    """Raised when an update package fails a structural or content check."""


def require(condition, message):
    if not condition:
        raise PackageValidationError(message)


def stm32_crc32(payload):
    """Match the OSTC4 STM32 word-oriented, non-reflected CRC-32."""
    require(len(payload) % 4 == 0, "CRC input must contain complete 32-bit words")
    crc = 0xFFFFFFFF
    for offset in range(0, len(payload), 4):
        word = int.from_bytes(payload[offset:offset + 4], "little")
        for shift in (24, 16, 8, 0):
            crc ^= ((word >> shift) & 0xFF) << 24
            for _ in range(8):
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def package_fletcher(payload):
    low = 0
    high = 0
    for value in payload:
        low = (low + value) & 0xFFFF
        high = (high + low) & 0xFFFF
    return struct.pack("<HH", low, high)


def bootloader_fletcher(payload):
    require(len(payload) == 0x1FFF0, "BootLoader Fletcher input must be 0x1FFF0 bytes")
    low = 0
    high = 0
    for (word,) in struct.iter_unpack("<H", payload):
        low = (low + word) & 0xFFFF
        high = (high + low) & 0xFFFF
    return (high << 16) | low


def version_string(payload, offset):
    first, second, third, beta = payload[offset:offset + 4]
    return f"{first}.{second}.{third}{'-beta' if beta else ''}"


def check_version(component, payload):
    spec = COMPONENTS[component]
    offset = spec["version_offset"]
    require(len(payload) >= offset + 0x40, f"{component}: payload is too short for SFirmwareData")
    expected_magic = bytes((0x00, 0x00, spec["magic"], 0xFF))
    require(payload[offset + 0x3C:offset + 0x40] == expected_magic,
            f"{component}: invalid SFirmwareData magic at payload offset 0x{offset + 0x3C:X}")
    return version_string(payload, offset)


def check_bootloader(payload):
    require(len(payload) == 0x20000, "bootloader: padded payload must be exactly 0x20000 bytes")
    require(payload[0x1FFF0:0x1FFF4] == b"\x00" * 4, "bootloader: reserved block is not zero")
    require(int.from_bytes(payload[0x1FFF4:0x1FFF8], "big") == 0x100,
            "bootloader: invalid internal block type")
    expected = bootloader_fletcher(payload[:0x1FFF0])
    stored = int.from_bytes(payload[0x1FFF8:0x1FFFC], "big")
    require(stored == expected, f"bootloader: internal Fletcher mismatch (stored 0x{stored:08X}, computed 0x{expected:08X})")
    original_length = int.from_bytes(payload[0x1FFFC:0x20000], "big")
    require(0 < original_length <= 0x1FFF0, "bootloader: invalid original image length")
    require(payload[original_length:0x1FFF0] == b"\xFF" * (0x1FFF0 - original_length),
            "bootloader: padding before the internal block is not entirely 0xFF")
    require(payload[0xA040:0xA080] == b"\xFF" * 64,
            "bootloader: manufacturing-data placeholder is not blank")
    return original_length


def verify_package(package_path, package_type, raw_paths=None, require_all_raw=False):
    raw_paths = raw_paths or {}
    data = Path(package_path).read_bytes()
    require(len(data) >= 24, "Package is too short")
    require(len(data) <= 2000004, "Package exceeds the final packer's 2,000,000-byte input buffer")
    require(package_fletcher(data[:-4]) == data[-4:], "Final package Fletcher checksum mismatch")

    expected_component_sequences = PACKAGE_TYPES[package_type]
    components = []
    offset = 0
    package_end = len(data) - 4
    while offset < package_end:
        require(package_end - offset >= 20, f"Truncated segment header at offset 0x{offset:X}")
        length = int.from_bytes(data[offset:offset + 4], "big")
        marker = int.from_bytes(data[offset + 4:offset + 8], "big")
        header_checksum = int.from_bytes(data[offset + 8:offset + 12], "little")
        header_version = data[offset + 12:offset + 16]
        require(length > 0 and length % 4 == 0, f"Invalid payload length {length} at offset 0x{offset:X}")
        require(header_checksum == (length + marker) & 0xFFFFFFFF,
                f"Segment header checksum mismatch at offset 0x{offset:X}")
        payload_start = offset + 16
        payload_end = payload_start + length
        require(payload_end + 4 <= package_end, f"Truncated payload at offset 0x{offset:X}")
        payload = data[payload_start:payload_end]
        stored_crc = int.from_bytes(data[payload_end:payload_end + 4], "big")
        computed_crc = stm32_crc32(payload)
        require(stored_crc == computed_crc,
                f"Segment CRC mismatch at offset 0x{offset:X} (stored 0x{stored_crc:08X}, computed 0x{computed_crc:08X})")

        matches = [name for name, spec in COMPONENTS.items() if spec["marker"] == marker]
        require(len(matches) == 1, f"Unknown component marker 0x{marker:08X} at offset 0x{offset:X}")
        component = matches[0]
        spec = COMPONENTS[component]
        require(length <= spec["max_payload"], f"{component}: payload exceeds its flash-region limit")
        require(length <= 1050000, f"{component}: payload exceeds OSTC4pack_V4's input buffer")

        version = check_version(component, payload)
        header_version_offset = 0 if component in ("fontpack", "bootloader") else spec["version_offset"]
        require(header_version == payload[header_version_offset:header_version_offset + 4],
                f"{component}: segment-header version does not match its payload")
        report = {
            "component": component,
            "offset": offset,
            "payload_size": length,
            "target_address": f"0x{spec['base']:08X}",
            "version": version,
            "crc32": f"0x{computed_crc:08X}",
        }

        original_length = None
        if component == "bootloader":
            original_length = check_bootloader(payload)
            report["original_image_size"] = original_length

        raw_path = raw_paths.get(component)
        if raw_path:
            raw = Path(raw_path).read_bytes()
            if component == "bootloader":
                require(original_length == len(raw), "bootloader: original length in package does not match raw BIN")
                require(payload[:len(raw)] == raw, "bootloader: packaged image differs from raw BIN")
            else:
                require(payload == raw, f"{component}: packaged payload differs from raw BIN")
            report["raw_bin_match"] = True
        elif require_all_raw:
            raise PackageValidationError(f"{component}: raw BIN is required for content verification")
        components.append(report)
        offset = payload_end + 4

    require(offset == package_end, "Unparsed trailing data before final package checksum")
    actual_components = tuple(item["component"] for item in components)
    require(actual_components in expected_component_sequences,
            f"Component sequence mismatch: expected {expected_component_sequences}, found {actual_components}")
    return {
        "package": str(package_path),
        "type": package_type,
        "size": len(data),
        "final_fletcher": data[-4:].hex().upper(),
        "components": components,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--type", required=True, choices=PACKAGE_TYPES)
    for component in COMPONENTS:
        parser.add_argument(f"--{component}-bin", type=Path, dest=f"{component}_bin")
    parser.add_argument("--require-all-raw", action="store_true",
                        help="Fail unless every segment is compared with its just-built raw BIN")
    parser.add_argument("--json", action="store_true", help="Print the successful report as JSON")
    return parser.parse_args()


def main():
    args = parse_args()
    raw_paths = {component: getattr(args, f"{component}_bin") for component in COMPONENTS
                 if getattr(args, f"{component}_bin") is not None}
    report = verify_package(args.package, args.type, raw_paths, args.require_all_raw)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Validated {report['type']} package: {report['package']} ({report['size']} bytes)")
        for component in report["components"]:
            raw = ", raw BIN match" if component.get("raw_bin_match") else ""
            print(f"  {component['component']}: {component['version']}, {component['payload_size']} bytes, "
                  f"target {component['target_address']}, CRC {component['crc32']}{raw}")
        print(f"Final Fletcher: {report['final_fletcher']}")


if __name__ == "__main__":
    main()
