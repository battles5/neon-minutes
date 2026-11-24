"""Make the language model release ("modelli-2"): Qwen3-4B converted to CTranslate2 int8.

    python installer/convert_lm.py <work folder> [--ct2 <folder already converted>]

1. Downloads Qwen/Qwen3-4B from Hugging Face and converts it with ct2-transformers-converter
   (needs `pip install transformers` besides the program's requirements; about 20 GB of disk
   and 16 GB of RAM for a few minutes).
2. Splits model.bin in parts below GitHub's 2 GB limit per release file, into <work>/release.
3. Prints the FILES table for meeting_transcriber/lm.py (sizes and SHA-256 of the whole files).

Then: gh release create modelli-2 <work>/release/* --prerelease --title "..." --notes "..."
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = "Qwen/Qwen3-4B"
PART_BYTES = 1_900_000_000
COPY = ("tokenizer.json", "tokenizer_config.json", "generation_config.json", "LICENSE")
NOTICE = """Qwen3-4B (https://huggingface.co/Qwen/Qwen3-4B), Apache License 2.0 (see LICENSE),
converted to CTranslate2 with int8 weights for Neon Minutes:
    ct2-transformers-converter --model Qwen/Qwen3-4B --quantization int8
model.bin is split in parts (model.bin.000, .001, ...): join them in order.
"""


def convert(work: Path) -> Path:
    from huggingface_hub import snapshot_download

    src, out = work / "hf", work / "ct2"
    snapshot_download(REPO, local_dir=str(src), allow_patterns=["*.json", "*.safetensors", "*.txt", "LICENSE*"])
    converter = Path(sys.executable).with_name("ct2-transformers-converter" + (".exe" if sys.platform == "win32" else ""))
    subprocess.run([str(converter), "--model", str(src), "--output_dir", str(out), "--quantization", "int8",
                    "--copy_files", *COPY, "--force"], check=True)
    shutil.rmtree(src)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("work", type=Path)
    p.add_argument("--ct2", type=Path, help="a folder with the model already converted")
    args = p.parse_args()
    ct2 = args.ct2 or convert(args.work)
    release = args.work / "release"
    release.mkdir(parents=True, exist_ok=True)
    (ct2 / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    files = {}
    for path in sorted(ct2.iterdir()):
        digest, parts = hashlib.sha256(), []
        with open(path, "rb") as f:
            while chunk := f.read(PART_BYTES):
                digest.update(chunk)
                name = path.name if path.stat().st_size <= PART_BYTES else f"{path.name}.{len(parts):03d}"
                (release / name).write_bytes(chunk)
                parts.append(name)
        files[path.name] = (path.stat().st_size, digest.hexdigest(), parts)
    print("FILES = {")
    for name, entry in files.items():
        print(f"    {json.dumps(name)}: ({entry[0]}, {json.dumps(entry[1])},\n        {json.dumps(entry[2])}),")
    print("}")


if __name__ == "__main__":
    main()
