"""Where the program and its data live.

Development checkout: everything next to the code. Installed copy (the installer writes
install.json next to the package): code in the install folder, per-user data (voice
library, ETA timings, glossary, settings, downloaded models) in
%LOCALAPPDATA%\\Trascrittore riunioni, which updates and uninstalls leave alone.
"""

import os
import shutil
from pathlib import Path

APP_NAME = "Trascrittore riunioni"
APP_DIR = Path(__file__).resolve().parent.parent
INSTALL_INFO = APP_DIR / "install.json"
INSTALLED = INSTALL_INFO.exists()
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME if INSTALLED else APP_DIR
MODELS_DIR = DATA_DIR / "modelli"
BUNDLED_PYANNOTE = APP_DIR / "models" / "pyannote-community-1"
GUIDE = APP_DIR / "docs" / "Guida.html"
ICON = APP_DIR / "assets" / "piuma.ico"

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
