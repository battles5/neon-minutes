"""Pick GPU or CPU settings for this machine.

The CUDA 12.8 build of PyTorch runs on NVIDIA GPUs with compute capability 7.5 or newer
(GTX 16xx, RTX 20xx and later). Whisper large-v3 needs about 4.5 GB of VRAM in float16,
about 3 GB in int8_float16. Anything else runs on the CPU with the lighter large-v3-turbo.
"""

import threading
from dataclasses import dataclass

MIN_COMPUTE_CAPABILITY = (7, 5)
FLOAT16_MIN_VRAM_GB = 6.0
INT8_MIN_VRAM_GB = 3.5


@dataclass(frozen=True)
class Profile:
    device: str
    compute_type: str
    model: str
    reason: str  # i18n key: hw_fast for the GPU, why not the GPU otherwise
    gpu_name: str = ""

    @property
    def gpu(self) -> bool:
        return self.device == "cuda"

    @property
    def description(self) -> str:
        """One line for the window and the installer, in the interface language."""
        from .i18n import t

        if self.gpu:
            text = t("hw_fast", name=self.gpu_name)
            return text + " (int8)" if self.compute_type != "float16" else text
        return t("hw_cpu", reason=t(self.reason, name=self.gpu_name))


CPU_MODEL = "large-v3-turbo"
GPU_MODEL = "large-v3"


def cpu_profile(reason: str, gpu_name: str = "") -> Profile:
    return Profile("cpu", "int8", CPU_MODEL, reason, gpu_name)


_lock = threading.Lock()
_profile: Profile | None = None


def detect() -> Profile:
    """The profile of this PC, computed once; callers on other threads wait for the first one."""
    global _profile
    with _lock:
        if _profile is None:
            _profile = _detect()
        return _profile


def _detect() -> Profile:
    try:
        import torch
    except ImportError:
        return cpu_profile("hw_no_torch")
    if not torch.cuda.is_available():
        return cpu_profile("hw_no_gpu")
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / 1024**3
    name = f"{props.name} ({vram_gb:.0f} GB)"
    if (props.major, props.minor) < MIN_COMPUTE_CAPABILITY:
        return cpu_profile("hw_too_old", name)
    if vram_gb >= FLOAT16_MIN_VRAM_GB:
        return Profile("cuda", "float16", GPU_MODEL, "hw_fast", name)
    if vram_gb >= INT8_MIN_VRAM_GB:
        return Profile("cuda", "int8_float16", GPU_MODEL, "hw_fast", name)
    return cpu_profile("hw_low_memory", name)
