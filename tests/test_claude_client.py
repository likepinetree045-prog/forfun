from __future__ import annotations

import pytest

from playlist_builder.claude_client import _parse_recommendations


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
