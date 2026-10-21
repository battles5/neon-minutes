"""Audio decoding without an ffmpeg binary: PyAV ships its own FFmpeg libraries."""

from pathlib import Path

import av
import numpy as np

SAMPLE_RATE = 16000


def load_audio(path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode the first audio stream of `path` to mono float32 at `sample_rate`."""
    chunks = []
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=sample_rate)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32, copy=False)
