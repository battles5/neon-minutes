"""Where the program and its data live.

Development checkout: everything next to the code. Installed copy (the installer writes
install.json next to the package): code in the install folder, per-user data (voice
library, ETA timings, glossary, settings, downloaded models) in %LOCALAPPDATA%\\Neon Minutes
on Windows and $XDG_DATA_HOME/neon-minutes (~/.local/share/neon-minutes) on Linux, which
updates and uninstalls leave alone.
"""

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Neon Minutes"
# Earlier names of the data folder, newest first: "Neon Verbale" (1.2.0-1.4.0, Linux "neon-verbale"
# from 1.3.0) and "Trascrittore riunioni" (up to 1.1.0, Windows only).
OLD_DATA_NAMES = ("Neon Verbale", "Trascrittore riunioni") if sys.platform == "win32" else ("neon-verbale",)
APP_DIR = Path(__file__).resolve().parent.parent
INSTALL_INFO = APP_DIR / "install.json"
INSTALLED = INSTALL_INFO.exists()


def user_data_dir() -> Path:
    """Per-user data folder of an installed copy (also used by the installers)."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "neon-minutes"


DATA_DIR = user_data_dir() if INSTALLED else APP_DIR

if INSTALLED and not DATA_DIR.exists():
    # First start after a rename (or the installer's first import): keep voices, glossary, timings
    # and downloaded models.
    for _old in (DATA_DIR.parent / name for name in OLD_DATA_NAMES):
        if _old.is_dir():
            try:
                _old.rename(DATA_DIR)
            except OSError:
                pass
            break

MODELS_DIR = DATA_DIR / "modelli"
BUNDLED_PYANNOTE = APP_DIR / "models" / "pyannote-community-1"
GUIDE = APP_DIR / "docs" / "Guide.html"
ICON = APP_DIR / "assets" / "piuma.ico"
ICON_PNG = APP_DIR / "assets" / "piuma.png"

if INSTALLED:
    # Must be set before huggingface_hub is imported: it reads HF_HOME once.
    os.environ.setdefault("HF_HOME", str(MODELS_DIR))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def glossary_path() -> Path:
    """The user's glossary; an installed copy starts from the template shipped with it."""
    path = DATA_DIR / "glossary.txt"
    template = APP_DIR / "glossary.txt"
    if INSTALLED and not path.exists() and template.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, path)
    return path


def setup_environment() -> str | None:
    """Create the data folder, read .env from it and return the Hugging Face token, if any."""
    from dotenv import load_dotenv

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_dotenv(DATA_DIR / ".env")
    return os.environ.get("HF_TOKEN") or None
