"""Minimal Tkinter window: pick one or more recordings, transcribe them one after the other.

Each recording gets a progress bar with its own ETA, plus an overall bar when there are
several. Results land in a "Trascrizioni" folder next to each recording.
"""

import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import hardware
from .diarize import available as diarization_available
from .paths import DATA_DIR, GUIDE, ICON, glossary_path, setup_environment
from .pipeline import Options, Reporter, default_out_root, expected_seconds, plan, process
from .voices import VoiceLibrary

FILE_TYPES = [
    ("Registrazioni", "*.mp4 *.mkv *.mov *.avi *.webm *.m4a *.mp3 *.wav *.ogg"),
    ("Tutti i file", "*.*"),
]
TICK_MS = 500


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(int(round(seconds)), 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class _LogFile:
    """pythonw has no console: send library output (warnings, download bars) to a file."""

    def __init__(self, path: Path):
        self._f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, text):
        self._f.write(text)
        return len(text)

    def flush(self):
        self._f.flush()

    def isatty(self):
        return False


class _QueueReporter(Reporter):
    def __init__(self, q: queue.Queue, index: int):
        self.q, self.index = q, index

    def log(self, message: str):
        self.q.put(("log", self.index, message))

    def progress(self, fraction: float, stage: str):
        self.q.put(("progress", self.index, fraction, stage))


STAGE_LABELS = {
    "audio": "audio",
    "video": "lettura nomi",
    "diarization": "separazione voci",
    "parallel": "nomi + voci",
    "asr": "trascrizione",
    "fatto": "fatto",
}


class Job:
    def __init__(self, path: Path, estimate: float):
        self.path = path
        self.estimate = estimate  # expected seconds before any progress is known
        self.fraction = 0.0
        self.stage = ""
        self.started: float | None = None
        self.finished: float | None = None
        self.error: str | None = None
        self.output: Path | None = None

    def eta(self, speed: float) -> float | None:
        """Seconds left. Before 5% progress trust the estimate, then the observed rate."""
        if self.finished or self.error:
            return 0.0
        if self.started is None:
            return self.estimate * speed
        elapsed = time.time() - self.started
        if self.fraction < 0.05:
            return max(self.estimate * speed - elapsed, self.estimate * speed * (1 - self.fraction) * 0.5)
        return elapsed * (1 - self.fraction) / self.fraction


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.token = setup_environment()
        self.jobs: list[Job] = []
        self.rows: list[dict] = []
        self.q: queue.Queue = queue.Queue()
        self.running = False
        self.started: float | None = None
        self.finished: float | None = None

        root.title("Trascrittore riunioni")
        root.geometry("820x560")
        root.minsize(640, 420)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        top = ttk.Frame(root, padding=(12, 12, 12, 4))
        top.pack(fill="x")
        self.pick_btn = ttk.Button(top, text="Scegli video…", command=self.pick)
        self.pick_btn.pack(side="left")
        self.start_btn = ttk.Button(top, text="Avvia", command=self.start, state="disabled")
        self.start_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(top, text="Apri cartella risultati", command=self.open_output, state="disabled")
        self.open_btn.pack(side="left")
        ttk.Button(top, text="Guida", command=lambda: self.open_file(GUIDE)).pack(side="right")
        ttk.Button(top, text="Glossario…", command=lambda: self.open_file(glossary_path())).pack(side="right", padx=8)

        self.hardware = ttk.Label(root, padding=(12, 0), foreground="#555", text="Verifica dell'hardware…")
        self.hardware.pack(fill="x")
        threading.Thread(target=lambda: self.q.put(("hardware", hardware.detect())), daemon=True).start()
        self.info = ttk.Label(root, padding=(12, 0), foreground="#555")
        self.info.pack(fill="x")
        if not diarization_available(self.token):
            ttk.Label(
                root, padding=(12, 4), foreground="#b45309", wraplength=780,
                text="Modello pyannote non disponibile: gli speaker verranno attribuiti solo dal video "
                     "(meno preciso). Vedi la guida.",
            ).pack(fill="x")

        self.list_frame = ttk.Frame(root, padding=(12, 8))
        self.list_frame.pack(fill="x")
        self.list_frame.columnconfigure(1, weight=1)
        ttk.Label(self.list_frame, text="Nessun video scelto.", foreground="#777").grid(row=0, column=0, sticky="w")

        self.total_frame = ttk.Frame(root, padding=(12, 4))
        self.total_frame.columnconfigure(1, weight=1)
        ttk.Label(self.total_frame, text="Totale", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.total_bar = ttk.Progressbar(self.total_frame, maximum=1000)
        self.total_bar.grid(row=0, column=1, sticky="ew", padx=10)
        self.total_label = ttk.Label(self.total_frame, width=30)
        self.total_label.grid(row=0, column=2, sticky="w")

        log_frame = ttk.Frame(root, padding=(12, 4, 12, 12))
        log_frame.pack(fill="both", expand=True, side="bottom")
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word", font=("Consolas", 9),
                                background="#f7f7f7", relief="flat")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

        root.after(TICK_MS, self.tick)

    # --- choosing files -------------------------------------------------------------

    def pick(self):
        files = filedialog.askopenfilenames(
            title="Scegli una o più registrazioni",
            initialdir=str(Path.home() / "Downloads"),
            filetypes=FILE_TYPES,
        )
        if files:
            self.add_files(files)

    def add_files(self, files):
        opts = Options()
        self.jobs = []
        self.started = self.finished = None
        for f in files:
            path = Path(f)
            try:
                estimate = expected_seconds(plan(path, opts, None, self.token))
            except Exception as exc:  # unreadable file: show it, skip it
                self.write_log(f"Impossibile leggere {path.name}: {exc}")
                continue
            self.jobs.append(Job(path, estimate))
        self.build_rows()
        folders = sorted({str(default_out_root(j.path)) for j in self.jobs})
        self.info.configure(text="Risultati in: " + "; ".join(folders))
        self.start_btn.configure(state="normal" if self.jobs else "disabled")
        self.open_btn.configure(state="disabled")

    def build_rows(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.rows = []
        for i, job in enumerate(self.jobs):
            name = ttk.Label(self.list_frame, text=job.path.name, width=46, anchor="w")
            name.grid(row=i, column=0, sticky="w", pady=3)
            bar = ttk.Progressbar(self.list_frame, maximum=1000)
            bar.grid(row=i, column=1, sticky="ew", padx=10)
            status = ttk.Label(self.list_frame, width=30, anchor="w")
            status.grid(row=i, column=2, sticky="w")
            self.rows.append({"bar": bar, "status": status})
        if len(self.jobs) > 1:
            self.total_frame.pack(fill="x", after=self.list_frame)
        else:
            self.total_frame.pack_forget()
        self.refresh()

    # --- running --------------------------------------------------------------------

    def start(self):
        if self.running or not self.jobs:
            return
        self.running = True
        self.started, self.finished = time.time(), None
        self.pick_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        opts = Options()
        library = VoiceLibrary(DATA_DIR / "voices.json")
        for i, job in enumerate(self.jobs):
            self.q.put(("start", i))
            try:
                output = process(job.path, opts, self.token, library, report=_QueueReporter(self.q, i))
                self.q.put(("done", i, output))
            except Exception as exc:
                traceback.print_exc()
                self.q.put(("error", i, f"{type(exc).__name__}: {exc}"))
        self.q.put(("all_done",))

    def tick(self):
        while True:
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                break
            kind, *rest = msg
            if kind == "hardware":
                profile = rest[0]
                self.hardware.configure(text=profile.description,
                                        foreground="#555" if profile.gpu else "#b45309")
            elif kind == "start":
                job = self.jobs[rest[0]]
                job.started = time.time()
                self.write_log(f"== {job.path.name}")
            elif kind == "log":
                self.write_log(rest[1])
            elif kind == "progress":
                job = self.jobs[rest[0]]
                job.fraction, job.stage = rest[1], rest[2]
            elif kind == "done":
                job = self.jobs[rest[0]]
                job.fraction, job.finished, job.output = 1.0, time.time(), rest[1]
                self.open_btn.configure(state="normal")
            elif kind == "error":
                job = self.jobs[rest[0]]
                job.error = rest[1]
                self.write_log(f"ERRORE: {rest[1]}")
            elif kind == "all_done":
                self.running = False
                self.finished = time.time()
                self.pick_btn.configure(state="normal")
                failed = [j for j in self.jobs if j.error]
                if failed:
                    messagebox.showwarning("Trascrittore", f"{len(failed)} file non completati: vedi il log.")
        self.refresh()
        self.root.after(TICK_MS, self.tick)

    def speed(self) -> float:
        """Observed time / estimated time, so queued recordings get realistic ETAs."""
        ratios = [(j.finished - j.started) / j.estimate for j in self.jobs if j.finished and j.estimate]
        current = next((j for j in self.jobs if j.started and not j.finished and not j.error), None)
        if current and current.fraction >= 0.2:
            ratios.append((time.time() - current.started) / (current.fraction * current.estimate))
        return sum(ratios) / len(ratios) if ratios else 1.0

    def refresh(self):
        speed = self.speed()
        for job, row in zip(self.jobs, self.rows):
            row["bar"]["value"] = job.fraction * 1000
            if job.error:
                text = "errore"
            elif job.finished:
                text = f"fatto in {_clock(job.finished - job.started)}"
            elif job.started:
                stage = STAGE_LABELS.get(job.stage, "avvio")
                text = f"{stage} {job.fraction:.0%} · ETA {_clock(job.eta(speed))}"
            else:
                text = f"in attesa · ETA {_clock(job.eta(speed))}"
            row["status"].configure(text=text)
        if len(self.jobs) > 1:
            total = sum(j.estimate for j in self.jobs) or 1.0
            done = sum(j.estimate * (1.0 if (j.finished or j.error) else j.fraction) for j in self.jobs)
            self.total_bar["value"] = done / total * 1000
            if self.running:
                remaining = sum(j.eta(speed) or 0.0 for j in self.jobs)
                self.total_label.configure(text=f"{done / total:.0%} · ETA {_clock(remaining)}")
            elif self.finished:
                self.total_label.configure(text=f"fatto in {_clock(self.finished - self.started)}")
            else:
                self.total_label.configure(text=f"stima {_clock(sum(j.eta(speed) or 0.0 for j in self.jobs))}")

    # --- misc -----------------------------------------------------------------------

    def write_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def open_output(self):
        done = [j for j in self.jobs if j.output]
        if done:
            os.startfile(done[-1].output.parent.parent if len(done) > 1 else done[-1].output.parent)

    def open_file(self, path: Path):
        if path.exists():
            os.startfile(path)
        else:
            messagebox.showinfo("Trascrittore", f"File non trovato:\n{path}")

    def on_close(self):
        if self.running and not messagebox.askyesno("Trascrittore", "Trascrizione in corso: vuoi interromperla?"):
            return
        self.root.destroy()
        os._exit(0)  # the worker thread may be inside a GPU call


def main(files: list[str] | None = None):
    """Files given on the command line (or dropped on the shortcut) are preselected."""
    if sys.stdout is None or sys.stderr is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = _LogFile(DATA_DIR / "gui.log")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    if ICON.exists():
        root.iconbitmap(default=str(ICON))
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = App(root)
    files = files if files is not None else sys.argv[1:]
    if files:
        app.add_files([f for f in files if Path(f).is_file()])
    root.mainloop()


if __name__ == "__main__":
    main()
