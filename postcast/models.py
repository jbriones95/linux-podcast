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
    language: str = ""
    categories: str = ""
    explicit: bool = False
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
            language=row["language"] or "",
            categories=row["categories"] or "",
            explicit=bool(row["explicit"]),
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
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    explicit: bool = False

    @property
    def is_downloaded(self) -> bool:
        from pathlib import Path
        return bool(self.downloaded_path and Path(self.downloaded_path).is_file())

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
            season_number=row["season_number"],
            episode_number=row["episode_number"],
            explicit=bool(row["explicit"]),
        )
