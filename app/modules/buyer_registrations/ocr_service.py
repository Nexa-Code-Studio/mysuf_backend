from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from typing import Any

from app.modules.buyer_registrations.model_store import ModelStore


@dataclass
class OCRResult:
    raw_text: str
    nik: str | None
    nik_valid: bool


class OCRService:
    NIK_LINE_PATTERN = re.compile(r"(?:NIK\s*[:\-]?\s*)?([0-9OIlB\s]{16,24})", re.IGNORECASE)

    def __init__(self, model_store: ModelStore):
        self.model_store = model_store

    def extract_nik(self, image: Any) -> OCRResult:
        # Step 1: Try running OCR on the raw/rectified image directly
        raw_text = self._run_ocr(image)
        nik = self.extract_nik_from_text(raw_text)
        
        # Step 2: Fallback to preprocessed image if NIK is not found
        if not (nik is not None and len(nik) == 16):
            preprocessed = self._preprocess_image(image)
            raw_text_preprocessed = self._run_ocr(preprocessed)
            nik_preprocessed = self.extract_nik_from_text(raw_text_preprocessed)
            if nik_preprocessed is not None and len(nik_preprocessed) == 16:
                raw_text = raw_text_preprocessed
                nik = nik_preprocessed

        return OCRResult(
            raw_text=raw_text,
            nik=nik,
            nik_valid=nik is not None and len(nik) == 16,
        )

    def extract_nik_from_text(self, raw_text: str) -> str | None:
        preferred_lines = []
        other_lines = []
        for line in raw_text.splitlines():
            normalized_line = self.normalize_text_for_digits(line)
            if "NIK" in line.upper():
                preferred_lines.append(normalized_line)
            else:
                other_lines.append(normalized_line)

        for text in [*preferred_lines, *other_lines, self.normalize_text_for_digits(raw_text)]:
            direct_match = re.search(r"\d{16}", text)
            if direct_match:
                return direct_match.group(0)

            for candidate in self.NIK_LINE_PATTERN.findall(text):
                digits_only = re.sub(r"\D", "", candidate)
                if len(digits_only) >= 16:
                    return digits_only[:16]
        return None

    def normalize_text_for_digits(self, value: str) -> str:
        return (
            value.replace("O", "0")
            .replace("o", "0")
            .replace("I", "1")
            .replace("l", "1")
            .replace("B", "8")
            .replace("L", "1")
            .replace("]", "1")
            .replace("[", "1")
            .replace("|", "1")
            .replace("S", "5")
            .replace("s", "5")
            .replace("g", "9")
            .replace("q", "9")
            .replace("D", "0")
            .replace("d", "0")
            .replace("Z", "2")
            .replace("z", "2")
            .replace("A", "4")
            .replace("T", "7")
        )

    def _preprocess_image(self, image: Any) -> Any:
        cv2 = importlib.import_module("cv2")

        resized = cv2.resize(image, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray)
        contrasted = cv2.equalizeHist(denoised)
        return cv2.adaptiveThreshold(
            contrasted,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15,
        )

    def _run_ocr(self, image: Any) -> str:
        if self.model_store.ocr_engine is None:
            return ""

        ocr_result = self.model_store.ocr_engine.ocr(image, cls=True)
        if not ocr_result:
            return ""

        lines: list[str] = []
        for page in ocr_result:
            if not page:
                continue
            for line in page:
                if len(line) < 2 or len(line[1]) < 1:
                    continue
                lines.append(str(line[1][0]))
        return "\n".join(lines)
