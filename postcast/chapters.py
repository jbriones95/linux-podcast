from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Chapter:
    title: str
    start_seconds: float
    end_seconds: Optional[float] = None


def parse_extended_comments(values):
    """Parse CHAPTER001/CHAPTER001NAME comment pairs into ordered chapters."""
    starts = {}
    names = {}
    for value in values or ():
        key, separator, raw = str(value).partition("=")
        if not separator:
            continue
        key = key.strip().upper()
        raw = raw.strip()
        if key.startswith("CHAPTER") and key.endswith("NAME"):
            names[key[7:-4]] = raw
        elif key.startswith("CHAPTER"):
            try:
                starts[key[7:]] = _timestamp(raw)
            except ValueError:
                continue

    ordered = sorted((start, index) for index, start in starts.items())
    chapters = []
    for position, (start, index) in enumerate(ordered):
        if chapters and start <= chapters[-1].start_seconds:
            continue
        end = ordered[position + 1][0] if position + 1 < len(ordered) else None
        chapters.append(Chapter(names.get(index, f"Chapter {len(chapters) + 1}"), start, end))
    return chapters


def active_chapter(chapters, position):
    current = None
    for chapter in chapters or ():
        if position >= chapter.start_seconds:
            current = chapter
        else:
            break
    return current


def _timestamp(value):
    parts = value.strip().split(":")
    if len(parts) == 1:
        seconds = float(parts[0])
    elif len(parts) == 2:
        seconds = int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError("invalid chapter timestamp")
    if seconds < 0:
        raise ValueError("negative chapter timestamp")
    return seconds
