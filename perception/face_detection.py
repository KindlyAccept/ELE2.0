# perception/face_detection.py
"""
Face detector - CPU implementation based on OpenCV Haar Cascade.

Previously used Hailo-8L + SCRFD (HEF), now switched to CPU inference
to free Hailo PCIe channel for Hailo-10H LLM inference.
"""
import cv2
import numpy as np


class FaceDetector:
    """Face detector - OpenCV Haar Cascade CPU inference."""

    def __init__(
        self,
        model_path: str = None,       # Kept for API compatibility, unused
        confidence_threshold: float = 0.5,
        nms_threshold: float = 0.4,   # Kept for API compatibility, unused
    ):
        self.confidence_threshold = confidence_threshold

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.classifier = cv2.CascadeClassifier(cascade_path)
        if self.classifier.empty():
            raise RuntimeError(f"[FaceDetector] Failed to load Haar cascade: {cascade_path}")

        self.backend = "cpu"
        print(f"[FaceDetector] CPU Haar cascade loaded: {cascade_path}")

    def detect_faces(self, frame) -> list:
        """Detect faces, return [(x, y, w, h), ...]."""
        if frame is None:
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = self.classifier.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(40, 40),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        if len(faces) == 0:
            return []

        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    def draw_faces(self, frame, faces):
        """Draw face boxes on image."""
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        return frame

    def cleanup(self):
        pass
