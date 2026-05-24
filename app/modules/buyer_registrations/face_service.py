from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.modules.buyer_registrations.model_store import ModelStore


@dataclass
class FaceVerificationResult:
    match: bool
    similarity: float | None
    threshold: float
    error: str | None = None


class FaceService:
    def __init__(self, model_store: ModelStore):
        self.model_store = model_store

    def compare_portrait_and_selfie(self, portrait_image: Any, selfie_image: Any) -> FaceVerificationResult:
        if self.model_store.face_engine is None:
            return FaceVerificationResult(
                match=False,
                similarity=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                error="VERIFICATION_INTERNAL_ERROR",
            )

        portrait_faces = self.model_store.face_engine.get(portrait_image)
        if not portrait_faces:
            return FaceVerificationResult(
                match=False,
                similarity=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                error="FACE_NOT_USABLE_IN_KTP_PORTRAIT",
            )

        selfie_faces = self.model_store.face_engine.get(selfie_image)
        if not selfie_faces:
            return FaceVerificationResult(
                match=False,
                similarity=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                error="FACE_NOT_FOUND_IN_SELFIE",
            )
        if len(selfie_faces) > 1:
            return FaceVerificationResult(
                match=False,
                similarity=None,
                threshold=settings.FACE_MATCH_THRESHOLD,
                error="MULTIPLE_FACES_IN_SELFIE",
            )

        portrait_face = self._select_largest_face(portrait_faces)
        selfie_face = selfie_faces[0]
        similarity = self._cosine_similarity(portrait_face.embedding, selfie_face.embedding)
        return FaceVerificationResult(
            match=similarity >= settings.FACE_MATCH_THRESHOLD,
            similarity=similarity,
            threshold=settings.FACE_MATCH_THRESHOLD,
            error=None if similarity >= settings.FACE_MATCH_THRESHOLD else "FACE_MISMATCH",
        )

    def _select_largest_face(self, faces: list[Any]) -> Any:
        return max(faces, key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]))

    def _cosine_similarity(self, left_embedding: Any, right_embedding: Any) -> float:
        numpy = importlib.import_module("numpy")

        left = numpy.array(left_embedding)
        right = numpy.array(right_embedding)
        denominator = float(numpy.linalg.norm(left) * numpy.linalg.norm(right))
        if denominator == 0.0:
            return 0.0
        return float(numpy.dot(left, right) / denominator)
