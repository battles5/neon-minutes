"""Tkinter window with a queue of recordings, transcribed one after the other.

Recordings can be added at any time, also while one is being transcribed. Each row has a
progress bar with its own ETA, the meeting language (changeable until it starts) and buttons to
start it (or move it to the front of the queue) and to remove it; "Start all" queues every
waiting recording. The total ETA covers everything still to do and is recomputed whenever the
list changes. Results land in a "Trascrizioni" folder next to each recording. The interface
language can be switched at any time (texts in i18n.py).
"""

import itertools
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from . import hardware, i18n, theme
from .diarize import available as diarization_available
from .paths import DATA_DIR, GUIDE, ICON, ICON_PNG, glossary_path, setup_environment
from .pipeline import Options, Reporter, default_out_root, expected_seconds, plan, process
from .voices import VoiceLibrary

_EXTENSIONS = ("mp4", "mkv", "mov", "avi", "webm", "m4a", "mp3", "wav", "ogg")
# The Linux file dialog matches patterns case-sensitively: list both cases.
_PATTERNS = " ".join(f"*.{e} *.{e.upper()}" for e in _EXTENSIONS)
TICK_MS = 500
# On Linux the bundled Tk draws with X core fonts: Latin-1 letters are there, ▶ and ✕ are not.
SYMBOLS = sys.platform == "win32"
BUTTON_WIDTH = 3 if SYMBOLS else 8
t = i18n.t


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(int(round(seconds)), 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def open_path(path: Path):
    """Open a file or folder with the system's default application."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


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
    def __init__(self, q: queue.Queue, job_id: int):
        self.q, self.job_id = q, job_id

    def log(self, message: str):
        self.q.put(("log", self.job_id, message))

    def progress(self, fraction: float, stage: str):
        self.q.put(("progress", self.job_id, fraction, stage))


class Job:
    _ids = itertools.count(1)

    def __init__(self, path: Path, language: str):
        self.id = next(Job._ids)
        self.path = path
        self.language = language  # meeting language, "auto" to let Whisper detect it
        self.estimate: float | None = None  # expected seconds, computed in the background
        self.queued = False  # in the run queue, waiting for its turn
        self.taken = False  # picked up by the worker thread
        self.fraction = 0.0
        self.stage = ""
        self.started: float | None = None
        self.finished: float | None = None
        self.error: str | None = None
        self.output: Path | None = None

    @property
    def running(self) -> bool:
        return self.started is not None and not self.finished and not self.error

    @property
    def pending(self) -> bool:
        """Not started yet: waiting for "Start" or already in the queue."""
        return self.started is None and not self.error

    def eta(self, speed: float) -> float | None:
        """Seconds left. Before 5% progress trust the estimate, then the observed rate."""
        if self.finished or self.error:
            return 0.0
        if self.estimate is None:
            return None
        if self.started is None:
            return self.estimate * speed
        elapsed = time.time() - self.started
        if self.fraction < 0.05:
            return max(self.estimate * speed - elapsed, self.estimate * speed * (1 - self.fraction) * 0.5)
        return elapsed * (1 - self.fraction) / self.fraction


class App:
    def __init__(self, root: tk.Tk, palette: dict):
        self.root = root
        self.palette = palette
        self.token = setup_environment()
        self.jobs: list[Job] = []  # display order
        self.rows: dict[int, dict] = {}
        self.q: queue.Queue = queue.Queue()
        # The run queue is shared with the worker thread; the GPU takes one recording at a time.
        self.cond = threading.Condition()
        self.run_queue: list[Job] = []
        self.auto = False  # "Start all" is on: recordings added meanwhile join the run
        self.batch_errors = 0
        # Importing torch/faster-whisper the first time after boot can take a minute: it never
        # runs on the Tk thread, and one worker keeps the hardware check and the estimates in
        # sequence (two threads loading the CUDA libraries at once can deadlock).
        self.prep = ThreadPoolExecutor(max_workers=1)

        root.title("Neon Minutes")
        root.geometry("920x640")
        root.minsize(700, 460)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        bold = font.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")

        top = ttk.Frame(root, padding=(12, 12, 12, 4))
        top.pack(fill="x")
        self.add_btn = ttk.Button(top, command=self.pick)
        self.add_btn.pack(side="left")
        self.start_btn = ttk.Button(top, command=self.start_all, state="disabled")
        self.start_btn.pack(side="left", padx=8)
        self.open_btn = ttk.Button(top, command=self.open_output, state="disabled")
        self.open_btn.pack(side="left")
        self.guide_btn = ttk.Button(top, command=lambda: self.open_file(GUIDE))
        self.guide_btn.pack(side="right")
        self.glossary_btn = ttk.Button(top, command=lambda: self.open_file(glossary_path()))
        self.glossary_btn.pack(side="right", padx=8)

        # Languages: the meeting's (default for the recordings added next) and the window's.
        langs = ttk.Frame(root, padding=(12, 4, 12, 2))
        langs.pack(fill="x")
        self.meeting_label = ttk.Label(langs)
        self.meeting_label.pack(side="left")
        self.meeting_box = ttk.Combobox(langs, state="readonly", width=24)
        self.meeting_box.pack(side="left", padx=(6, 8))
        self.meeting_box.bind("<<ComboboxSelected>>", self.on_meeting_language)
        self.ui_box = ttk.Combobox(langs, state="readonly", width=11, values=list(i18n.UI_LANGUAGES.values()))
        self.ui_box.pack(side="right")
        self.ui_box.current(list(i18n.UI_LANGUAGES).index(i18n.ui_language()))
        self.ui_box.bind("<<ComboboxSelected>>", self.on_ui_language)
        self.ui_label = ttk.Label(langs)
        self.ui_label.pack(side="right", padx=(0, 6))
        self.meeting_hint = ttk.Label(root, padding=(12, 0), foreground=palette["muted"])
        self.meeting_hint.pack(fill="x")
        self.meeting_language = i18n.meeting_language()

        self.profile = None
        self.hardware = ttk.Label(root, padding=(12, 2), foreground=palette["muted"])
        self.hardware.pack(fill="x")
        self.prep.submit(lambda: self.q.put(("hardware", hardware.detect())))
        self.info = ttk.Label(root, padding=(12, 0), foreground=palette["muted"])
        self.info.pack(fill="x")
        self.warning = None
        if not diarization_available(self.token):
            self.warning = ttk.Label(root, padding=(12, 4), foreground=palette["warn"], wraplength=860)
            self.warning.pack(fill="x")

        # Packed bottom-up so the list in the middle takes the remaining height.
        log_frame = ttk.Frame(root, padding=(12, 4, 12, 12))
        log_frame.pack(fill="x", side="bottom")
        log_font = ("Consolas", 9) if sys.platform == "win32" else "TkFixedFont"
        self.log_text = tk.Text(log_frame, height=8, state="disabled", wrap="word", font=log_font,
                                background=palette["text_bg"], foreground=palette["text_fg"],
                                relief="flat", borderwidth=0, highlightthickness=0)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

        total = ttk.Frame(root, padding=(12, 6, 12, 2))
        total.pack(fill="x", side="bottom")
        total.columnconfigure(1, weight=1)
        self.total_title = ttk.Label(total, font=bold)
        self.total_bar = ttk.Progressbar(total, maximum=1000)
        self.total_label = ttk.Label(total, width=38, anchor="w")
        self.total_title.grid(row=0, column=0, sticky="w")
        self.total_bar.grid(row=0, column=1, sticky="ew", padx=10)
        self.total_label.grid(row=0, column=2, sticky="w")

        self.apply_texts()
        self.build_list_area()
        root.after(TICK_MS, self.tick)
        threading.Thread(target=self.worker, daemon=True).start()

    # --- languages ------------------------------------------------------------------

    def apply_texts(self):
        """(Re)write every text of the window in the interface language."""
        self.add_btn.configure(text=t("add_videos"))
        self.start_btn.configure(text=t("start_all"))
        self.open_btn.configure(text=t("open_results"))
        self.guide_btn.configure(text=t("guide"))
        self.glossary_btn.configure(text=t("glossary"))
        self.meeting_label.configure(text=t("meeting_language") + ":")
        self.meeting_box.configure(values=[i18n.language_name(c) for c in i18n.MEETING_LANGUAGES])
        self.meeting_box.current(i18n.MEETING_LANGUAGES.index(self.meeting_language))
        self.meeting_hint.configure(text=t("meeting_language_hint"))
        self.ui_label.configure(text=t("ui_language") + ":")
        self.hardware.configure(text=self.profile.description if self.profile else t("checking_hardware"))
        if self.warning is not None:
            self.warning.configure(text=t("no_pyannote_banner"))
        self.total_title.configure(text=t("total"))
        self.show_results_folders()

    def on_ui_language(self, _event=None):
        i18n.set_ui_language(list(i18n.UI_LANGUAGES)[self.ui_box.current()])
        self.apply_texts()
        self.build_rows()

    def on_meeting_language(self, _event=None):
        self.meeting_language = i18n.MEETING_LANGUAGES[self.meeting_box.current()]
        i18n.set_meeting_language(self.meeting_language)

    def on_row_language(self, job: Job, box: ttk.Combobox):
        if not job.taken:
            job.language = i18n.MEETING_LANGUAGES[box.current()]

    # --- list of recordings ---------------------------------------------------------

    def build_list_area(self):
        """A scrollable frame: the queue has no length limit."""
        area = ttk.Frame(self.root, padding=(12, 8, 0, 4))
        area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(area, highlightthickness=0, borderwidth=0, background=self.palette["bg"])
        scroll = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 4))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width - 12))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.list_frame.columnconfigure(1, weight=1)
        self.build_rows()

    def _wheel(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

    def build_rows(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.rows = {}
        if not self.jobs:
            ttk.Label(self.list_frame, text=t("empty_list", add=t("add_videos")),
                      foreground=self.palette["muted"]).grid(row=0, column=0, sticky="w")
        for i, job in enumerate(self.jobs):
            name = ttk.Label(self.list_frame, text=job.path.name, width=40, anchor="w")
            name.grid(row=i, column=0, sticky="w", pady=3)
            bar = ttk.Progressbar(self.list_frame, maximum=1000)
            bar.grid(row=i, column=1, sticky="ew", padx=10)
            status = ttk.Label(self.list_frame, width=34, anchor="w")
            status.grid(row=i, column=2, sticky="w")
            language = ttk.Combobox(self.list_frame, state="readonly", width=5,
                                    values=[c.upper() for c in i18n.MEETING_LANGUAGES])
            language.current(i18n.MEETING_LANGUAGES.index(job.language))
            language.bind("<<ComboboxSelected>>", lambda e, j=job, b=language: self.on_row_language(j, b))
            language.grid(row=i, column=3, padx=(6, 0))
            play = ttk.Button(self.list_frame, text="▶" if SYMBOLS else t("play"), width=BUTTON_WIDTH,
                              command=lambda j=job: self.start_one(j))
            play.grid(row=i, column=4, padx=(6, 2))
            remove = ttk.Button(self.list_frame, text="✕" if SYMBOLS else t("remove"), width=BUTTON_WIDTH,
                                command=lambda j=job: self.remove(j))
            remove.grid(row=i, column=5, padx=(2, 0))
            self.rows[job.id] = {"bar": bar, "status": status, "language": language, "play": play, "remove": remove}
        self.refresh()

    def pick(self):
        files = filedialog.askopenfilenames(
            title=t("pick_title"),
            initialdir=str(Path.home() / "Downloads"),
            filetypes=[(t("recordings"), _PATTERNS), (t("all_files"), "*")],
        )
        if files:
            self.add_files(files)

    def add_files(self, files):
        listed = {j.path.resolve(): j for j in self.jobs}
        added = []
        for f in files:
            path = Path(f)
            old = listed.get(path.resolve())
            if old and not (old.finished or old.error):
                continue  # already waiting, queued or running
            if old:
                self.jobs.remove(old)  # done before: add it again as new
            job = Job(path, self.meeting_language)
            self.jobs.append(job)
            added.append(job)
            self.prep.submit(self.estimate, job.id, path, job.language)
        if not added:
            return
        if self.auto:
            self.enqueue(added)
        self.build_rows()
        self.show_results_folders()

    def show_results_folders(self):
        folders = sorted({str(default_out_root(j.path)) for j in self.jobs})
        self.info.configure(text=t("results_in", folders="; ".join(folders)) if folders else "")

    def estimate(self, job_id: int, path: Path, language: str):
        """Background: expected seconds for one file, or the reason it cannot be read."""
        try:
            result = expected_seconds(plan(path, Options(language=language), None, self.token))
        except Exception as exc:
            result = exc
        self.q.put(("estimate", job_id, result))

    def remove(self, job: Job):
        with self.cond:
            if job.taken and not (job.finished or job.error):
                return  # in progress
            if job in self.run_queue:
                self.run_queue.remove(job)
        self.jobs.remove(job)
        self.build_rows()

    # --- running --------------------------------------------------------------------

    def enqueue(self, jobs: list[Job], front: bool = False):
        with self.cond:
            jobs = [j for j in jobs if not j.taken]
            for job in jobs:
                if job in self.run_queue:
                    self.run_queue.remove(job)
                job.queued = True
            if front:
                self.run_queue[0:0] = jobs
            else:
                self.run_queue.extend(jobs)
            self.cond.notify()

    def start_all(self):
        self.auto = True
        self.enqueue([j for j in self.jobs if j.pending and not j.queued])

    def start_one(self, job: Job):
        """Run this recording now, or right after the one in progress."""
        if job.pending:
            self.enqueue([job], front=True)

    def worker(self):
        library = None
        while True:
            with self.cond:
                while not self.run_queue:
                    self.cond.wait()
                job = self.run_queue.pop(0)
                job.taken = True  # from now on it can no longer be removed or re-queued
            if library is None:
                library = VoiceLibrary(DATA_DIR / "voices.json")
            self.q.put(("start", job.id))
            try:
                output = process(job.path, Options(language=job.language), self.token, library,
                                 report=_QueueReporter(self.q, job.id))
                self.q.put(("done", job.id, output))
            except Exception as exc:
                traceback.print_exc()
                self.q.put(("error", job.id, f"{type(exc).__name__}: {exc}"))

    def busy(self) -> bool:
        return any(j.running or j.queued for j in self.jobs)

    def tick(self):
        by_id = {j.id: j for j in self.jobs}
        while True:
            try:
                kind, *rest = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "hardware":
                self.profile = profile = rest[0]
                self.hardware.configure(text=profile.description,
                                        foreground=self.palette["muted"] if profile.gpu else self.palette["warn"])
                continue
            job = by_id.get(rest[0])
            if job is None:
                continue  # removed from the list meanwhile
            if kind == "estimate":
                if isinstance(rest[1], Exception):
                    self.write_log(t("cannot_read", name=job.path.name, error=rest[1]))
                    with self.cond:
                        if not job.taken:
                            job.error, job.queued = "unreadable", False
                            if job in self.run_queue:
                                self.run_queue.remove(job)
                else:
                    job.estimate = rest[1]
            elif kind == "start":
                job.started, job.queued = time.time(), False
                self.write_log(f"== {job.path.name}")
            elif kind == "log":
                self.write_log(rest[1])
            elif kind == "progress":
                job.fraction, job.stage = rest[1], rest[2]
            elif kind == "done":
                job.fraction, job.finished, job.output = 1.0, time.time(), rest[1]
                self.open_btn.configure(state="normal")
            elif kind == "error":
                job.error = rest[1]
                self.batch_errors += 1
                self.write_log(t("error_line", error=rest[1]))
            if kind in ("done", "error") and not self.busy():
                self.auto = False
                if self.batch_errors:
                    messagebox.showwarning("Neon Minutes", t("not_completed", n=self.batch_errors))
                self.batch_errors = 0
        self.refresh()
        self.root.after(TICK_MS, self.tick)

    def speed(self) -> float:
        """Observed time / estimated time, so queued recordings get realistic ETAs."""
        ratios = [(j.finished - j.started) / j.estimate for j in self.jobs if j.finished and j.estimate]
        current = next((j for j in self.jobs if j.running), None)
        if current and current.estimate and current.fraction >= 0.2:
            ratios.append((time.time() - current.started) / (current.fraction * current.estimate))
        return sum(ratios) / len(ratios) if ratios else 1.0

    def refresh(self):
        speed = self.speed()
        with self.cond:
            positions = {job.id: i for i, job in enumerate(self.run_queue, 1)}
        for job in self.jobs:
            row = self.rows.get(job.id)
            if row is None:
                continue
            row["bar"]["value"] = job.fraction * 1000
            eta = _clock(job.eta(speed))
            if job.error:
                text = t("status_error")
            elif job.finished:
                text = t("status_done", time=_clock(job.finished - job.started))
            elif job.started:
                key = f"stage_{job.stage}"
                stage = t(key if key in i18n.T else "stage_start")
                text = t("status_running", stage=stage, pct=f"{job.fraction:.0%}", eta=eta)
            elif job.estimate is None:
                text = t("status_estimating")
            elif job.id in positions:
                text = t("status_queued", n=positions[job.id], eta=eta)
            else:
                text = t("status_waiting", eta=eta)
            row["status"].configure(text=text)
            in_progress = job.taken and not (job.finished or job.error)
            row["language"].configure(state="disabled" if job.taken or job.finished or job.error else "readonly")
            row["play"].configure(state="normal" if job.pending and not job.taken and positions.get(job.id) != 1
                                  else "disabled")
            row["remove"].configure(state="disabled" if in_progress else "normal")

        self.start_btn.configure(state="normal" if any(j.pending and not j.queued for j in self.jobs) else "disabled")
        self.refresh_total(speed)

    def refresh_total(self, speed: float):
        todo = [j for j in self.jobs if not (j.finished or j.error)]
        if len(self.jobs) < 2:
            for widget in (self.total_title, self.total_bar, self.total_label):
                widget.grid_remove()
            return
        for widget in (self.total_title, self.total_bar, self.total_label):
            widget.grid()
        counted = [j for j in self.jobs if not j.error and j.estimate]
        total = sum(j.estimate for j in counted) or 1.0
        done = sum(j.estimate * (1.0 if j.finished else j.fraction) for j in counted)
        self.total_bar["value"] = done / total * 1000
        if not todo:
            self.total_label.configure(text=t("total_done", n=len(self.jobs)))
        elif any(j.estimate is None for j in todo):
            self.total_label.configure(text=t("total_estimating", n=len(todo)))
        else:
            remaining = sum(j.eta(speed) or 0.0 for j in todo)
            self.total_label.configure(text=t("total_eta", n=len(todo), eta=_clock(remaining)))

    # --- misc -----------------------------------------------------------------------

    def write_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def open_output(self):
        done = [j for j in self.jobs if j.output]
        if done:
            last = max(done, key=lambda j: j.finished)
            open_path(last.output.parent)

    def open_file(self, path: Path):
        if path.exists():
            open_path(path)
        else:
            messagebox.showinfo("Neon Minutes", t("file_not_found", path=path))

    def on_close(self):
        if self.busy() and not messagebox.askyesno("Neon Minutes", t("confirm_close")):
            return
        self.root.destroy()
        os._exit(0)  # the worker thread may be inside a GPU call


def main(files: list[str] | None = None):
    """Files given on the command line (or dropped on the shortcut) are added to the list."""
    if sys.stdout is None or sys.stderr is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = _LogFile(DATA_DIR / "gui.log")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk(className="neon-minutes")  # WM_CLASS, matched by the Linux .desktop entry
    if ICON.exists() and sys.platform == "win32":
        root.iconbitmap(default=str(ICON))
    elif ICON_PNG.exists():
        root.iconphoto(True, tk.PhotoImage(file=str(ICON_PNG)))
    palette = theme.apply(root)
    app = App(root, palette)
    files = [f for f in (files if files is not None else sys.argv[1:]) if Path(f).is_file()]
    if files:
        root.after(100, lambda: app.add_files(files))  # once the window is on screen
    root.mainloop()


if __name__ == "__main__":
    main()
