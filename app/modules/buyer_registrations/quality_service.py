from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass

from app.core.config import settings


@dataclass
class QualityCheckResult:
    errors: list[str]
    blurry: bool
    brightness_ok: bool
    resolution_ok: bool
    glare_detected: bool
    brightness: float
    variance_of_laplacian: float
    width: int
    height: int

    def to_dict(self) -> dict:
        return asdict(self)


class QualityService:
    BLUR_THRESHOLD = 80.0
    BRIGHTNESS_MIN = 60.0
    BRIGHTNESS_MAX = 220.0
    GLARE_THRESHOLD = 0.12

    def check_ktp_image(self, image: object) -> QualityCheckResult:
        return self._check_image(image=image, enforce_card_clarity=True)

    def check_selfie_image(self, image: object) -> QualityCheckResult:
        return self._check_image(image=image, enforce_card_clarity=False)

    def _check_image(self, image: object, enforce_card_clarity: bool) -> QualityCheckResult:
        cv2 = importlib.import_module("cv2")
        numpy = importlib.import_module("numpy")

        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance_of_laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(numpy.mean(gray))
        glare_ratio = float(numpy.mean(gray >= 245))

        errors: list[str] = []
        blurry = variance_of_laplacian < self.BLUR_THRESHOLD
        brightness_ok = self.BRIGHTNESS_MIN <= brightness <= self.BRIGHTNESS_MAX
        resolution_ok = width >= settings.MIN_IMAGE_WIDTH and height >= settings.MIN_IMAGE_HEIGHT
        glare_detected = glare_ratio >= self.GLARE_THRESHOLD

        if not resolution_ok:
            errors.append("IMAGE_TOO_SMALL")
        if blurry:
            errors.append("IMAGE_TOO_BLURRY")
        if brightness < self.BRIGHTNESS_MIN:
            errors.append("IMAGE_TOO_DARK")
        if brightness > self.BRIGHTNESS_MAX:
            errors.append("IMAGE_TOO_BRIGHT")
        if enforce_card_clarity and glare_detected:
            errors.append("KTP_CARD_NOT_CLEAR")

        return QualityCheckResult(
            errors=errors,
            blurry=blurry,
            brightness_ok=brightness_ok,
            resolution_ok=resolution_ok,
            glare_detected=glare_detected,
            brightness=brightness,
            variance_of_laplacian=variance_of_laplacian,
            width=width,
            height=height,
        )
