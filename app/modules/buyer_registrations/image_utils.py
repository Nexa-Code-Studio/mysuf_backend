from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


class ImageUtils:
    @staticmethod
    def read_bytes(file_path: Path) -> bytes:
        return file_path.read_bytes()

    @staticmethod
    def load_cv2_image(file_path: Path) -> Any:
        cv2 = importlib.import_module("cv2")
        numpy = importlib.import_module("numpy")

        image_bytes = numpy.frombuffer(ImageUtils.read_bytes(file_path), dtype=numpy.uint8)
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image from {file_path}")
        return image

    @staticmethod
    def perspective_correct_ktp(image: Any) -> Any:
        cv2 = importlib.import_module("cv2")
        numpy = importlib.import_module("numpy")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 75, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:10]:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) != 4:
                continue

            points = approx.reshape(4, 2).astype("float32")
            ordered = ImageUtils._order_points(points)
            width_a = numpy.linalg.norm(ordered[2] - ordered[3])
            width_b = numpy.linalg.norm(ordered[1] - ordered[0])
            height_a = numpy.linalg.norm(ordered[1] - ordered[2])
            height_b = numpy.linalg.norm(ordered[0] - ordered[3])
            max_width = max(int(width_a), int(width_b))
            max_height = max(int(height_a), int(height_b))

            if max_width < 10 or max_height < 10:
                continue

            destination = numpy.array(
                [
                    [0, 0],
                    [max_width - 1, 0],
                    [max_width - 1, max_height - 1],
                    [0, max_height - 1],
                ],
                dtype="float32",
            )
            matrix = cv2.getPerspectiveTransform(ordered, destination)
            return cv2.warpPerspective(image, matrix, (max_width, max_height))

        return image

    @staticmethod
    def crop_ktp_portrait(image: Any) -> Any:
        height, width = image.shape[:2]
        left = int(width * 0.70)
        right = int(width * 0.96)
        top = int(height * 0.16)
        bottom = int(height * 0.82)
        left = max(0, left)
        right = min(width, right)
        top = max(0, top)
        bottom = min(height, bottom)
        return image[top:bottom, left:right].copy()

    @staticmethod
    def _order_points(points: Any) -> Any:
        numpy = importlib.import_module("numpy")

        ordered = numpy.zeros((4, 2), dtype="float32")
        sums = points.sum(axis=1)
        diffs = numpy.diff(points, axis=1)
        ordered[0] = points[numpy.argmin(sums)]
        ordered[2] = points[numpy.argmax(sums)]
        ordered[1] = points[numpy.argmin(diffs)]
        ordered[3] = points[numpy.argmax(diffs)]
        return ordered
