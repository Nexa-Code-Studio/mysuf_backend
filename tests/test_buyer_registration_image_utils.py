import pytest

from app.modules.buyer_registrations.image_utils import ImageUtils


def test_crop_ktp_portrait_returns_expected_slice_shape():
    numpy = pytest.importorskip("numpy")

    image = numpy.zeros((600, 1000, 3), dtype=numpy.uint8)
    portrait = ImageUtils.crop_ktp_portrait(image)

    assert portrait.shape[0] == 396
    assert portrait.shape[1] == 260
