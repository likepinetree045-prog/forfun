from __future__ import annotations

from playlist_builder.curator import dedupe_by_uri, filter_tracks, sort_for_playlist
from playlist_builder.models import Track


def _t(uri: str, **kw) -> Track:
    return Track(
        uri=uri,
        name=kw.get("name", "song"),
        artists=kw.get("artists", ["A"]),
        tags=kw.get("tags", []),
        rating=kw.get("rating"),
        added_at=kw.get("added_at", ""),
    )


def test_filter_match_all_tags() -> None:
    a = _t("1", tags=["여름", "드라이브"])
    b = _t("2", tags=["여름"])
    c = _t("3", tags=["새벽"])
    result = filter_tracks([a, b, c], tags=["여름", "드라이브"], match_all_tags=True)
    assert [t.uri for t in result] == ["1"]


def test_filter_any_tag() -> None:
    a = _t("1", tags=["여름"])
    b = _t("2", tags=["드라이브"])
    c = _t("3", tags=["새벽"])
    result = filter_tracks([a, b, c], tags=["여름", "드라이브"], match_all_tags=False)
    assert sorted(t.uri for t in result) == ["1", "2"]


def test_filter_min_rating_excludes_unrated() -> None:
    a = _t("1", rating=5)
    b = _t("2", rating=3)
    c = _t("3", rating=None)
    result = filter_tracks([a, b, c], min_rating=4)
    assert [t.uri for t in result] == ["1"]


def test_filter_exclude_artist_case_insensitive() -> None:
    a = _t("1", artists=["IU"])
    b = _t("2", artists=["aespa"])
    result = filter_tracks([a, b], exclude_artists=["IU"])
    assert [t.uri for t in result] == ["2"]


def test_dedupe_by_uri_preserves_order() -> None:
    a = _t("1")
    b = _t("2")
    a2 = _t("1", name="other")
    result = dedupe_by_uri([a, b, a2])
    assert [t.uri for t in result] == ["1", "2"]
    assert result[0].name == "song"  # 첫 항목 유지


def test_sort_for_playlist_high_rating_first() -> None:
    a = _t("1", rating=3)
    b = _t("2", rating=5)
    c = _t("3", rating=None)
    result = sort_for_playlist([a, b, c])
    assert [t.uri for t in result] == ["2", "1", "3"]
