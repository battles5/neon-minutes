"""Where the program and its data live.

Development checkout: everything next to the code. Installed copy (the installer writes
install.json next to the package): code in the install folder, per-user data (voice
library, ETA timings, glossary, settings, downloaded models) in %LOCALAPPDATA%\\Neon Verbale
on Windows and $XDG_DATA_HOME/neon-verbale (~/.local/share/neon-verbale) on Linux, which
updates and uninstalls leave alone.
"""

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Neon Verbale"
OLD_APP_NAME = "Trascrittore riunioni"  # name up to 1.1.0, Windows only
APP_DIR = Path(__file__).resolve().parent.parent
INSTALL_INFO = APP_DIR / "install.json"
INSTALLED = INSTALL_INFO.exists()


def user_data_dir() -> Path:
    """Per-user data folder of an installed copy (also used by the installers)."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "neon-verbale"


DATA_DIR = user_data_dir() if INSTALLED else APP_DIR
_OLD_DATA_DIR = DATA_DIR.parent / OLD_APP_NAME

if INSTALLED and sys.platform == "win32" and not DATA_DIR.exists() and _OLD_DATA_DIR.is_dir():
    # First start after the rename: keep voices, glossary, timings and downloaded models.
    try:
        _OLD_DATA_DIR.rename(DATA_DIR)
    except OSError:
        pass

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
