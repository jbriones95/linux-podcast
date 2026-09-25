from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Podcast:
    id: Optional[int]
    feed_url: str
    title: str = ""
    author: str = ""
    description: str = ""
    image_url: str = ""
    link: str = ""
    episode_count: int = 0

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row["id"],
            feed_url=row["feed_url"],
            title=row["title"] or "",
            author=row["author"] or "",
            description=row["description"] or "",
            image_url=row["image_url"] or "",
            link=row["link"] or "",
        )


@dataclass
class Episode:
    id: Optional[int]
    podcast_id: int
    guid: str = ""
    title: str = ""
    description: str = ""
    audio_url: str = ""
    duration_seconds: int = 0
    published: Optional[int] = None
    downloaded_path: str = ""
    played: bool = False
    favorite: bool = False
    position_seconds: int = 0

    @property
    def is_downloaded(self) -> bool:
        return bool(self.downloaded_path)

    def playable_uri(self) -> str:
        from pathlib import Path
        if self.downloaded_path and Path(self.downloaded_path).exists():
            return Path(self.downloaded_path).as_uri()
        return self.audio_url

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row["id"],
            podcast_id=row["podcast_id"],
            guid=row["guid"] or "",
            title=row["title"] or "",
            description=row["description"] or "",
            audio_url=row["audio_url"] or "",
            duration_seconds=row["duration_seconds"] or 0,
            published=row["published"],
            downloaded_path=row["downloaded_path"] or "",
            played=bool(row["played"]),
            favorite=bool(row["favorite"]),
            position_seconds=row["position_seconds"] or 0,
        )
