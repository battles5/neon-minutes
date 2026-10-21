"""Pick GPU or CPU settings for this machine.

The CUDA 12.8 build of PyTorch runs on NVIDIA GPUs with compute capability 7.5 or newer
(GTX 16xx, RTX 20xx and later). Whisper large-v3 needs about 4.5 GB of VRAM in float16,
about 3 GB in int8_float16. Anything else runs on the CPU with the lighter large-v3-turbo.
"""

from dataclasses import dataclass
from functools import lru_cache

MIN_COMPUTE_CAPABILITY = (7, 5)
FLOAT16_MIN_VRAM_GB = 6.0
INT8_MIN_VRAM_GB = 3.5


@dataclass(frozen=True)
class Profile:
    device: str
    compute_type: str
    model: str
    description: str

    @property
    def gpu(self) -> bool:
        return self.device == "cuda"


CPU_MODEL = "large-v3-turbo"
GPU_MODEL = "large-v3"


def cpu_profile(reason: str) -> Profile:
    return Profile("cpu", "int8", CPU_MODEL, f"{reason}: modalità CPU (più lenta)")


@lru_cache(maxsize=1)
def detect() -> Profile:
    try:
        import torch
    except ImportError:
        return cpu_profile("PyTorch non disponibile")
    if not torch.cuda.is_available():
        return cpu_profile("Nessuna GPU NVIDIA utilizzabile")
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / 1024**3
    name = f"{props.name} ({vram_gb:.0f} GB)"
    if (props.major, props.minor) < MIN_COMPUTE_CAPABILITY:
        return cpu_profile(f"{name} troppo vecchia")
    if vram_gb >= FLOAT16_MIN_VRAM_GB:
        return Profile("cuda", "float16", GPU_MODEL, f"GPU {name}: modalità veloce")
    if vram_gb >= INT8_MIN_VRAM_GB:
        return Profile("cuda", "int8_float16", GPU_MODEL, f"GPU {name}: modalità veloce (int8)")
    return cpu_profile(f"{name}: memoria insufficiente")
