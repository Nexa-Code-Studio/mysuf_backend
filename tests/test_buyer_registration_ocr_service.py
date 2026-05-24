from app.modules.buyer_registrations.model_store import ModelStore
from app.modules.buyer_registrations.ocr_service import OCRService


def test_ocr_service_normalizes_common_typos():
    service = OCRService(ModelStore())

    normalized = service.normalize_text_for_digits("NIK OI1B 1234")

    assert normalized == "N1K 0118 1234"


def test_ocr_service_extracts_nik_from_multiline_text():
    service = OCRService(ModelStore())

    nik = service.extract_nik_from_text("PROVINSI\nNIK : 3174 OI23 4567 89l2\nNama")

    assert nik == "3174012345678912"
