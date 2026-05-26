from __future__ import annotations

import pytest

from playlist_builder.claude_client import _parse_classification, _parse_recommendations
from playlist_builder.models import Track


def test_parse_raw_json_array() -> None:
    text = '[{"title": "Blue", "artist": "박효신", "reason": "차분"}]'
    recs = _parse_recommendations(text)
    assert len(recs) == 1
    assert recs[0].title == "Blue"
    assert recs[0].artist == "박효신"


def test_parse_with_code_fence() -> None:
    text = """여기 추천이야:
```json
[
  {"title": "Spring Day", "artist": "BTS", "reason": "그리움"},
  {"title": "Through the Night", "artist": "IU", "reason": "잔잔"}
]
```
"""
    recs = _parse_recommendations(text)
    assert len(recs) == 2
    assert recs[1].artist == "IU"


def test_parse_embedded_array_in_prose() -> None:
    text = '추천: [{"title":"x","artist":"y","reason":"z"}] 끝.'
    recs = _parse_recommendations(text)
    assert recs[0].title == "x"


def test_parse_skips_invalid_entries() -> None:
    text = '[{"title":"ok","artist":"a","reason":""},{"title":"","artist":"b"},{"foo":"bar"}]'
    recs = _parse_recommendations(text)
    assert len(recs) == 1
    assert recs[0].title == "ok"


def test_parse_raises_when_no_json_array() -> None:
    with pytest.raises(ValueError):
        _parse_recommendations("미안, 추천을 못 했어")


def _track(i: int) -> Track:
    return Track(uri=f"spotify:track:{i}", name=f"song{i}", artists=[f"artist{i}"])


def test_parse_classification_normal() -> None:
    tracks = [_track(i) for i in range(5)]
    text = """{
      "categories": [
        {"name": "여름", "description": "햇살", "track_indices": [0, 1, 2]},
        {"name": "새벽", "description": "잔잔", "track_indices": [3, 4]}
      ]
    }"""
    cats = _parse_classification(text, tracks)
    assert len(cats) == 2
    assert cats[0].name == "여름"
    assert cats[0].track_uris == ["spotify:track:0", "spotify:track:1", "spotify:track:2"]
    assert cats[1].track_uris == ["spotify:track:3", "spotify:track:4"]


def test_parse_classification_skips_out_of_range_and_dupes() -> None:
    tracks = [_track(i) for i in range(3)]
    text = """{
      "categories": [
        {"name": "A", "description": "", "track_indices": [0, 1, 99, -1, 1]},
        {"name": "B", "description": "", "track_indices": [1, 2]}
      ]
    }"""
    cats = _parse_classification(text, tracks)
    # 99/-1은 범위 밖, 1 중복 → A는 [0,1], B는 1 이미 사용됐으므로 [2]
    assert cats[0].track_uris == ["spotify:track:0", "spotify:track:1"]
    assert cats[1].track_uris == ["spotify:track:2"]


def test_parse_classification_drops_empty_category() -> None:
    tracks = [_track(i) for i in range(2)]
    text = """{
      "categories": [
        {"name": "비어있음", "description": "", "track_indices": []},
        {"name": "정상", "description": "", "track_indices": [0, 1]}
      ]
    }"""
    cats = _parse_classification(text, tracks)
    assert len(cats) == 1
    assert cats[0].name == "정상"


def test_parse_classification_with_code_fence() -> None:
    tracks = [_track(0)]
    text = """좋아, 분류했어:
```json
{"categories": [{"name": "단일", "description": "", "track_indices": [0]}]}
```
"""
    cats = _parse_classification(text, tracks)
    assert cats[0].track_uris == ["spotify:track:0"]


def test_parse_classification_raises_on_missing_categories() -> None:
    with pytest.raises(ValueError):
        _parse_classification("{}", [_track(0)])
