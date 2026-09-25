import os
from pathlib import Path

APP_ID = "io.postcast.Postcast"
APP_NAME = "Postcast"
APP_DISPLAY_NAME = "Postcast"
APP_VERSION = "0.1.5"
USER_AGENT = "Postcast/0.1.5 (postmarketOS; +https://github.com/jbriones)"

def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d

def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d

def db_path() -> Path:
    return data_dir() / "library.db"

def artwork_cache_dir() -> Path:
    d = cache_dir() / "artwork"
    d.mkdir(parents=True, exist_ok=True)
    return d

def default_download_dir() -> Path:
    base = os.environ.get("XDG_DOWNLOAD_DIR", str(Path.home()))
    d = Path(base) / "Podcasts"
    d.mkdir(parents=True, exist_ok=True)
    return d
