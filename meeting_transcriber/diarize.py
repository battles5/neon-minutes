"""Speaker diarization with pyannote community-1 on the GPU."""

from collections.abc import Callable

import numpy as np

from .audio import SAMPLE_RATE
from .paths import BUNDLED_PYANNOTE

MODEL = "pyannote/speaker-diarization-community-1"


def available(token: str | None) -> bool:
    """The installer ships the model (CC-BY-4.0); a development checkout downloads it with a token."""
    return BUNDLED_PYANNOTE.exists() or bool(token)
# Share of the run spent before/within each pipeline step, for progress reporting.
STEP_SPAN = {
    "segmentation": (0.0, 0.25),
    "speaker_counting": (0.25, 0.3),
    "embeddings": (0.3, 0.95),
    "discrete_diarization": (0.95, 1.0),
}


def _hook(progress: Callable[[float], None] | None):
    def hook(step_name, step_artifact, file=None, total=None, completed=None):
        if progress and step_name in STEP_SPAN:
            lo, hi = STEP_SPAN[step_name]
            done = completed / total if total else 1.0
            progress(lo + (hi - lo) * done)

    return hook


def diarize(
    audio: np.ndarray,
    token: str | None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    device: str = "cuda",
    progress: Callable[[float], None] | None = None,
    checkpoint: str | None = None,
) -> dict:
    """Return {"turns": [{"start", "end", "speaker"}], "embeddings": {speaker: [floats]}}.

    Turns come from the exclusive diarization (one speaker at a time), which is what
    word-level attribution needs.
    """
    import torch
    from pyannote.audio import Pipeline

    if checkpoint is None:
        checkpoint = str(BUNDLED_PYANNOTE) if BUNDLED_PYANNOTE.exists() else MODEL
    pipeline = Pipeline.from_pretrained(checkpoint, token=token)
    pipeline.to(torch.device(device))
    # Passing the waveform in memory skips pyannote's own decoder (torchcodec + FFmpeg DLLs).
    waveform = torch.from_numpy(audio).unsqueeze(0)
    bounds = {"num_speakers": num_speakers, "min_speakers": min_speakers, "max_speakers": max_speakers}
    output = pipeline(
        {"waveform": waveform, "sample_rate": SAMPLE_RATE},
        hook=_hook(progress),
        **{k: v for k, v in bounds.items() if v},
    )

    turns = [
        {"start": round(seg.start, 3), "end": round(seg.end, 3), "speaker": label}
        for seg, _, label in output.exclusive_speaker_diarization.itertracks(yield_label=True)
    ]
    embeddings = {}
    if output.speaker_embeddings is not None:
        for label, emb in zip(output.speaker_diarization.labels(), output.speaker_embeddings):
            if np.all(np.isfinite(emb)):
                embeddings[label] = [round(float(v), 6) for v in emb]

    del pipeline
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return {"model": MODEL, "turns": turns, "embeddings": embeddings}


def turns_from_video(samples: list[dict], roster: dict[str, str], fps: float, lag_s: float = 0.6) -> dict:
    """Fallback without pyannote: use the instants where exactly one label is lit as turns.

    Teams lights a label about `lag_s` after the voice starts (median 0.6 s on the
    test stand-ups), so turns are moved back by that much.
    """
    turns = []
    step = 1.0 / fps
    for sample in samples:
        names = {roster[n] for n in sample["names"] if n in roster}
        if len(names) != 1:
            continue
        name = names.pop()
        t = max(sample["t"] - lag_s, 0.0)
        if turns and turns[-1]["speaker"] == name and t - turns[-1]["end"] <= step * 1.5:
            turns[-1]["end"] = round(t + step, 3)
        else:
            turns.append({"start": round(t, 3), "end": round(t + step, 3), "speaker": name})
    return {"model": "video-only", "turns": turns, "embeddings": {}}
