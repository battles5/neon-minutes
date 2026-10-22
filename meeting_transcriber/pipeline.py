"""Transcribe one meeting: stages, caches and progress reporting, shared by the CLI and the GUI.

Results go to <out_root>/<video name>/: trascrizione.{md,srt,vtt,json} and speakers.json,
with each stage's raw result cached in _lavoro/. A re-run only redoes what is missing
or what Options.redo asks for, so editing a name in speakers.json and re-running
regenerates the transcript in seconds.
"""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

import av

from . import hardware, naming
from .asr import build_prompt, is_model_cached, transcribe
from .audio import load_audio
from .diarize import available as diarization_available
from .diarize import diarize, turns_from_video
from .paths import DATA_DIR, glossary_path
from .render import attribute_words, paragraphs, write_outputs
from .video_labels import scan_speaker_labels
from .voices import VoiceLibrary

OUTPUT_DIR_NAME = "Trascrizioni"
STAGES = ("video", "diarization", "asr", "names")
# Seconds of work per second of recording, plus model loading. GPU figures measured on an
# RTX 2000 Ada laptop, CPU ones on an i7-14700HX. Used for ETAs; every run refines them in
# timings.json, since Whisper's speed varies with the audio and with the GPU's clocks.
RATE = {
    "cuda": {"audio": 0.004, "video": 0.037, "diarization": 0.06, "asr": 0.15},
    "cpu": {"audio": 0.004, "video": 0.05, "diarization": 0.65, "asr": 0.8},
}
OVERHEAD_S = {"audio": 1.0, "video": 2.0, "diarization": 10.0, "asr": 8.0}
FINISH_S = 2.0
MODEL_DOWNLOAD_S = 180.0  # first run only: Whisper weights are 1.6-3 GB
TIMINGS_PATH = DATA_DIR / "timings.json"
_timings_lock = threading.Lock()


def _rates(device: str) -> dict[str, float]:
    rates = dict(RATE[device])
    try:
        rates.update(json.loads(TIMINGS_PATH.read_text(encoding="utf-8")).get(device, {}))
    except (OSError, ValueError, AttributeError):
        pass
    return rates


def _record_rate(device: str, stage: str, seconds: float, duration: float):
    """Blend a measured stage speed into timings.json (half old, half new)."""
    if duration <= 0:
        return
    with _timings_lock:
        try:
            stored = json.loads(TIMINGS_PATH.read_text(encoding="utf-8"))
            if not isinstance(stored.get(device, {}), dict):
                stored = {}
        except (OSError, ValueError, AttributeError):
            stored = {}
        rates = _rates(device)
        measured = max(seconds - OVERHEAD_S[stage], 0.0) / duration
        rates[stage] = round((rates[stage] + measured) / 2, 4)
        stored[device] = rates
        TIMINGS_PATH.write_text(json.dumps(stored, indent=1), encoding="utf-8")


TEAMS_FILENAME = re.compile(r"^(?P<title>.*?)-(?P<date>\d{8})_(?P<time>\d{6})-")
SPEAKERS_HELP = (
    "Per correggere un nome cambia il campo 'name' e rilancia: si rigenerano solo i file "
    "trascrizione.*, e la voce corretta entra nella libreria voci."
)


@dataclass
class Options:
    """model, device and compute_type left as None are chosen from the hardware profile."""

    model: str | None = None
    language: str = "it"
    glossary: list[str] = field(default_factory=list)
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    video_fps: float = 2.0
    use_video: bool = True
    redo: set[str] = field(default_factory=set)
    device: str | None = None
    compute_type: str | None = None

    def resolved(self) -> "Options":
        if self.device == "cpu" and not (self.model and self.compute_type):
            profile = hardware.cpu_profile("CPU richiesta")
        else:
            profile = hardware.detect()
        return replace(
            self,
            device=self.device or profile.device,
            compute_type=self.compute_type or profile.compute_type,
            model=self.model or profile.model,
        )


class Reporter:
    """Receives a meeting's log lines and overall progress; the base class ignores them."""

    def log(self, message: str):
        pass

    def progress(self, fraction: float, stage: str):
        pass


def default_out_root(video: Path) -> Path:
    return video.parent / OUTPUT_DIR_NAME


def meeting_dir(video: Path, out_root: Path | None) -> Path:
    return (out_root or default_out_root(video)) / video.stem


def media_duration(path: Path) -> float:
    with av.open(str(path)) as container:
        return container.duration / av.time_base if container.duration else 0.0


def has_video(path: Path) -> bool:
    with av.open(str(path)) as container:
        return bool(container.streams.video)


def meeting_meta(video: Path) -> dict:
    m = TEAMS_FILENAME.match(video.stem)
    if m:
        when = datetime.strptime(m["date"] + m["time"], "%Y%m%d%H%M%S")
        return {"title": m["title"], "date": when.strftime("%d/%m/%Y %H:%M"), "id": f"{m['title']}-{m['date']}"}
    return {"title": video.stem, "date": None, "id": video.stem}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data, indent=None):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")


def load_glossary(extra: list[str]) -> list[str]:
    terms = list(extra)
    path = glossary_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                terms.append(line)
    return list(dict.fromkeys(terms))


def _load_speakers(path: Path) -> dict:
    """Read speakers.json; a name the user changed counts as a manual identification."""
    speakers = _read_json(path)["speakers"]
    for info in speakers.values():
        if info.get("auto") is not None and info["name"] != info["auto"]:
            info["source"] = "manual"
            info.pop("confidence", None)
    return speakers


def _save_speakers(path: Path, speakers: dict, lag_s):
    for info in speakers.values():
        info.setdefault("auto", info["name"])
    _write_json(path, {"_istruzioni": SPEAKERS_HELP, "video_lag_s": lag_s, "speakers": speakers}, indent=2)


def plan(video: Path, opts: Options, out_root: Path | None, token: str | None) -> dict[str, float]:
    """Expected seconds of each stage that still has to run (cached stages are left out)."""
    opts = opts.resolved()
    work = meeting_dir(video, out_root) / "_lavoro"
    redo = set(STAGES) if "all" in opts.redo else opts.redo
    duration = media_duration(video)
    needed = {
        "video": opts.use_video and has_video(video) and ("video" in redo or not (work / "labels.json").exists()),
        "diarization": diarization_available(token)
        and ("diarization" in redo or not (work / "diarization.json").exists()),
        "asr": "asr" in redo or not (work / "asr.json").exists(),
    }
    needed["audio"] = needed["diarization"] or needed["asr"]
    rates = _rates(opts.device)
    stages = {s: rates[s] * duration + OVERHEAD_S[s] for s, need in needed.items() if need}
    if "asr" in stages and not is_model_cached(opts.model):
        stages["asr"] += MODEL_DOWNLOAD_S
    return stages


def expected_seconds(stages: dict[str, float]) -> float:
    """The video scan runs alongside the diarization, so only the longer of the two counts."""
    parallel = max(stages.get("video", 0.0), stages.get("diarization", 0.0))
    return stages.get("audio", 0.0) + parallel + stages.get("asr", 0.0) + FINISH_S


class _Progress:
    """Fold per-stage fractions into one fraction for the meeting."""

    def __init__(self, stages: dict[str, float], report: Reporter):
        self.stages = stages
        self.done = {s: 0.0 for s in stages}
        self.total = expected_seconds(stages)
        self.report = report
        self.lock = threading.Lock()

    def stage(self, name: str):
        return lambda fraction: self.update(name, fraction)

    def update(self, name: str, fraction: float):
        with self.lock:
            self.done[name] = max(self.done.get(name, 0.0), min(fraction, 1.0))
            sec = {s: self.stages.get(s, 0.0) * self.done.get(s, 0.0) for s in OVERHEAD_S}
            elapsed = sec["audio"] + max(sec["video"], sec["diarization"]) + sec["asr"]
            running = [s for s in ("video", "diarization") if s in self.done and self.done[s] < 1.0]
            stage = "parallel" if len(running) == 2 else name
            self.report.progress(min(elapsed / self.total, 0.99), stage)


def process(
    video: Path,
    opts: Options,
    token: str | None,
    library: VoiceLibrary | None,
    out_root: Path | None = None,
    report: Reporter | None = None,
) -> Path:
    """Run every stage that is not cached; return the path of trascrizione.md."""
    report = report or Reporter()
    log = report.log
    opts = opts.resolved()
    meta = meeting_meta(video)
    out_dir = meeting_dir(video, out_root)
    work = out_dir / "_lavoro"
    work.mkdir(parents=True, exist_ok=True)
    redo = set(STAGES) if "all" in opts.redo else set(opts.redo)
    paths = {s: work / f"{s}.json" for s in ("labels", "diarization", "asr")}
    speakers_path = out_dir / "speakers.json"
    progress = _Progress(plan(video, opts, out_root, token), report)
    duration = media_duration(video)
    fresh = set()
    started = time.time()

    audio = None

    def get_audio():
        nonlocal audio
        if audio is None:
            log("Decodifica audio...")
            t = time.time()
            audio = load_audio(video)
            _record_rate(opts.device, "audio", time.time() - t, duration)
            progress.update("audio", 1.0)
        return audio

    # The video scan is CPU-only: run it while the GPU does the diarization.
    with ThreadPoolExecutor(max_workers=1) as pool:
        labels_job = None
        if "video" in progress.stages:
            log(f"Lettura dei nomi dal video ({opts.video_fps:g} fps)...")

            def scan():
                t = time.time()
                samples = scan_speaker_labels(video, fps=opts.video_fps, progress=progress.stage("video"))
                progress.update("video", 1.0)  # the last sampled frame is a little before the end
                _write_json(paths["labels"], {"fps": opts.video_fps, "samples": samples})
                _record_rate(opts.device, "video", time.time() - t, duration)
                log(f"  video letto in {time.time() - t:.0f}s")
                return samples

            labels_job = pool.submit(scan)
            fresh.add("video")

        diarization = None
        if "diarization" in progress.stages:
            wave = get_audio()
            log("Separazione delle voci (pyannote)...")
            t = time.time()
            diarization = diarize(
                wave, token, device=opts.device, progress=progress.stage("diarization"),
                num_speakers=opts.num_speakers, min_speakers=opts.min_speakers, max_speakers=opts.max_speakers,
            )
            progress.update("diarization", 1.0)
            _write_json(paths["diarization"], diarization)
            _record_rate(opts.device, "diarization", time.time() - t, duration)
            log(f"  voci separate in {time.time() - t:.0f}s: {len(diarization['embeddings'])} voci")
            fresh.add("diarization")
        elif paths["diarization"].exists():
            diarization = _read_json(paths["diarization"])

        samples, fps = [], opts.video_fps
        if labels_job:
            samples = labels_job.result()
        elif opts.use_video and paths["labels"].exists():
            labels = _read_json(paths["labels"])
            samples, fps = labels["samples"], labels["fps"]

    roster = naming.build_roster(samples)
    names = naming.participants(roster)
    if names:
        log(f"Nomi letti dal video: {', '.join(names)}")
    elif opts.use_video:
        log("Nessuna etichetta Teams evidenziata nel video.")

    if diarization is None:
        if not samples:
            raise RuntimeError("Modello pyannote non disponibile: serve HF_TOKEN nel file .env (vedi la guida).")
        log("ATTENZIONE: modello pyannote non disponibile, attribuisco gli speaker solo dal video (meno preciso).")
        diarization = turns_from_video(samples, roster, fps)

    if "asr" in progress.stages:
        prompt = build_prompt(names, load_glossary(opts.glossary))
        wave = get_audio()
        downloading = not is_model_cached(opts.model)
        if downloading:
            log(f"Scarico il modello Whisper {opts.model} (1,6-3 GB, solo la prima volta)...")
        log(f"Trascrizione ({opts.model}, {opts.device})...")
        t = time.time()
        asr = transcribe(wave, model_name=opts.model, language=opts.language, prompt=prompt,
                         device=opts.device, compute_type=opts.compute_type, progress=progress.stage("asr"))
        _write_json(paths["asr"], asr)
        default_model = hardware.GPU_MODEL if opts.device == "cuda" else hardware.CPU_MODEL
        if opts.model == default_model and not downloading:
            _record_rate(opts.device, "asr", time.time() - t, duration)
        log(f"  trascrizione fatta in {time.time() - t:.0f}s")
        fresh.add("asr")
    else:
        asr = _read_json(paths["asr"])

    turns = diarization["turns"]
    if speakers_path.exists() and not ("names" in redo or fresh & {"diarization"}):
        speakers = _load_speakers(speakers_path)
        lag_s = _read_json(speakers_path).get("video_lag_s")
    elif diarization["model"] == "video-only":
        speakers = {
            n: {"name": n, "source": "video-only", "speech_s": round(s, 1)}
            for n, s in naming.speech_seconds(turns).items()
        }
        lag_s = None
    else:
        video_names = naming.name_from_video(samples, roster, turns, fps) if samples else None
        voice = library.match(diarization["embeddings"], meta["id"]) if library else {}
        speakers = naming.resolve(turns, video_names, voice)
        lag_s = video_names["lag_s"] if video_names else None
        if lag_s is not None:
            log(f"Ritardo evidenziazione Teams stimato: {lag_s:+.2f}s")
    _save_speakers(speakers_path, speakers, lag_s)
    for cluster, info in speakers.items():
        log(f"  {cluster}: {info['name']}  [{info.get('source') or '-'}, {info['speech_s']:.0f}s]")

    if library is not None and diarization["embeddings"]:
        learned = library.update(meta["id"], speakers, diarization["embeddings"])
        library.save()
        if learned:
            log(f"Libreria voci aggiornata: {', '.join(sorted(set(learned)))}")

    names_by_cluster = {cluster: info["name"] for cluster, info in speakers.items()}
    paras = paragraphs(attribute_words(asr["segments"], turns), names_by_cluster)
    meta.update(duration_s=round(duration, 1), source=str(video), asr_model=asr["model"],
                diarization_model=diarization["model"], video_lag_s=lag_s)
    outputs = write_outputs(out_dir, meta, speakers, paras)
    report.progress(1.0, "fatto")
    log(f"Fatto in {time.time() - started:.0f}s -> {outputs[0]}")
    return outputs[0]
