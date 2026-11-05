"""Command line: python -m meeting_transcriber VIDEO [VIDEO ...]  (no arguments opens the GUI)."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .paths import DATA_DIR, setup_environment
from .pipeline import OUTPUT_DIR_NAME, STAGES, Options, Reporter, process
from .voices import VoiceLibrary


class ConsoleReporter(Reporter):
    """Log lines with a timestamp; progress every 10%."""

    def __init__(self):
        self.next = 1

    def log(self, message: str):
        print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)

    def progress(self, fraction: float, stage: str):
        if fraction * 10 >= self.next:
            self.log(f"  {int(fraction * 100)}% ({stage})")
            self.next = int(fraction * 10) + 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from .gui import main as gui_main

        return gui_main()

    p = argparse.ArgumentParser(prog="python -m meeting_transcriber", description=__doc__)
    p.add_argument("videos", nargs="+", type=Path, help="registrazioni (mp4, mkv, ...) o file audio")
    p.add_argument("--out", type=Path, help=f"cartella dei risultati (default: {OUTPUT_DIR_NAME}/ accanto al video)")
    p.add_argument("--model", help="modello Whisper (default: large-v3 su GPU, large-v3-turbo su CPU)")
    p.add_argument("--language", default="it", help="lingua della riunione: it, en, es, fr, pt, zh, ... oppure auto (la riconosce Whisper)")
    p.add_argument("--glossary", nargs="*", default=[], help="termini da suggerire a Whisper (oltre a glossary.txt)")
    p.add_argument("--num-speakers", type=int)
    p.add_argument("--min-speakers", type=int)
    p.add_argument("--max-speakers", type=int)
    p.add_argument("--video-fps", type=float, default=2.0, help="campioni al secondo per leggere i nomi")
    p.add_argument("--no-video", action="store_true", help="non usare il video per i nomi")
    p.add_argument("--voices", type=Path, default=DATA_DIR / "voices.json", help="libreria voci")
    p.add_argument("--no-voices", action="store_true", help="non usare né aggiornare la libreria voci")
    p.add_argument("--redo", nargs="*", default=[], choices=STAGES + ("all",), help="rifai questi passaggi")
    p.add_argument("--cpu", action="store_true", help="non usare la GPU anche se c'è (molto più lento)")
    args = p.parse_args(argv)

    opts = Options(
        model=args.model, language=args.language, glossary=args.glossary,
        num_speakers=args.num_speakers, min_speakers=args.min_speakers, max_speakers=args.max_speakers,
        video_fps=args.video_fps, use_video=not args.no_video, redo=set(args.redo),
        device="cpu" if args.cpu else None,
    )
    token = setup_environment()
    library = None if args.no_voices else VoiceLibrary(args.voices)
    for video in args.videos:
        if not video.exists():
            sys.exit(f"File non trovato: {video}")
    reporter = ConsoleReporter()
    for video in args.videos:
        reporter.next = 1
        reporter.log(f"== {video.name}")
        process(video.resolve(), opts, token, library, out_root=args.out, report=reporter)
