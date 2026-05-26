from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Track:
    uri: str
    name: str
    artists: list[str]
    album: str = ""
    added_at: str = ""
    tags: list[str] = field(default_factory=list)
    rating: Optional[int] = None
    note: str = ""

    @property
    def display(self) -> str:
        return f"{', '.join(self.artists)} — {self.name}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "artists": list(self.artists),
            "album": self.album,
            "added_at": self.added_at,
            "tags": sorted(set(self.tags)),
            "rating": self.rating,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, uri: str, data: dict) -> "Track":
        return cls(
            uri=uri,
            name=data.get("name", ""),
            artists=list(data.get("artists", [])),
            album=data.get("album", ""),
            added_at=data.get("added_at", ""),
            tags=list(data.get("tags", [])),
            rating=data.get("rating"),
            note=data.get("note", ""),
        )


@dataclass
class PlaylistRecord:
    name: str
    spotify_id: Optional[str] = None
    criteria: dict = field(default_factory=dict)
    last_synced: str = ""

    def to_dict(self) -> dict:
        return {
            "spotify_id": self.spotify_id,
            "criteria": self.criteria,
            "last_synced": self.last_synced,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "PlaylistRecord":
        return cls(
            name=name,
            spotify_id=data.get("spotify_id"),
            criteria=data.get("criteria", {}),
            last_synced=data.get("last_synced", ""),
        )
