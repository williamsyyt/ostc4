#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path

from verify_update_package import (
    COMPONENTS,
    PackageValidationError,
    package_fletcher,
    stm32_crc32,
    verify_package,
)


def firmware_image():
    payload = bytearray(0x10040)
    payload[:4] = bytes((0x00, 0x00, 0x01, 0x08))
    payload[0x10000:0x10004] = bytes((1, 7, 7, 1))
    payload[0x1003C:0x10040] = bytes((0x00, 0x00, 0xEE, 0xFF))
    for offset in range(4, 0x10000, 4):
        payload[offset:offset + 4] = (offset // 4).to_bytes(4, "little")
    return bytes(payload)


def make_segment(component, payload):
    spec = COMPONENTS[component]
    length = len(payload)
    version_offset = 0 if component in ("fontpack", "bootloader") else spec["version_offset"]
    header = (length.to_bytes(4, "big") + spec["marker"].to_bytes(4, "big") +
              ((length + spec["marker"]) & 0xFFFFFFFF).to_bytes(4, "little") +
              payload[version_offset:version_offset + 4])
    return header + payload + stm32_crc32(payload).to_bytes(4, "big")


def make_package(component, payload):
    body = make_segment(component, payload)
    return body + package_fletcher(body)


class UpdatePackageTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.raw = self.root / "firmware.bin"
        self.package = self.root / "update.bin"
        self.raw.write_bytes(firmware_image())
        self.package.write_bytes(make_package("firmware", self.raw.read_bytes()))

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_valid_firmware_package(self):
        report = verify_package(self.package, "firmware", {"firmware": self.raw}, True)
        self.assertEqual(report["components"][0]["version"], "1.7.7-beta")
        self.assertEqual(report["components"][0]["target_address"], "0x08040000")
        self.assertTrue(report["components"][0]["raw_bin_match"])

    def test_payload_tampering_is_rejected(self):
        data = bytearray(self.package.read_bytes())
        data[32] ^= 0x01
        data[-4:] = package_fletcher(data[:-4])
        self.package.write_bytes(data)
        with self.assertRaisesRegex(PackageValidationError, "Segment CRC mismatch"):
            verify_package(self.package, "firmware", {"firmware": self.raw}, True)

    def test_final_checksum_tampering_is_rejected(self):
        data = bytearray(self.package.read_bytes())
        data[-1] ^= 0x01
        self.package.write_bytes(data)
        with self.assertRaisesRegex(PackageValidationError, "Final package Fletcher"):
            verify_package(self.package, "firmware", {"firmware": self.raw}, True)

    def test_stale_raw_binary_is_rejected(self):
        raw = bytearray(self.raw.read_bytes())
        raw[32] ^= 0x01
        self.raw.write_bytes(raw)
        with self.assertRaisesRegex(PackageValidationError, "differs from raw BIN"):
            verify_package(self.package, "firmware", {"firmware": self.raw}, True)

    def test_missing_raw_binary_is_rejected_when_required(self):
        with self.assertRaisesRegex(PackageValidationError, "raw BIN is required"):
            verify_package(self.package, "firmware", require_all_raw=True)


if __name__ == "__main__":
    unittest.main()
