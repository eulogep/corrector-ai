#!/usr/bin/env python3
"""Vérifier EasyOCR sur une copie synthétique sans afficher son contenu."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    image_path = Path(os.environ.get("EASYOCR_TEST_IMAGE", ""))
    if not image_path.is_file():
        print("EASYOCR_TEST_IMAGE_MISSING")
        return 2

    try:
        import easyocr

        reader = easyocr.Reader(["fr", "en"], gpu=False, verbose=False)
        entries = reader.readtext(str(image_path), detail=1, paragraph=False)
    except Exception as exc:
        print(f"EASYOCR_FAILED={type(exc).__name__}")
        return 4

    nonempty = [entry for entry in entries if len(entry) >= 2 and str(entry[1]).strip()]
    print("EASYOCR_SUCCESS")
    print(f"EASYOCR_TEXT_SEGMENTS={len(nonempty)}")
    print(f"EASYOCR_TEXT_TOTAL_LENGTH={sum(len(str(entry[1]).strip()) for entry in nonempty)}")
    return 0 if nonempty else 3


if __name__ == "__main__":
    raise SystemExit(main())
