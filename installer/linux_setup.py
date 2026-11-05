"""Neon Verbale installer for Linux, run by the self-extracting .run file with the bundled Python.

    sh NeonVerbale-<version>-linux-x86_64.run [--cli] [-y] [--cpu] [--no-models] [--no-desktop]

With a graphical session it shows a small wizard (licence, hardware and space summary,
progress with ETA, finish page); otherwise, or with --cli, it works in the terminal.
Everything goes in the user's home, no root needed:
  ~/.local/lib/neon-verbale            program, bundled Python, libraries (pip)
  ~/.local/share/neon-verbale          data: voices, glossary, models (kept on uninstall)
  ~/.local/bin/neon-verbale            launcher (GUI; --trascrivi, --ripara, --disinstalla)
  ~/.local/share/applications/...      menu entry, plus the icon

The installed copy keeps this script to uninstall:  neon-verbale --disinstalla
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import postinstall  # noqa: E402  (hardware detection shared with Windows)

HOME = Path.home()
APP_DIR = HOME / ".local" / "lib" / "neon-verbale"
BIN = HOME / ".local" / "bin" / "neon-verbale"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local" / "share")
DESKTOP_ENTRY = DATA_HOME / "applications" / "neon-verbale.desktop"
ICON = DATA_HOME / "icons" / "hicolor" / "256x256" / "apps" / "neon-verbale.png"
DATA_DIR = DATA_HOME / "neon-verbale"
MIN_GLIBC = (2, 28)  # manylinux_2_28 wheels of PyTorch and ONNX Runtime
COLORS = {"bg": "#140a2a", "panel": "#1e1040", "fg": "#ece6f7", "muted": "#a99bc4",
          "accent": "#ff2975", "cyan": "#2de2e6", "button": "#2c1858"}


def gb(n: float) -> str:
    return f"{n / 1e9:.1f}".replace(".", ",") + " GB"


# --- what will be installed ---------------------------------------------------------------

class Plan:
    def __init__(self, payload: Path, force_cpu: bool, models: bool):
        self.payload = payload
        self.sizes = json.loads((payload / "installer" / "sizes.json").read_text(encoding="utf-8"))
        self.variant, self.reason = ("cpu", "versione per CPU richiesta") if force_cpu else postinstall.detect_variant()
        self.models = models
        self.version = (payload / "meeting_transcriber" / "__init__.py").read_text(encoding="utf-8")
        self.version = self.version.split('__version__ = "')[1].split('"')[0]

    @property
    def download(self) -> int:
        d = self.sizes["download"]
        total = d["torch"][self.variant] + d["deps"]
        return total + (d["whisper"][self.variant] if self.models else 0)

    @property
    def disk(self) -> int:
        model = self.sizes["download"]["whisper"][self.variant] if self.models else 0
        return self.sizes["installed"][self.variant] + model

    @property
    def peak(self) -> int:
        return self.disk + self.sizes["download"]["torch"][self.variant]

    def problems(self) -> list[str]:
        found = []
        if platform.machine() not in ("x86_64", "AMD64"):
            found.append(f"Serve un PC x86_64 (questo è {platform.machine()}).")
        try:  # the system's glibc ("glibc 2.39"); platform.libc_ver() reads the Python binary instead
            name, version = os.confstr("CS_GNU_LIBC_VERSION").split()
        except (ValueError, OSError, AttributeError):
            name, version = "", ""
        if name == "glibc" and tuple(int(x) for x in version.split(".")[:2]) < MIN_GLIBC:
            found.append(f"Serve glibc 2.28 o successiva (questa è {version}): una distribuzione più recente.")
        elif name != "glibc":
            found.append("Questa distribuzione non usa glibc (per esempio Alpine): PyTorch non è disponibile.")
        free = shutil.disk_usage(HOME).free
        if free < self.peak:
            found.append(f"Spazio libero nella cartella home: {gb(free)}, ne servono circa {gb(self.peak)}.")
        return found

    def summary(self) -> str:
        d = self.sizes["download"]
        mode = ("GPU NVIDIA (modalità veloce): una riunione di un'ora in circa 12-15 minuti"
                if self.variant == "cuda" else
                "CPU: funziona su qualunque PC ma è più lenta (un'ora di riunione in circa 1 ora e mezza "
                "su un processore potente, 2-3 ore su un portatile da ufficio)")
        if self.variant == "cpu" and "nessuna GPU" not in self.reason and "richiesta" not in self.reason:
            mode += f"\n({self.reason})"
        elif self.variant == "cuda":
            mode += f"\n(trovata {self.reason})"
        whisper = d["whisper"][self.variant]
        lines = [
            f"Verrà installata la versione per {mode}.",
            "",
            f"DA SCARICARE: circa {gb(self.download)}",
            f"  - PyTorch: {gb(d['torch'][self.variant])}",
            f"  - altre librerie: {gb(d['deps'])}",
            f"  - modello Whisper: {gb(whisper)}" if self.models
            else f"  - modello Whisper ({gb(whisper)}): al primo utilizzo",
            "",
            f"SPAZIO SU DISCO: circa {gb(self.disk)} a installazione finita, fino a {gb(self.peak)} durante "
            "l'installazione.",
            "",
            f"TEMPO INDICATIVO: circa {self.minutes(50)} minuti con 50 Mbit/s, {self.minutes(200)} a 200 Mbit/s.",
            "",
            f"Programma in {APP_DIR}, dati in {DATA_DIR}. Non servono permessi di amministratore.",
        ]
        return "\n".join(lines)

    def minutes(self, mbit: int) -> int:
        return int(self.download * 8 / (mbit * 1e6) / 60) + (8 if self.variant == "cuda" else 5)


# --- installing -----------------------------------------------------------------------------

def copy_program(payload: Path):
    """Copy the payload into APP_DIR; on an upgrade the libraries pip installed stay."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("meeting_transcriber", "installer", "docs", "assets", "models"):
        shutil.rmtree(APP_DIR / name, ignore_errors=True)
    shutil.copytree(payload, APP_DIR, dirs_exist_ok=True, symlinks=True)
    site = next((APP_DIR / "runtime" / "lib").glob("python3.*")) / "site-packages"
    # A .pth file makes the program importable from any working directory.
    (site / "neon_verbale.pth").write_text(str(APP_DIR) + "\n", encoding="utf-8")


def run_postinstall(plan: Plan, wizard: bool, on_line=None) -> int:
    cmd = [str(APP_DIR / "runtime" / "bin" / "python3"), *postinstall.PY, "-u",
           str(APP_DIR / "installer" / "postinstall.py"), "--app", str(APP_DIR), "--variant", plan.variant]
    if plan.models:
        cmd.append("--models")
    if wizard:
        cmd.append("--wizard")
    # pip unpacks multi-GB wheels in TMPDIR, which is a small RAM disk on some distributions.
    tmp = APP_DIR / ".tmp"
    tmp.mkdir(exist_ok=True)
    env = {**os.environ, "TMPDIR": str(tmp)}
    try:
        if on_line is None:
            return subprocess.call(cmd, env=env)
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1)
        for line in proc.stdout:
            on_line(line.rstrip("\n"))
        return proc.wait()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


LAUNCHER = """#!/bin/sh
# Neon Verbale launcher (written by the installer).
APP="{app}"
PY="$APP/runtime/bin/python3"
# CUDA libraries installed by pip (nvidia-*): CTranslate2 looks them up by name.
for d in "$APP"/runtime/lib/python3.*/site-packages/nvidia/*/lib; do
    [ -d "$d" ] && LD_LIBRARY_PATH="$d${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
done
export LD_LIBRARY_PATH
# -I: isolated, so neither the working directory (which may hold another copy of the code), the
# user's site-packages nor PYTHON* variables get in; the program is found via neon_verbale.pth.
case "$1" in
    --trascrivi) shift; exec "$PY" -I -m meeting_transcriber "$@" ;;
    --ripara) exec "$PY" -I -u "$APP/installer/postinstall.py" --app "$APP" --variant auto --models ;;
    --disinstalla) shift; exec "$PY" -I "$APP/installer/linux_setup.py" --uninstall "$@" ;;
    -h|--help)
        echo "neon-verbale [file...]           apre la finestra (con i file indicati)"
        echo "neon-verbale --trascrivi file    trascrive da terminale (--help per le opzioni)"
        echo "neon-verbale --ripara            reinstalla PyTorch e le librerie"
        echo "neon-verbale --disinstalla       rimuove il programma"
        exit 0 ;;
    *) exec "$PY" -I -m meeting_transcriber.gui "$@" ;;
esac
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=Neon Verbale
GenericName=Trascrizione di riunioni
Comment=Trascrivi le riunioni con i nomi di chi parla, tutto sul tuo PC
Exec="{bin}" %F
Icon=neon-verbale
Terminal=false
Categories=AudioVideo;Audio;Utility;
MimeType=video/mp4;video/x-matroska;video/quicktime;video/webm;video/x-msvideo;audio/mpeg;audio/mp4;audio/x-wav;audio/ogg;
StartupWMClass=Neon-verbale
Actions=guida;disinstalla;

[Desktop Action guida]
Name=Guida
Exec=xdg-open "{app}/docs/Guide.html"

[Desktop Action disinstalla]
Name=Disinstalla Neon Verbale
Exec="{bin}" --disinstalla
"""


def desktop_dir() -> Path | None:
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=10).stdout.strip()
        path = Path(out) if out else HOME / "Desktop"
    except (OSError, subprocess.TimeoutExpired):
        path = HOME / "Desktop"
    return path if path.is_dir() and path != HOME else None


def create_shortcuts(desktop_icon: bool):
    BIN.parent.mkdir(parents=True, exist_ok=True)
    BIN.write_text(LAUNCHER.format(app=APP_DIR), encoding="utf-8")
    BIN.chmod(0o755)
    ICON.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(APP_DIR / "assets" / "piuma.png", ICON)
    entry = DESKTOP.format(bin=BIN, app=APP_DIR)
    DESKTOP_ENTRY.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP_ENTRY.write_text(entry, encoding="utf-8")
    for tool in (["update-desktop-database", str(DESKTOP_ENTRY.parent)],
                 ["gtk-update-icon-cache", "-q", "-t", str(DATA_HOME / "icons" / "hicolor")]):
        try:
            subprocess.run(tool, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
    desk = desktop_dir() if desktop_icon else None
    if desk:
        link = desk / "neon-verbale.desktop"
        link.write_text(entry, encoding="utf-8")
        link.chmod(0o755)
        try:  # GNOME asks for confirmation before running untrusted launchers
            subprocess.run(["gio", "set", str(link), "metadata::trusted", "true"], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


def install(plan: Plan, desktop_icon: bool, wizard_lines=None) -> int:
    copy_program(plan.payload)
    code = run_postinstall(plan, wizard=wizard_lines is not None, on_line=wizard_lines)
    if code == 0:
        create_shortcuts(desktop_icon)
    return code


# --- terminal -------------------------------------------------------------------------------

def terminal(args, plan: Plan) -> int:
    print(f"\n  N E O N   V E R B A L E   {plan.version}\n  verbali al neon\n")
    problems = plan.problems()
    print(plan.summary() + "\n")
    for p in problems:
        print("ATTENZIONE: " + p)
    if not args.yes:
        answer = input("Installare? [S/n] ").strip().lower()
        if answer not in ("", "s", "si", "sì", "y", "yes"):
            return 1
    code = install(plan, desktop_icon=not args.no_desktop)
    if code == 0:
        print(f"\nInstallato. Avvia «Neon Verbale» dal menu delle applicazioni, oppure: {BIN}")
        if str(BIN.parent) not in os.environ.get("PATH", "").split(os.pathsep):
            print(f"(Per usare il comando neon-verbale da terminale aggiungi {BIN.parent} al PATH.)")
    else:
        print(f"\nInstallazione non riuscita. Dettagli in {APP_DIR / 'install.log'}; riprova con: {BIN} --ripara")
    return code


# --- wizard ---------------------------------------------------------------------------------

def wizard(args, plan: Plan) -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk(className="neon-verbale-setup")
    root.title(f"Installazione di Neon Verbale {plan.version}")
    root.geometry("760x620")
    root.minsize(680, 560)
    root.configure(background=COLORS["bg"])
    icon_png = plan.payload / "assets" / "piuma.png"
    if icon_png.exists():
        root.iconphoto(True, tk.PhotoImage(file=str(icon_png)))

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=COLORS["bg"], foreground=COLORS["fg"], fieldbackground=COLORS["panel"])
    style.configure("TButton", background=COLORS["button"], foreground=COLORS["fg"], borderwidth=0, padding=(14, 6))
    style.map("TButton", background=[("active", COLORS["accent"]), ("disabled", COLORS["panel"])],
              foreground=[("disabled", COLORS["muted"])])
    style.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["fg"])
    style.map("TCheckbutton", background=[("active", COLORS["bg"])])
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Title.TLabel", font=("TkDefaultFont", 13, "bold"), foreground=COLORS["cyan"])
    style.configure("Horizontal.TProgressbar", background=COLORS["accent"], troughcolor=COLORS["panel"],
                    bordercolor=COLORS["panel"], lightcolor=COLORS["accent"], darkcolor=COLORS["accent"])

    banner_path = plan.payload / "assets" / "banner.png"
    if banner_path.exists():
        banner = tk.PhotoImage(file=str(banner_path)).subsample(2)
        tk.Label(root, image=banner, borderwidth=0, background=COLORS["bg"]).pack(side="top")
        root._banner = banner  # keep a reference
    body = ttk.Frame(root, padding=(24, 16, 24, 8))
    body.pack(fill="both", expand=True)
    buttons = ttk.Frame(root, padding=(24, 0, 24, 18))
    buttons.pack(fill="x", side="bottom")
    back_btn = ttk.Button(buttons, text="Indietro")
    next_btn = ttk.Button(buttons, text="Avanti")
    cancel_btn = ttk.Button(buttons, text="Annulla", command=root.destroy)
    cancel_btn.pack(side="right")
    next_btn.pack(side="right", padx=8)
    back_btn.pack(side="right")

    def text_box(parent, content, height):
        box = tk.Text(parent, height=height, wrap="word", background=COLORS["panel"], foreground=COLORS["fg"],
                      relief="flat", borderwidth=0, highlightthickness=0, padx=10, pady=8)
        box.insert("1.0", content)
        box.configure(state="disabled")
        return box

    accepted = tk.BooleanVar(value=False)
    models = tk.BooleanVar(value=plan.models)
    desktop = tk.BooleanVar(value=not args.no_desktop)
    launch = tk.BooleanVar(value=True)
    guide = tk.BooleanVar(value=False)
    result = {"code": 1}
    pages = []

    def page_license():
        f = ttk.Frame(body)
        ttk.Label(f, text="Contratto di licenza", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="Neon Verbale è software libero: puoi usarlo, modificarlo e ridistribuirlo senza obblighi.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        text_box(f, (plan.payload / "LICENSE.txt").read_text(encoding="utf-8"), 12).pack(fill="both", expand=True)
        ttk.Checkbutton(f, text="Accetto i termini della licenza", variable=accepted,
                        command=lambda: next_btn.configure(state="normal" if accepted.get() else "disabled")
                        ).pack(anchor="w", pady=(8, 0))
        return f

    def page_summary():
        f = ttk.Frame(body)
        ttk.Label(f, text="Verifica dell'hardware e spazio necessario", style="Title.TLabel").pack(anchor="w")
        summary = text_box(f, "", 13)
        summary.pack(fill="both", expand=True, pady=(8, 8))

        def refresh():
            plan.models = models.get()
            summary.configure(state="normal")
            summary.delete("1.0", "end")
            summary.insert("1.0", plan.summary())
            for p in plan.problems():
                summary.insert("end", "\n\nATTENZIONE: " + p)
            summary.configure(state="disabled")

        ttk.Checkbutton(f, text="Scarica subito il modello Whisper (consigliato)", variable=models,
                        command=refresh).pack(anchor="w")
        ttk.Checkbutton(f, text="Crea un collegamento sul desktop", variable=desktop).pack(anchor="w")
        f.refresh = refresh
        return f

    def page_progress():
        f = ttk.Frame(body)
        ttk.Label(f, text="Installazione dei componenti", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="Scarico e installo PyTorch, le librerie e il modello Whisper. Puoi continuare a usare il PC.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 18))
        f.first = ttk.Label(f, text="Copia del programma...")
        f.first.pack(anchor="w")
        f.second = ttk.Label(f, text="", style="Muted.TLabel")
        f.second.pack(anchor="w", pady=(2, 10))
        f.bar = ttk.Progressbar(f, maximum=1000)
        f.bar.pack(fill="x")
        return f

    def page_finish():
        f = ttk.Frame(body)
        f.title = ttk.Label(f, text="", style="Title.TLabel")
        f.title.pack(anchor="w")
        f.message = ttk.Label(f, text="", wraplength=680, justify="left")
        f.message.pack(anchor="w", pady=(8, 14))
        f.launch = ttk.Checkbutton(f, text="Avvia Neon Verbale", variable=launch)
        f.launch.pack(anchor="w")
        f.guide = ttk.Checkbutton(f, text="Apri la guida", variable=guide)
        f.guide.pack(anchor="w")
        return f

    pages = [page_license(), page_summary(), page_progress(), page_finish()]
    current = {"i": 0}

    def show(i):
        for p in pages:
            p.pack_forget()
        current["i"] = i
        pages[i].pack(fill="both", expand=True)
        back_btn.configure(state="normal" if i == 1 else "disabled")
        if i == 0:
            next_btn.configure(text="Avanti", state="normal" if accepted.get() else "disabled")
        elif i == 1:
            pages[1].refresh()
            next_btn.configure(text="Installa", state="normal")
        elif i == 2:
            next_btn.configure(state="disabled")
            back_btn.configure(state="disabled")
            cancel_btn.configure(state="disabled")
            start_install()
        else:
            next_btn.configure(text="Fine", state="normal")
            cancel_btn.configure(state="disabled")

    def go_next():
        i = current["i"]
        if i == 1 and plan.problems() and not messagebox.askyesno(
                "Neon Verbale", "Ci sono avvisi nel riepilogo. Continuare comunque?"):
            return
        if i < 3:
            show(i + 1)
        else:
            if result["code"] == 0 and launch.get():
                subprocess.Popen([str(BIN)], start_new_session=True)
            if result["code"] == 0 and guide.get():
                subprocess.Popen(["xdg-open", str(APP_DIR / "docs" / "Guide.html")], start_new_session=True)
            root.destroy()

    def start_install():
        prog = pages[2]
        lines = []

        def on_line(line):
            if line.startswith("@@P|"):
                _, per_mille, first, second = line.split("|", 3)
                root.after(0, lambda: (prog.first.configure(text=first), prog.second.configure(text=second),
                                       prog.bar.configure(value=int(per_mille))))
            else:
                lines.append(line)

        def work():
            try:
                code = install(plan, desktop_icon=desktop.get(), wizard_lines=on_line)
            except Exception as exc:
                lines.append(f"@@E|{exc}")
                code = 1
            root.after(0, lambda: finished(code, lines))

        threading.Thread(target=work, daemon=True).start()

    def finished(code, lines):
        result["code"] = code
        fin = pages[3]
        if code == 0:
            fin.title.configure(text="Installazione completata")
            warning = next((l[4:] for l in lines if l.startswith("@@W|")), "")
            fin.message.configure(text="Trovi «Neon Verbale» nel menu delle applicazioni. Da terminale: "
                                       f"{BIN}\n\nPer disinstallarlo: neon-verbale --disinstalla"
                                       + (f"\n\n{warning}" if warning else ""))
        else:
            error = next((l[4:] for l in lines if l.startswith("@@E|")), "errore sconosciuto")
            fin.title.configure(text="Installazione non riuscita")
            fin.message.configure(text=f"{error}\n\nDi solito dipende dalla connessione a Internet o da un proxy. "
                                       f"Dettagli in {APP_DIR / 'install.log'}.\nPer riprovare: "
                                       f"rilancia questo installer, oppure {BIN} --ripara")
            launch.set(False)
            fin.launch.configure(state="disabled")
            fin.guide.configure(state="disabled")
        show(3)

    back_btn.configure(command=lambda: show(0))
    next_btn.configure(command=go_next)
    show(0)
    if args.smoke_ui:  # CI: show every page except the installing one, then quit
        shots = os.environ.get("NEON_SMOKE_SHOTS")  # folder for screenshots of the virtual display

        def snap(name):
            if shots:
                root.update()
                subprocess.run(["import", "-window", "root", f"{shots}/{name}.png"], check=False)

        root.after(1500, lambda: (accepted.set(True), show(0), snap("wizard_1_licenza")))
        root.after(3000, lambda: (show(1), snap("wizard_2_riepilogo")))
        root.after(4500, lambda: (finished(0, []), snap("wizard_3_fine")))
        root.after(6000, root.destroy)
    root.mainloop()
    return result["code"]


# --- uninstalling ---------------------------------------------------------------------------

def uninstall(args) -> int:
    graphical = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and not args.cli

    def ask(question: str, default: bool) -> bool:
        if args.yes:
            return default
        if graphical:
            from tkinter import Tk, messagebox
            root = Tk()
            root.withdraw()
            answer = messagebox.askyesno("Neon Verbale", question)
            root.destroy()
            return answer
        reply = input(f"{question} [{'S/n' if default else 's/N'}] ").strip().lower()
        return default if not reply else reply in ("s", "si", "sì", "y", "yes")

    if not ask("Disinstallare Neon Verbale?", True):
        return 1
    remove_data = args.remove_data or (not args.yes and DATA_DIR.exists() and ask(
        f"Eliminare anche modelli scaricati, libreria delle voci e glossario?\n\n{DATA_DIR}\n\n"
        "Le trascrizioni accanto ai video restano dove sono.", False))
    desk = desktop_dir()
    for path in (BIN, DESKTOP_ENTRY, ICON, desk / "neon-verbale.desktop" if desk else None):
        if path and path.exists():
            path.unlink()
    shutil.rmtree(APP_DIR, ignore_errors=True)
    if remove_data:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run(["update-desktop-database", str(DESKTOP_ENTRY.parent)], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass
    print("Neon Verbale è stato rimosso." + ("" if remove_data else f" I dati restano in {DATA_DIR}."))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="NeonVerbale-linux-x86_64.run")
    p.add_argument("--payload", type=Path, default=HERE.parent, help=argparse.SUPPRESS)
    p.add_argument("--cli", action="store_true", help="installa da terminale, senza finestra")
    p.add_argument("-y", "--yes", action="store_true", help="non chiedere conferme")
    p.add_argument("--cpu", action="store_true", help="installa la versione per CPU anche se c'è una GPU NVIDIA")
    p.add_argument("--no-models", action="store_true", help="non scaricare ora il modello Whisper")
    p.add_argument("--no-desktop", action="store_true", help="niente collegamento sul desktop")
    p.add_argument("--uninstall", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--remove-data", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--smoke-ui", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.uninstall:
        return uninstall(args)
    plan = Plan(args.payload.resolve(), force_cpu=args.cpu, models=not args.no_models)
    graphical = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.cli or not graphical:
        return terminal(args, plan)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return terminal(args, plan)
    return wizard(args, plan)


if __name__ == "__main__":
    sys.exit(main())
