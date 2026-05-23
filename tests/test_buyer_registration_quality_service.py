import pytest

from app.modules.buyer_registrations.quality_service import QualityService


def test_quality_service_flags_too_small_image():
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")

    _ = cv2
    image = numpy.zeros((120, 200, 3), dtype=numpy.uint8)

    result = QualityService().check_selfie_image(image)

    assert "IMAGE_TOO_SMALL" in result.errors
