import json
import time
from pathlib import Path


def export_library(db, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"exported_at": int(time.time()), "library": db.export_sync_state()}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def import_library(db, path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    state = payload.get("library", payload)
    return db.import_sync_state(state)
