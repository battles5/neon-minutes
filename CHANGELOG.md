# Changelog

## 1.5.1 — 2026-11-05

- **Meeting language menu**: choosing a language now also changes every video in the list that has
  not started yet (before, it applied only to the videos added afterwards, so nothing seemed to
  happen). Each row keeps its own menu for exceptions.
- The meeting language starts as **Detect automatically** instead of the system's language.

## 1.5.0 — 2026-11-05

- **New name: NEON MINUTES** (formerly *Neon Verbale*), now that everything is in English. New
  banner, tagline *names in lights*, and a "Why neon?" section in the README and the guide. The
  repository is now `battles5/neon-minutes`; GitHub redirects the old links.
- **Upgrade without downloads**: the Windows setup moves the installed *Neon Verbale* (or
  *Trascrittore riunioni*) folder to *Neon Minutes*, replaces the old shortcuts and keeps an icon
  pinned to the taskbar working; voices, glossary, timings and models move to the new data folder.
  On Linux the `.run` file moves `~/.local/lib/neon-verbale`, replaces the `neon-verbale` command
  with `neon-minutes` and the data folder follows.
- The Linux build on GitHub Actions now also tests the upgrade from Neon Verbale 1.4.0.
- Linux: installing a new version over an existing one stopped while copying the bundled Python
  (its symbolic links already existed). Found by the new upgrade test, now fixed.

## 1.4.0 — 2026-11-05

- **Window in six languages**: English, Italian, Spanish, French, Portuguese and Chinese, chosen
  from the **Interface** menu and switched at once; the first time the program uses the system's
  language. Chinese is offered on Windows only (Linux's bundled Tk cannot draw it).
- **Meeting language**: a menu for the language of the meetings (the same six, or automatic
  detection by Whisper), remembered between sessions. Each video in the list has its own
  language, changeable until it starts. The names and terms suggested to Whisper are introduced
  in the meeting's language. Processing a video again with a different language redoes the
  transcription. On the command line: `--language auto`.
- The progress log and the hardware line follow the interface language.
- Setup: the progress page showed "?" instead of "·" and accented letters; the icon in the
  wizard's header no longer touches the right edge.
- The Linux build on GitHub Actions also transcribes an English clip with automatic detection
  and takes a screenshot of the window in every language.

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
