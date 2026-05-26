from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import PlaylistRecord, Track

DEFAULT_LIBRARY_PATH = Path("data/library.json")


class Library:
    def __init__(self, path: Path = DEFAULT_LIBRARY_PATH):
        self.path = path
        self.tracks: dict[str, Track] = {}
        self.playlists: dict[str, PlaylistRecord] = {}

    def load(self) -> "Library":
        if not self.path.exists():
            return self
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.tracks = {
            uri: Track.from_dict(uri, td) for uri, td in data.get("tracks", {}).items()
        }
        self.playlists = {
            name: PlaylistRecord.from_dict(name, pd)
            for name, pd in data.get("playlists", {}).items()
        }
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tracks": {uri: t.to_dict() for uri, t in self.tracks.items()},
            "playlists": {n: p.to_dict() for n, p in self.playlists.items()},
        }
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)

    def upsert_track(self, track: Track) -> Track:
        existing = self.tracks.get(track.uri)
        if existing is None:
            self.tracks[track.uri] = track
            return track
        # 메타데이터는 새 값 우선, 사용자 큐레이션 데이터는 기존 값 보존
        existing.name = track.name or existing.name
        existing.artists = track.artists or existing.artists
        existing.album = track.album or existing.album
        if track.added_at and not existing.added_at:
            existing.added_at = track.added_at
        return existing

    def add_tags(self, uri: str, tags: Iterable[str]) -> Track:
        track = self.tracks[uri]
        track.tags = sorted(set(track.tags) | {t.strip() for t in tags if t.strip()})
        return track

    def remove_tag(self, uri: str, tag: str) -> Track:
        track = self.tracks[uri]
        track.tags = [t for t in track.tags if t != tag]
        return track

    def set_rating(self, uri: str, rating: Optional[int]) -> Track:
        track = self.tracks[uri]
        if rating is not None and not (0 <= rating <= 5):
            raise ValueError("rating은 0-5 사이여야 합니다")
        track.rating = rating
        return track

    def set_note(self, uri: str, note: str) -> Track:
        track = self.tracks[uri]
        track.note = note
        return track

    def upsert_playlist(self, record: PlaylistRecord) -> None:
        record.last_synced = datetime.now(timezone.utc).isoformat()
        self.playlists[record.name] = record

    def all_tags(self) -> list[str]:
        seen: set[str] = set()
        for t in self.tracks.values():
            seen.update(t.tags)
        return sorted(seen)
