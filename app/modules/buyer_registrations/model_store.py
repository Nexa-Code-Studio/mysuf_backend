from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelStore:
    ocr_engine: Any | None = None
    face_engine: Any | None = None
    initialized: bool = False
    initialization_error: str | None = None


_MODEL_STORE = ModelStore()
_MODEL_LOCK = Lock()


def get_model_store() -> ModelStore:
    return _MODEL_STORE


async def initialize_model_store() -> ModelStore:
    if _MODEL_STORE.initialized:
        return _MODEL_STORE

    with _MODEL_LOCK:
        if _MODEL_STORE.initialized:
            return _MODEL_STORE

    try:
        ocr_engine = await asyncio.to_thread(_load_paddle_ocr)
        face_engine = await asyncio.to_thread(_load_insightface)
        _MODEL_STORE.ocr_engine = ocr_engine
        _MODEL_STORE.face_engine = face_engine
        _MODEL_STORE.initialization_error = None
    except Exception as exc:  # pragma: no cover - exercised through logging path
        logger.warning("Identity verification models could not be loaded: %s", exc)
        _MODEL_STORE.ocr_engine = None
        _MODEL_STORE.face_engine = None
        _MODEL_STORE.initialization_error = str(exc)
    finally:
        _MODEL_STORE.initialized = True

    return _MODEL_STORE


async def close_model_store() -> None:
    _MODEL_STORE.ocr_engine = None
    _MODEL_STORE.face_engine = None
    _MODEL_STORE.initialized = False
    _MODEL_STORE.initialization_error = None


def _load_paddle_ocr() -> Any:
    paddleocr_module = importlib.import_module("paddleocr")
    return paddleocr_module.PaddleOCR(
        use_angle_cls=True,
        lang=settings.OCR_MODEL_LANGUAGE,
        show_log=False,
    )


def _load_insightface() -> Any:
    insightface_module = importlib.import_module("insightface")
    face_analysis = insightface_module.app.FaceAnalysis(name=settings.INSIGHTFACE_MODEL_NAME)
    face_analysis.prepare(ctx_id=0 if _onnx_gpu_available() else -1)
    return face_analysis


def _onnx_gpu_available() -> bool:
    try:
        onnxruntime_module = importlib.import_module("onnxruntime")
    except ModuleNotFoundError:
        return False
    return "CUDAExecutionProvider" in onnxruntime_module.get_available_providers()
