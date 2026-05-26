from __future__ import annotations

from typing import Iterable, Optional

from .models import Track


def filter_tracks(
    tracks: Iterable[Track],
    tags: Optional[Iterable[str]] = None,
    min_rating: Optional[int] = None,
    exclude_artists: Optional[Iterable[str]] = None,
    match_all_tags: bool = True,
) -> list[Track]:
    """태그·평점·아티스트 제외 기준으로 트랙을 필터링한다.

    match_all_tags=True면 지정 태그 전부를 가진 트랙만 통과(AND),
    False면 하나라도 가진 트랙 통과(OR).
    """
    tag_set = {t for t in (tags or []) if t}
    excluded = {a.lower() for a in (exclude_artists or [])}

    def keep(t: Track) -> bool:
        if tag_set:
            owned = set(t.tags)
            if match_all_tags:
                if not tag_set.issubset(owned):
                    return False
            else:
                if owned.isdisjoint(tag_set):
                    return False
        if min_rating is not None:
            if t.rating is None or t.rating < min_rating:
                return False
        if excluded:
            if any(a.lower() in excluded for a in t.artists):
                return False
        return True

    return [t for t in tracks if keep(t)]


def dedupe_by_uri(tracks: Iterable[Track]) -> list[Track]:
    seen: set[str] = set()
    out: list[Track] = []
    for t in tracks:
        if t.uri in seen:
            continue
        seen.add(t.uri)
        out.append(t)
    return out


def sort_for_playlist(tracks: Iterable[Track]) -> list[Track]:
    """평점 높은 곡을 앞에, 동률은 최근 추가 순."""
    return sorted(
        tracks,
        key=lambda t: (-(t.rating or 0), t.added_at or ""),
        reverse=False,
    )
