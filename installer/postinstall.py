"""Second half of the setup, run by the wizard with the bundled Python (and by "Ripara componenti").

    runtime\\python.exe -u installer\\postinstall.py --app <install dir> --variant cuda|cpu|auto [--models] [--wizard]

1. PyTorch: the CUDA 12.8 build on a suitable NVIDIA GPU, otherwise the CPU build.
2. The other dependencies, pinned to the versions this release was tested with.
3. install.json, which switches the program to installed mode (per-user data folder).
4. Optionally the Whisper model, so that the first transcription does not wait for it.
5. A check that everything loads, including the bundled pyannote model.

With --wizard, progress goes to stdout as lines the setup's progress page understands:
    @@P|<per mille>|<first line>|<second line>
Without it (the "Ripara componenti" shortcut opens a console) the same text is printed for people.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from importlib import metadata
from pathlib import Path

TORCH_INDEX = {
    "cuda": "https://download.pytorch.org/whl/cu128",
    "cpu": "https://download.pytorch.org/whl/cpu",
}
TORCH_LABEL = {"cuda": "cu128", "cpu": "cpu"}
WHISPER_REPOS = {"large-v3": "Systran/faster-whisper-large-v3",
                 "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo"}
# Same limits as meeting_transcriber/hardware.py, plus the driver CUDA 12.8 needs.
MIN_COMPUTE_CAPABILITY = (7, 5)
MIN_VRAM_MB = 3584
MIN_DRIVER = 570
# Only weighs downloads against unpacking time for the progress bar; the ETA uses the measured speed.
NOMINAL_SPEED = 8e6
# No user site-packages and no PYTHON* variables: a Python already on the PC must not leak in
# (on Windows the runtime's ._pth file already does this).
PY = ["-s", "-E"]
REPAIR_HINT = ("Start > Neon Minutes > Ripara componenti" if sys.platform == "win32"
               else "il comando \"neon-minutes --ripara\"")


def user_data_dir(app: Path) -> Path:
    """Same folder as meeting_transcriber.paths.user_data_dir (only stdlib is needed to import it)."""
    sys.path.insert(0, str(app))
    from meeting_transcriber.paths import user_data_dir as data_dir

    return data_dir()


class Log:
    def __init__(self, path: Path):
        self.path = path

    def __call__(self, message: str):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")


def _gb(n: float) -> str:
    return f"{n / 1e9:.1f}".replace(".", ",") + " GB"


def _eta(seconds: float) -> str:
    if seconds < 60:
        return "meno di un minuto"
    minutes = round(seconds / 60)
    return "circa 1 minuto" if minutes == 1 else f"circa {minutes} minuti"


class Progress:
    """One progress figure for the whole run, from per-step downloads and unpacking times.

    Every step has bytes to download and seconds of local work. The bar weighs both
    (bytes at a nominal speed); the ETA uses the download speed actually measured.
    """

    def __init__(self, steps: list[dict], wizard: bool, log: Log):
        self.steps = steps
        self.wizard = wizard
        self.log = log
        self.current = 0
        self.speed = None
        self.last_emit = 0.0
        self.last_sample = None  # (time, total downloaded) for the speed estimate
        self.lock = threading.Lock()
        for s in steps:
            s.update(done_bytes=0, work=0.0, work_started=None)
        # pip prints nothing while it unpacks PyTorch for a minute or more: keep the ETA moving.
        threading.Thread(target=self._ticker, daemon=True).start()

    def _ticker(self):
        while True:
            time.sleep(1.0)
            self.tick()

    def _downloaded(self) -> float:
        return sum(s["done_bytes"] for s in self.steps)

    def start(self, index: int):
        with self.lock:
            self.current = index
        self.log(f"[{index + 1}/{len(self.steps)}] {self.steps[index]['title']}")
        self.emit(force=True)

    def bytes(self, done: int):
        step = self.steps[self.current]
        with self.lock:
            step["done_bytes"] = min(done, step["bytes"]) if step["bytes"] else done
            now, total = time.time(), self._downloaded()
            if self.last_sample and now - self.last_sample[0] >= 1.0:
                rate = (total - self.last_sample[1]) / (now - self.last_sample[0])
                if rate > 0:
                    self.speed = rate if self.speed is None else 0.7 * self.speed + 0.3 * rate
                self.last_sample = (now, total)
            elif not self.last_sample:
                self.last_sample = (now, total)
        self.emit()

    def working(self):
        """Downloads of the current step are over: unpacking/installing."""
        step = self.steps[self.current]
        with self.lock:
            step["done_bytes"] = step["bytes"]
            if step["work_started"] is None:
                step["work_started"] = time.time()
        self.emit(force=True)

    def finish(self, index: int):
        step = self.steps[index]
        with self.lock:
            step["done_bytes"], step["work"] = step["bytes"], 1.0
        self.emit(force=True)

    def tick(self):
        """Advance the estimated share of local work that has no measurable progress."""
        with self.lock:
            step = self.steps[self.current]
            if step["work_started"] is not None and step["work"] < 1.0:
                step["work"] = min((time.time() - step["work_started"]) / max(step["seconds"], 1), 0.95)
        self.emit()

    def emit(self, force: bool = False):
        now = time.time()
        if not force and now - self.last_emit < 0.5:
            return
        self.last_emit = now
        with self.lock:
            total = sum(s["bytes"] / NOMINAL_SPEED + s["seconds"] for s in self.steps) or 1
            done = sum(s["done_bytes"] / NOMINAL_SPEED + s["work"] * s["seconds"] for s in self.steps)
            speed = self.speed or NOMINAL_SPEED
            remaining = sum((s["bytes"] - s["done_bytes"]) / speed + (1 - s["work"]) * s["seconds"]
                            for s in self.steps)
            step = self.steps[self.current]
            first = f"Passo {self.current + 1} di {len(self.steps)}: {step['title']}"
            if step["bytes"] and step["done_bytes"] < step["bytes"]:
                detail = f"{_gb(step['done_bytes'])} di {_gb(step['bytes'])}"
                if self.speed:
                    detail += f" · {self.speed / 1e6:.1f} MB/s".replace(".", ",")
            else:
                detail = step.get("working", "installazione in corso")
            second = f"{detail} · tempo rimanente: {_eta(remaining)}"
            per_mille = int(min(done / total, 0.999) * 1000)
        if self.wizard:
            print(f"@@P|{per_mille}|{first}|{second}", flush=True)
        else:
            print(f"\r{per_mille / 10:5.1f}%  {first} — {second}".ljust(118)[:118], end="", flush=True)


def detect_variant() -> tuple[str, str]:
    """('cuda' or 'cpu', reason) from nvidia-smi; no NVIDIA driver means no nvidia-smi."""
    query = "--query-gpu=name,memory.total,driver_version,compute_cap"
    try:
        out = subprocess.run(["nvidia-smi", query, "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "cpu", "nessuna GPU NVIDIA trovata"
    if out.returncode or not out.stdout.strip():
        return "cpu", "nessuna GPU NVIDIA trovata"
    try:
        name, mem, driver, cap = [x.strip() for x in out.stdout.splitlines()[0].split(",")[:4]]
        major, minor = (int(x) for x in cap.split(".")[:2])
        mem_mb, driver_major = int(float(mem)), int(driver.split(".")[0])
    except ValueError:
        return "cpu", f"GPU non riconosciuta ({out.stdout.strip()[:80]})"
    if (major, minor) < MIN_COMPUTE_CAPABILITY:
        return "cpu", f"{name}: architettura troppo vecchia (compute capability {cap}, serve 7.5)"
    if mem_mb < MIN_VRAM_MB:
        return "cpu", f"{name}: {mem_mb} MB di memoria video, ne servono almeno 3,5 GB"
    if driver_major < MIN_DRIVER:
        return "cpu", f"{name}: driver {driver} troppo vecchio (serve 570 o successivo)"
    return "cuda", f"{name}, {mem_mb / 1024:.0f} GB, driver {driver}"


def run_pip(args: list[str], progress: Progress, log: Log):
    """pip with machine-readable download progress ("Progress <done> of <total>")."""
    cmd = [sys.executable, *PY, "-u", "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
           "--no-cache-dir", "--progress-bar", "raw", *args]
    log(" ".join(cmd))
    finished_files, current, last_total = 0, 0, None
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    tail = []
    for line in proc.stdout:
        line = line.rstrip()
        if line.startswith("Progress ") and " of " in line:
            try:
                done, total = (int(x) for x in line[len("Progress "):].split(" of "))
            except ValueError:
                continue
            if last_total is not None and (total != last_total or done < current):
                finished_files += last_total
            current, last_total = done, total
            progress.bytes(finished_files + current)
            continue
        log(line)
        tail = (tail + [line])[-15:]
        if line.startswith("Installing collected packages"):
            progress.working()
        else:
            progress.tick()
    if proc.wait():
        raise RuntimeError("pip non è riuscito:\n" + "\n".join(tail[-6:]))


def run_quiet(cmd: list[str], log: Log, progress: Progress, cwd: Path, watch: Path | None = None,
              env: dict | None = None) -> str:
    """Run a helper, ticking the progress (and measuring `watch`'s growth as downloaded bytes)."""
    log(" ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", env={**os.environ, **(env or {})})
    output = []
    reader = threading.Thread(target=lambda: output.extend(proc.stdout), daemon=True)
    reader.start()
    start_size = _tree_size(watch) if watch else 0
    while proc.poll() is None:
        if watch:
            progress.bytes(_tree_size(watch) - start_size)
        progress.tick()
        time.sleep(0.5)
    reader.join(5)
    text = "".join(output)
    log(text.strip())
    if proc.returncode:
        raise RuntimeError(text.strip().splitlines()[-1] if text.strip() else f"codice {proc.returncode}")
    return text


def _tree_size(path: Path) -> int:
    total = 0
    if path.exists():
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return total


def installed_torch() -> str | None:
    try:
        return metadata.version("torch")
    except metadata.PackageNotFoundError:
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app", required=True, type=Path)
    p.add_argument("--variant", choices=("cuda", "cpu", "auto"), default="auto")
    p.add_argument("--models", action="store_true")
    p.add_argument("--wizard", action="store_true")
    args = p.parse_args()
    if args.wizard:
        # The setups read the progress lines as UTF-8; on Windows a pipe would otherwise get the
        # ANSI code page and "·", accents and dashes would show up as question marks.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    app = args.app.resolve()
    installer = app / "installer"
    log = Log(app / "install.log")
    try:
        # Read, not imported: the dependencies of the package are what this script installs.
        version = (app / "meeting_transcriber" / "__init__.py").read_text(encoding="utf-8")
        version = version.split('__version__ = "')[1].split('"')[0]
        if args.variant == "auto":
            variant, reason = detect_variant()
        else:
            variant, reason = args.variant, "rilevata dal programma di installazione"
        sizes = json.loads((installer / "sizes.json").read_text(encoding="utf-8"))
        seconds = sizes["install_seconds"]
        model = "large-v3" if variant == "cuda" else "large-v3-turbo"
        torch_version = (installer / "torch-version.txt").read_text(encoding="utf-8").strip()
        log(f"Neon Minutes {version}: installazione dei componenti")
        log(f"Modalità: {'GPU NVIDIA' if variant == 'cuda' else 'CPU'} ({reason})")

        steps = [
            {"title": f"PyTorch per {'GPU NVIDIA (CUDA 12.8)' if variant == 'cuda' else 'CPU'}",
             "bytes": sizes["download"]["torch"][variant], "seconds": seconds["torch"][variant]},
            {"title": "Librerie (faster-whisper, pyannote, OCR...)",
             "bytes": sizes["download"]["deps"], "seconds": seconds["deps"]},
        ]
        if args.models:
            steps.append({"title": f"Modello Whisper {model}", "bytes": sizes["download"]["whisper"][variant],
                          "seconds": 5, "working": "verifica del modello"})
        steps.append({"title": "Verifica finale", "bytes": 0, "seconds": seconds["check"],
                      "working": "controllo che tutto si carichi"})
        progress = Progress(steps, args.wizard, log)

        progress.start(0)
        current = installed_torch()
        force = ["--force-reinstall", "--no-deps"] if current and not current.endswith(TORCH_LABEL[variant]) else []
        run_pip([f"torch=={torch_version}", f"torchaudio=={torch_version}",
                 "--index-url", TORCH_INDEX[variant], *force], progress, log)
        progress.finish(0)

        progress.start(1)
        run_pip(["-r", str(installer / "requirements-lock.txt")], progress, log)
        progress.finish(1)

        info = {"version": version, "variant": variant, "reason": reason, "installed": datetime.now().isoformat()}
        (app / "install.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

        index = 2
        if args.models:
            progress.start(index)
            # install.json now exists, so meeting_transcriber.paths points HF_HOME at the data folder.
            data = user_data_dir(app) / "modelli"
            watch = data / "hub" / ("models--" + WHISPER_REPOS[model].replace("/", "--"))
            # Plain HTTP instead of the Xet backend: it writes the file as it arrives, so its
            # growth is the download progress (Xet assembles the file only at the end).
            run_quiet([sys.executable, *PY, "-X", "utf8", "-c",
                       f"from meeting_transcriber import asr; asr.download({model!r})"],
                      log, progress, cwd=app, watch=watch, env={"HF_HUB_DISABLE_XET": "1"})
            progress.finish(index)
            index += 1

        progress.start(index)
        progress.working()
        out = run_quiet([sys.executable, *PY, "-X", "utf8", "-c",
                         "import av, cv2, faster_whisper, rapidocr_onnxruntime\n"
                         "from pyannote.audio import Pipeline\n"
                         "from meeting_transcriber import hardware, paths\n"
                         "Pipeline.from_pretrained(str(paths.BUNDLED_PYANNOTE))\n"
                         "print('@@HW', hardware.detect().description)"],
                        log, progress, cwd=app)
        description = next((l[5:] for l in out.splitlines() if l.startswith("@@HW ")), "")
        progress.finish(index)
        log(f"Verifica: {description}")
        if variant == "cuda" and "CPU" in description:
            log("ATTENZIONE: la GPU non risulta utilizzabile, il programma userà la CPU.")
            print("@@W|La GPU non risulta utilizzabile: il programma userà la CPU. Aggiorna il driver "
                  "NVIDIA e poi usa " + REPAIR_HINT + ".", flush=True)
        log("Installazione completata.")
        if not args.wizard:
            print("\n\nInstallazione completata.")
            time.sleep(3)
        return 0
    except Exception as exc:
        log(traceback.format_exc())
        message = f"{exc}".strip().splitlines()[-1] if str(exc).strip() else type(exc).__name__
        if args.wizard:
            print(f"@@E|{message}", flush=True)
        else:
            print(f"\n\nERRORE: {exc}\nControlla la connessione a Internet (o il proxy aziendale) e riprova. "
                  f"Dettagli in {log.path}")
            input("\nPremi Invio per chiudere questa finestra...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
