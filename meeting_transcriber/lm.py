"""The local language model: Qwen3-4B (Apache 2.0) converted to CTranslate2 int8.

It reads the transcript to name voices from what people say (content_names.py) and to give the
meeting a title (titles.py). It runs on this PC like Whisper; nothing leaves it.

The converted model (4 GB) is attached to the "modelli-2" release of the repository, with
model.bin split in parts under GitHub's 2 GB limit (installer/convert_lm.py made them). It is
downloaded by the setup together with Whisper, or at the first meeting that needs it.
"""

import hashlib
import os
import shutil
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .paths import MODELS_DIR

MODEL_NAME = "qwen3-4b-ct2-int8"
RELEASE_URL = "https://github.com/battles5/neon-minutes/releases/download/modelli-2/"
# File -> (size, sha256, parts as uploaded). Written by installer/convert_lm.py.
FILES = {
    "config.json": (154, "c6272f7a9c5dd8c61f08fda35a21c9c0419406e13431a47183b12a345b977530",
        ["config.json"]),
    "generation_config.json": (239, "2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2",
        ["generation_config.json"]),
    "LICENSE": (11343, "832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e",
        ["LICENSE"]),
    "model.bin": (4027735607, "2061f66b172d9ef6f573c57399bc42276ca0d3f4f6990efefe76632d0a169c3f",
        ["model.bin.000", "model.bin.001", "model.bin.002"]),
    "NOTICE.txt": (297, "24537811bdf3d6184e576d065cd1685ab4395aafeb41101071e28ac8a870608a",
        ["NOTICE.txt"]),
    "tokenizer.json": (11422654, "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
        ["tokenizer.json"]),
    "tokenizer_config.json": (9732, "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
        ["tokenizer_config.json"]),
    "vocabulary.json": (4013091, "c13bfc16f420511f173be2b8577f08acfc7453a3ba08c777d0389f0ff1c03a7f",
        ["vocabulary.json"]),
}
MODEL_BYTES = sum(size for size, _, _ in FILES.values())
# int8 weights plus the KV cache of a 4k-token prompt; below this the model runs on the CPU.
MIN_VRAM_GB = 6.0
SYSTEM = "You analyse meeting transcripts."


def model_dir() -> Path:
    """NEON_LM_DIR points elsewhere (tests, or a model converted by hand)."""
    return Path(os.environ.get("NEON_LM_DIR") or MODELS_DIR / MODEL_NAME)


def is_installed() -> bool:
    folder = model_dir()
    return all((folder / name).is_file() and (folder / name).stat().st_size == size
               for name, (size, _, _) in FILES.items())


def download(progress: Callable[[int, int], None] | None = None) -> Path:
    """Fetch the parts, check them and assemble the model folder; progress(done, total) in bytes."""
    folder = model_dir()
    if is_installed():
        return folder
    partial = folder.with_name(folder.name + ".download")
    partial.mkdir(parents=True, exist_ok=True)
    done = 0
    for name, (size, sha256, parts) in FILES.items():
        target = partial / name
        if target.is_file() and target.stat().st_size == size:
            done += size  # from an interrupted download
            continue
        digest = hashlib.sha256()
        with open(target, "wb") as out:
            for part in parts:
                with urllib.request.urlopen(RELEASE_URL + part, timeout=60) as response:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, MODEL_BYTES)
        if target.stat().st_size != size or (sha256 and digest.hexdigest() != sha256):
            target.unlink()
            raise RuntimeError(f"{name}: download incomplete or damaged, try again")
    if folder.exists():
        shutil.rmtree(folder)
    os.replace(partial, folder)
    return folder


def choose_device(device: str, whisper_compute_type: str) -> tuple[str, str]:
    """GPU when Whisper itself runs there in float16 (6 GB of video memory or more), else CPU."""
    if device == "cuda" and whisper_compute_type == "float16":
        return "cuda", "int8_float16"
    return "cpu", "int8"


class LanguageModel:
    """A chat model converted to CTranslate2: multiple-choice questions and short answers."""

    def __init__(self, path: Path | None = None, device: str = "cuda", compute_type: str = "int8_float16"):
        import ctranslate2
        from tokenizers import Tokenizer

        path = Path(path or model_dir())
        self.device = device
        if device == "cuda":
            # pyannote and Whisper ran just before: give their cached GPU memory back.
            try:
                import torch

                torch.cuda.empty_cache()
            except Exception:
                pass
        threads = max(4, (os.cpu_count() or 8) // 2) if device == "cpu" else 0
        self.generator = ctranslate2.Generator(str(path), device=device, compute_type=compute_type,
                                               intra_threads=threads)
        self.tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))

    def _tokens(self, text: str) -> list[str]:
        return self.tokenizer.encode(text, add_special_tokens=False).tokens

    @staticmethod
    def prefix(system: str, examples: tuple[tuple[str, str], ...] = ()) -> str:
        """Qwen3 chat format with thinking switched off (an empty think block), after worked examples."""
        text = f"<|im_start|>system\n{system}<|im_end|>\n"
        for question, answer in examples:
            text += (f"<|im_start|>user\n{question}<|im_end|>\n"
                     f"<|im_start|>assistant\n<think>\n\n</think>\n\n{answer}<|im_end|>\n")
        return text

    @staticmethod
    def turn(user: str) -> str:
        return f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def choose(self, prompts: list[str], options: tuple[str, ...], system: str = SYSTEM,
               examples: tuple[tuple[str, str], ...] = ()) -> list[dict[str, float]]:
        """Probability of each one-token option as the answer's first token, renormalised over the options.

        One prompt at a time: in a batch, CTranslate2 feeds the longer prompts token by token and
        the first-step logits of the others are wrong. The system message and the worked examples
        are the same for every prompt: CTranslate2 computes them once (static prompt).
        """
        import ctranslate2
        import numpy as np

        ids = [self.tokenizer.token_to_id(o) for o in options]
        static = self._tokens(self.prefix(system, examples))
        results = []
        for prompt in prompts:
            out = self.generator.generate_batch([self._tokens(self.turn(prompt))], static_prompt=static,
                                                max_length=1, sampling_topk=1, return_logits_vocab=True,
                                                include_prompt_in_result=False)
            logits = out[0].logits[0]  # first hypothesis ...
            while isinstance(logits, list):
                logits = logits[0]  # ... first generated step
            if logits.device != "cpu":
                logits = logits.to_device(ctranslate2.Device.cpu)
            row = np.asarray(logits, dtype=np.float32).reshape(-1)[ids]
            p = np.exp(row - row.max())
            p /= p.sum()
            results.append(dict(zip(options, p.round(3).tolist())))
        return results

    def answer(self, prompt: str, system: str = SYSTEM, examples: tuple[tuple[str, str], ...] = (),
               max_tokens: int = 32) -> str:
        """A short free-text answer (greedy decoding)."""
        tokens = self._tokens(self.prefix(system, examples) + self.turn(prompt))
        out = self.generator.generate_batch([tokens], max_length=max_tokens, sampling_topk=1,
                                            end_token="<|im_end|>", include_prompt_in_result=False)
        return self.tokenizer.decode(out[0].sequences_ids[0]).strip()
