"""Active-speaker timeline from Teams recordings.

Teams draws the name label of whoever is producing audio on a Teams-purple (#6264A7)
rounded box; the presenter label of a screen share lights up the same way. Several
labels are often lit at once (cross-talk, open mics), so this module only reports
which names are lit at each sampled instant. Deciding which voice belongs to which
name is naming.py's job.
"""

import re
from collections.abc import Callable
from pathlib import Path

import av
import cv2
import numpy as np

TEAMS_PURPLE = np.array([98, 100, 167], dtype=np.int16)
COLOR_TOLERANCE = 22
# Label size relative to frame height (1080p recordings: ~26 px tall, 100-300 px wide).
# Wider purple areas (banners, title bars of a shared screen) are not labels.
LABEL_HEIGHT = (0.015, 0.045)
LABEL_WIDTH = (0.045, 0.55)
LABEL_MIN_FILL = 0.6


def clean_name(text: str) -> str:
    """Drop OCR'd icons and stray symbols; keep the "..." Teams uses for truncated names."""
    text = re.sub(r"[^\w\s.'’-]", "", text)
    return re.sub(r"\s+", " ", text).strip(" -")


class _CachedOcr:
    """The same label crop repeats for minutes: OCR each distinct crop once."""

    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()
        self._cache: dict[tuple, list[tuple[np.ndarray, str]]] = {}
        self.calls = 0

    def read(self, crop: np.ndarray, box: tuple[int, int, int, int]) -> str:
        key = tuple(v // 8 for v in box[:3])
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        thumb = cv2.resize(gray, (96, 16), interpolation=cv2.INTER_AREA).astype(np.int16)
        entries = self._cache.setdefault(key, [])
        for cached, text in entries:
            if np.abs(cached - thumb).mean() < 6:
                return text
        bgr = np.ascontiguousarray(crop[:, :, ::-1])
        result, _ = self._engine(bgr, use_det=False, use_cls=False, use_rec=True)
        self.calls += 1
        text = clean_name(result[0][0]) if result else ""
        entries.append((thumb, text))
        return text


def _lit_labels(rgb: np.ndarray):
    """Yield (crop, box) for every purple label-shaped box in a full-resolution RGB frame."""
    frame_h = rgb.shape[0]
    small = rgb[::2, ::2].astype(np.int16)
    mask = (np.abs(small - TEAMS_PURPLE).max(axis=2) < COLOR_TOLERANCE).astype(np.uint8)
    # Close the holes left by the white text so each label is one component.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    for x, y, w, h, area in stats[1:]:
        x, y, w, h, area = 2 * x, 2 * y, 2 * w, 2 * h, 4 * area
        if not LABEL_HEIGHT[0] * frame_h <= h <= LABEL_HEIGHT[1] * frame_h:
            continue
        if not LABEL_WIDTH[0] * frame_h <= w <= LABEL_WIDTH[1] * frame_h:
            continue
        if area / (w * h) < LABEL_MIN_FILL:
            continue
        yield rgb[y : y + h, x : x + w], (int(x), int(y), int(w), int(h))


def scan_speaker_labels(
    path: Path, fps: float = 2.0, progress: Callable[[float], None] | None = None
) -> list[dict]:
    """Sample the video at `fps` and return [{"t": seconds, "names": [lit label texts]}]."""
    ocr = _CachedOcr()
    samples = []
    next_t = 0.0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        duration = container.duration / av.time_base if container.duration else None
        for frame in container.decode(stream):
            t = frame.time
            if t is None or t < next_t:
                continue
            while next_t <= t:
                next_t += 1.0 / fps
            rgb = frame.to_ndarray(format="rgb24")
            names = {ocr.read(crop, box) for crop, box in _lit_labels(rgb)}
            samples.append({"t": round(t, 2), "names": sorted(names - {""})})
            if progress and duration:
                progress(min(t / duration, 1.0))
    return samples
