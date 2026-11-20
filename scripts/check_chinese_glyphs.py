#!/usr/bin/env python3
"""Check that every translated Chinese character has a generated bitmap glyph."""

import re
from pathlib import Path


def translation_coverage():
    root = Path(__file__).resolve().parents[1]
    text = (root / "Discovery/Src/text_multilanguage.c").read_text(encoding="utf-8-sig")
    header = (root / "Discovery/Inc/Fonts/font_T48_chinese.h").read_text(encoding="utf-8")
    strings = re.findall(r'text_ZH_\w+\[\]\s*=\s*"([^"]*)"', text)
    required = {ord(character) for string in strings for character in string if ord(character) >= 0x80}
    glyphs = {int(value, 16) for value in re.findall(r"\{ 0x([0-9A-F]+), &FontT48Chinese_", header)}
    missing = required - glyphs
    unused = glyphs - required
    if missing or unused:
        raise SystemExit(f"Chinese glyph coverage mismatch: missing={sorted(missing)}, unused={sorted(unused)}")
    if not strings or not required:
        raise SystemExit("No simplified Chinese translations or glyphs found")
    return strings, required


def main():
    strings, required = translation_coverage()
    print(f"Chinese glyph coverage passed: {len(required)} characters, {len(strings)} translated strings")


if __name__ == "__main__":
    main()
