from __future__ import annotations

import json
from pathlib import Path

import pytest

from playlist_builder.library import Library
from playlist_builder.models import PlaylistRecord, Track


def _sample_track(uri: str = "spotify:track:abc", **overrides) -> Track:
    base = dict(
        uri=uri,
        name="Test Song",
        artists=["Artist A"],
        album="Album",
        added_at="2026-05-01T00:00:00Z",
    )
    base.update(overrides)
    return Track(**base)


def test_upsert_track_preserves_user_data(tmp_path: Path) -> None:
    lib = Library(path=tmp_path / "lib.json")
    original = _sample_track(tags=["여름"], rating=5, note="기존 메모")
    lib.upsert_track(original)

    # 새로 들어오는 데이터(메타데이터만 갱신)
    incoming = _sample_track(name="New Title", album="New Album")
    lib.upsert_track(incoming)

    stored = lib.tracks[original.uri]
    assert stored.name == "New Title"
    assert stored.album == "New Album"
    # 사용자 큐레이션 데이터는 보존됨
    assert stored.tags == ["여름"]
    assert stored.rating == 5
    assert stored.note == "기존 메모"


def test_add_tags_dedupe_and_sort(tmp_path: Path) -> None:
    lib = Library(path=tmp_path / "lib.json")
    track = _sample_track()
    lib.upsert_track(track)

    lib.add_tags(track.uri, ["여름", "드라이브"])
    lib.add_tags(track.uri, ["여름", "  ", "고에너지"])
    assert lib.tracks[track.uri].tags == sorted(["여름", "드라이브", "고에너지"])


def test_set_rating_validates_range(tmp_path: Path) -> None:
    lib = Library(path=tmp_path / "lib.json")
    track = _sample_track()
    lib.upsert_track(track)

    lib.set_rating(track.uri, 4)
    assert lib.tracks[track.uri].rating == 4

    with pytest.raises(ValueError):
        lib.set_rating(track.uri, 6)


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "lib.json"
    lib = Library(path=path)
    lib.upsert_track(_sample_track(tags=["여름"], rating=5))
    lib.upsert_playlist(
        PlaylistRecord(name="여름 플리", spotify_id="pl1", criteria={"tags": ["여름"]})
    )
    lib.save()

    # 파일 내용 검증
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "spotify:track:abc" in raw["tracks"]
    assert raw["playlists"]["여름 플리"]["spotify_id"] == "pl1"

    # 재로드
    lib2 = Library(path=path).load()
    assert lib2.tracks["spotify:track:abc"].rating == 5
    assert lib2.playlists["여름 플리"].criteria == {"tags": ["여름"]}
    assert lib2.playlists["여름 플리"].last_synced  # 채워져 있음


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    lib = Library(path=tmp_path / "does-not-exist.json").load()
    assert lib.tracks == {}
    assert lib.playlists == {}


def test_all_tags_sorted_unique(tmp_path: Path) -> None:
    lib = Library(path=tmp_path / "lib.json")
    lib.upsert_track(_sample_track(uri="spotify:track:1", tags=["여름", "드라이브"]))
    lib.upsert_track(_sample_track(uri="spotify:track:2", tags=["여름", "새벽"]))
    assert lib.all_tags() == ["드라이브", "새벽", "여름"]
