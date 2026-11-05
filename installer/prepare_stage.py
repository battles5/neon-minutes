"""Fill the installer staging folder with what the build venv knows.

    python installer/prepare_stage.py <stage dir>

- models/pyannote-community-1: the diarization pipeline (CC-BY-4.0), copied from the
  Hugging Face cache so colleagues need no token. The demo GIF is left out.
- installer/requirements-lock.txt and torch-version.txt: the exact versions tested here.
  torch/torchaudio are pinned separately because the setup picks the CUDA or CPU build.
- THIRD-PARTY-NOTICES.txt: the bundled components, then every package the setup
  downloads, with its license as declared in its metadata.
- installer/sizes.json: download and disk sizes per variant, so the wizard can say
  how much it will download and need before it starts, and postinstall can show an ETA.
"""

import json
import os
import shutil
import sys
import sysconfig
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parent.parent
PYANNOTE = "pyannote/speaker-diarization-community-1"
SEPARATE = {"torch", "torchaudio"}
NOT_SHIPPED = {"pip", "setuptools", "wheel"}
TORCH_WHEEL = "https://download.pytorch.org/whl/{label}/{name}-{version}%2B{label}-cp312-cp312-win_amd64.whl"
WHISPER_REPOS = {"cuda": "Systran/faster-whisper-large-v3", "cpu": "mobiuslabsgmbh/faster-whisper-large-v3-turbo"}
WHISPER_FILES = ("config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary")


def stage_model(dest: Path):
    load_dotenv(ROOT / ".env")
    src = Path(snapshot_download(PYANNOTE, token=os.environ.get("HF_TOKEN")))
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=False, ignore=shutil.ignore_patterns("*.gif", ".gitattributes"))


def _license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr
    classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return ", ".join(dict.fromkeys(classifiers))
    text = (meta.get("License") or "").strip()
    return text.splitlines()[0][:80] if text else "see the package"


def _homepage(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    if meta.get("Home-page"):
        return meta["Home-page"]
    for url in meta.get_all("Project-URL") or []:
        label, _, link = url.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return link.strip()
    return ""


def stage_requirements(installer_dir: Path) -> list[metadata.Distribution]:
    dists = {d.metadata["Name"].lower().replace("_", "-"): d for d in metadata.distributions()}
    pinned = sorted(
        f"{d.metadata['Name']}=={d.version}"
        for name, d in dists.items()
        if name not in SEPARATE | NOT_SHIPPED
    )
    installer_dir.mkdir(parents=True, exist_ok=True)
    (installer_dir / "requirements-lock.txt").write_text("\n".join(pinned) + "\n", encoding="utf-8")
    torch_version = dists["torch"].version.split("+")[0]
    (installer_dir / "torch-version.txt").write_text(torch_version + "\n", encoding="utf-8")
    return [d for name, d in sorted(dists.items()) if name not in NOT_SHIPPED]


def write_notices(stage: Path, dists: list[metadata.Distribution]):
    header = (ROOT / "installer" / "notices_header.txt").read_text(encoding="utf-8")
    rows = []
    for d in dists:
        version = d.version.split("+")[0]
        rows.append(f"- {d.metadata['Name']} {version} — {_license(d)}  {_homepage(d)}".rstrip())
    body = header.rstrip() + "\n\n" + "\n".join(rows) + "\n"
    (stage / "THIRD-PARTY-NOTICES.txt").write_text(body, encoding="utf-8")


def _content_length(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return int(resp.headers["Content-Length"])


def _wheel_size(name: str, version: str) -> int:
    """Size of the wheel pip will pick on 64-bit Windows / CPython 3.12, from PyPI's JSON API."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as resp:
        files = [f for f in json.load(resp)["urls"] if f["packagetype"] == "bdist_wheel"]

    def rank(f):
        n = f["filename"]
        if "win_amd64" in n and ("cp312" in n or "abi3" in n):
            return 0
        if "none-any" in n:
            return 1
        return 2

    files = [f for f in files if rank(f) < 2]
    return min(files, key=rank)["size"] if files else 0


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def write_sizes(installer_dir: Path, stage: Path):
    lock = (installer_dir / "requirements-lock.txt").read_text(encoding="utf-8").split()
    version = (installer_dir / "torch-version.txt").read_text(encoding="utf-8").strip()
    with ThreadPoolExecutor(16) as pool:
        deps = sum(pool.map(lambda pin: _wheel_size(*pin.split("==")), lock))
        torch = {
            variant: sum(pool.map(lambda n: _content_length(TORCH_WHEEL.format(label=label, name=n, version=version)),
                                  ("torch", "torchaudio")))
            for variant, label in (("cuda", "cu128"), ("cpu", "cpu"))
        }
    api = HfApi()
    whisper = {}
    for variant, repo in WHISPER_REPOS.items():
        info = api.model_info(repo, files_metadata=True)
        whisper[variant] = sum(s.size or 0 for s in info.siblings if s.rfilename.startswith(WHISPER_FILES))

    # Installed size: what the build venv takes, with the CPU build of torch scaled from the
    # CUDA one by the wheel sizes (both unpack in about the same ratio).
    site = Path(sysconfig.get_paths()["purelib"])
    torch_dirs = sum(_dir_size(site / d) for d in ("torch", "torchaudio") if (site / d).exists())
    others = _dir_size(site) - torch_dirs
    unpack_ratio = torch_dirs / torch["cuda"]
    base = _dir_size(stage)  # runtime + program + pyannote model
    installed = {v: int(base + others + torch[v] * unpack_ratio) for v in ("cuda", "cpu")}
    sizes = {
        "download": {"torch": torch, "deps": deps, "whisper": whisper},
        "installed": installed,
        # Unpacking times measured on a test install (antivirus scanning included).
        "install_seconds": {"torch": {"cuda": 160, "cpu": 30}, "deps": 260, "check": 50},
    }
    (installer_dir / "sizes.json").write_text(json.dumps(sizes, indent=1), encoding="utf-8")
    mb = lambda b: f"{b / 1e6:,.0f} MB"
    print(f"download: torch {mb(torch['cuda'])} / {mb(torch['cpu'])}, librerie {mb(deps)}, "
          f"whisper {mb(whisper['cuda'])} / {mb(whisper['cpu'])}; installato {mb(installed['cuda'])} / {mb(installed['cpu'])}")


def main():
    stage = Path(sys.argv[1])
    stage_model(stage / "models" / "pyannote-community-1")
    dists = stage_requirements(stage / "installer")
    write_notices(stage, dists)
    write_sizes(stage / "installer", stage)
    print(f"stage pronto: {len(dists)} pacchetti, modello pyannote copiato")


if __name__ == "__main__":
    main()
