# Changelog

## 1.3.0 — 2026-11-05

- **Linux x86_64 installer**: `NeonVerbale-<version>-linux-x86_64.run`, a self-extracting file
  with portable Python, the program, the pyannote model and the guide.
  - On a graphical desktop it shows a wizard in the Neon Verbale style: licence, hardware check
    with GB to download, disk space and time, progress with ETA, final page.
  - Without a desktop it runs in the terminal.
  - Installs in the home folder, no `sudo`: an entry in the applications menu and the
    `neon-verbale` command (also `--trascrivi`, `--ripara`, `--disinstalla`).
  - NVIDIA GPU with CUDA as on Windows, CPU otherwise.
- The Linux installer is built and tested by GitHub Actions for every release: installation, a test
  transcription, window and wizard on a virtual screen, uninstall.
- Portable code: XDG data folder on Linux, window icon, file filters that also accept upper-case
  extensions.
- Documentation (README, user guide, changelog) now in English; the guide is `docs/Guide.html`.
  The program's window stays in Italian.

## 1.2.0 — 2026-11-05

- **New name: NEON VERBALE** (formerly *Trascrittore riunioni*), with a synthwave icon (a neon
  quill on a striped sun), a banner and installer wizard images in the same style. The repository
  is now `battles5/neon-verbale`; GitHub redirects the old links.
- **Lossless upgrade:** the setup installs over *Trascrittore riunioni* (same identifier), removes
  the old Start menu and desktop shortcuts and, at the first start, moves the data folder (voices,
  glossary, timings, models) under the new name.
- User guide in the colours of the new style.

## 1.1.0 — 2026-11-05

- **Recording queue.** "Aggiungi video…" (add videos) stays active during processing and videos
  queue up without limits, in a scrolling list. "Avvia tutti" (start all) queues everything that is
  waiting: while the queue is active, videos added later join it by themselves. On each row, ▶
  starts that video (or puts it first in the queue) and ✕ removes it from the list. The same video
  cannot be in the list twice.
- **Total ETA** of everything left to do, recomputed at every addition or removal, besides each
  video's ETA and queue position.
- **Light or dark theme** following Windows (read at start-up), with a dark title bar in the dark
  theme. New dependencies: sv-ttk (MIT) and darkdetect (BSD-3-Clause).
- "Apri cartella risultati" (open results folder) opens the folder of the last completed video.

## 1.0.1 — 2026-10-22

- **Fixed the window freezing after choosing a video.** The time estimate and the graphics card
  detection loaded PyTorch and faster-whisper in the window's thread, while another thread loaded
  the same CUDA libraries. On the first start after boot this can take more than a minute, and
  Windows marked the window as "Not responding". These operations now run in the background, one
  at a time: the window responds immediately, the file's row shows "calcolo della stima…"
  (computing the estimate) and "Avvia" (start) is enabled when the estimate is ready.
- Videos dropped on the icon open the window immediately, instead of waiting for the estimate.
- The "nomi + voci" (names + voices) label no longer stays lit after name reading ends.
- Tested with Windows screen recordings (Snipping Tool: H.264 mp4 1672×1420 at 30 fps, AAC stereo
  audio at 48 kHz).

## 1.0.0 — 2026-10-21

First public release.
