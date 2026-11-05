"""Linux counterpart of prepare_stage.py, run on Linux by build_linux.sh with the build venv.

    python installer/linux_prepare.py <payload dir>

- installer/requirements-lock.txt and torch-version.txt from the build venv, which was
  installed from requirements.txt with installer/constraints.txt (the versions tested on
  Windows), so Linux gets the same versions plus its own platform-only packages;
- THIRD-PARTY-NOTICES.txt;
- installer/sizes.json. On Linux the CUDA build of PyTorch pulls NVIDIA's libraries as
  separate wheels, so the sizes come from pip's resolution report (`pip install --dry-run
  --report`) and a HEAD request per file.
"""

import json
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_stage import WHISPER_FILES, WHISPER_REPOS, _dir_size, stage_requirements, write_notices  # noqa: E402

CUDA_UNPACK = 1.6
TORCH_INDEX = {"cuda": "https://download.pytorch.org/whl/cu128", "cpu": "https://download.pytorch.org/whl/cpu"}


def _content_length(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers["Content-Length"])


def resolved_download(args: list[str]) -> int:
    """Total size of the wheels pip would download for `args` on this machine."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
                        "--report", str(report), *args], check=True)
        urls = [item["download_info"]["url"] for item in json.loads(report.read_text())["install"]]
    with ThreadPoolExecutor(16) as pool:
        return sum(pool.map(_content_length, urls))


def write_sizes(installer_dir: Path, payload: Path):
    version = (installer_dir / "torch-version.txt").read_text(encoding="utf-8").strip()
    torch = {v: resolved_download([f"torch=={version}", f"torchaudio=={version}", "--index-url", TORCH_INDEX[v]])
             for v in ("cuda", "cpu")}
    # --no-deps: the lock is complete, and resolving it would pull PyPI's CUDA torch again.
    deps = resolved_download(["--no-deps", "-r", str(installer_dir / "requirements-lock.txt")])

    from huggingface_hub import HfApi

    api = HfApi()
    whisper = {}
    for variant, repo in WHISPER_REPOS.items():
        info = api.model_info(repo, files_metadata=True)
        whisper[variant] = sum(s.size or 0 for s in info.siblings if s.rfilename.startswith(WHISPER_FILES))

    # Installed size from the (CPU) build venv. The CUDA build (torch plus NVIDIA's wheels) is not
    # installed here: it unpacks to about 1.6 times its download, as measured with cu128 on Windows.
    site = Path(sysconfig.get_paths()["purelib"])
    torch_dirs = sum(_dir_size(site / d) for d in ("torch", "torchaudio") if (site / d).exists())
    others = _dir_size(site) - torch_dirs
    base = _dir_size(payload)
    installed = {"cpu": int(base + others + torch_dirs), "cuda": int(base + others + torch["cuda"] * CUDA_UNPACK)}
    sizes = {
        "download": {"torch": torch, "deps": deps, "whisper": whisper},
        "installed": installed,
        "install_seconds": {"torch": {"cuda": 120, "cpu": 30}, "deps": 150, "check": 50},
    }
    (installer_dir / "sizes.json").write_text(json.dumps(sizes, indent=1), encoding="utf-8")
    mb = lambda b: f"{b / 1e6:,.0f} MB"
    print(f"download: torch {mb(torch['cuda'])} / {mb(torch['cpu'])}, librerie {mb(deps)}, "
          f"whisper {mb(whisper['cuda'])} / {mb(whisper['cpu'])}; installato {mb(installed['cuda'])} / "
          f"{mb(installed['cpu'])}")


def main():
    payload = Path(sys.argv[1])
    dists = stage_requirements(payload / "installer")
    write_notices(payload, dists)
    write_sizes(payload / "installer", payload)


if __name__ == "__main__":
    main()
