"""Speech-to-text with faster-whisper (CTranslate2) on the GPU."""

import gc
import os
from collections.abc import Callable

import numpy as np

from .audio import SAMPLE_RATE


# "Participants:" and "Terms:" in the meeting's language: a prompt in another language nudges
# Whisper towards it. With automatic detection the lists go in without a heading.
PROMPT_WORDS = {
    "it": ("Partecipanti", "Termini"),
    "en": ("Participants", "Terms"),
    "es": ("Participantes", "Términos"),
    "fr": ("Participants", "Termes"),
    "pt": ("Participantes", "Termos"),
    "zh": ("参会者", "术语"),
}


def build_prompt(names: list[str], glossary: list[str], language: str = "it") -> str | None:
    """Whisper spells names and jargon better when they appear in the initial prompt."""
    headings = PROMPT_WORDS.get(language)
    parts = []
    for heading, items in zip(headings or ("", ""), (names, glossary)):
        if items:
            parts.append((f"{heading}: " if heading else "") + ", ".join(items) + ".")
    return " ".join(parts) or None


def is_model_cached(model_name: str) -> bool:
    from faster_whisper.utils import download_model

    try:
        download_model(model_name, local_files_only=True)
        return True
    except Exception:
        return False


def download(model_name: str) -> str:
    """Fetch the model weights now (the installer does this so the first run is quick)."""
    from faster_whisper.utils import download_model

    return download_model(model_name)


def _drop_repeats(segments: list[dict]) -> list[dict]:
    """Conditioning on previous text occasionally loops on a short phrase: keep one copy."""
    kept = []
    for seg in segments:
        if kept and seg["text"].strip() == kept[-1]["text"].strip():
            continue
        kept.append(seg)
    return kept


def transcribe(
    audio: np.ndarray,
    model_name: str = "large-v3",
    language: str | None = "it",
    prompt: str | None = None,
    device: str = "cuda",
    compute_type: str = "float16",
    progress: Callable[[float], None] | None = None,
) -> dict:
    """Return {"language", "model", "segments": [{"start", "end", "text", "words": [...]}]}.

    Sequential decoding with previous-text conditioning: on the test stand-ups the
    batched pipeline was 2x faster but dropped ~1 min of speech out of 13, and decoding
    without conditioning lost punctuation and capitals after the first window.
    """
    # On Windows CTranslate2 needs cuBLAS/cuDNN; the CUDA build of torch loads them into the process.
    import torch  # noqa: F401
    from faster_whisper import WhisperModel

    # faster-whisper defaults to 4 CPU threads; half the logical cores is close to the physical ones.
    threads = max(4, (os.cpu_count() or 8) // 2) if device == "cpu" else 0
    model = WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=threads)
    segments, info = model.transcribe(
        audio,
        language=language,
        initial_prompt=prompt,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=True,
        hallucination_silence_threshold=2.0,
    )
    duration = len(audio) / SAMPLE_RATE
    result = []
    for seg in segments:
        words = [
            {"start": round(w.start, 3), "end": round(w.end, 3), "text": w.word, "p": round(w.probability, 3)}
            for w in seg.words or []
        ]
        result.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text, "words": words})
        if progress:
            progress(min(seg.end / duration, 1.0))
    del segments, model
    gc.collect()
    return {"language": info.language, "model": model_name, "segments": _drop_repeats(result)}
