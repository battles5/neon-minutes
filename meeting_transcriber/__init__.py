"""Local meeting transcription: faster-whisper + pyannote + speaker names from the Teams video and from
what people say (a local language model)."""

__version__ = "1.6.0"

# Importing paths sets HF_HOME for an installed copy before any module loads huggingface_hub,
# so models always land in the user's data folder, whichever module is imported first.
from . import paths as _paths  # noqa: E402, F401
