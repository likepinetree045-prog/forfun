from __future__ import annotations

import os
from typing import Iterable, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .models import Track

SCOPE = " ".join(
    [
        "playlist-read-private",
        "playlist-modify-private",
        "playlist-modify-public",
        "user-library-read",
        "user-top-read",
    ]
)


def _build_client() -> spotipy.Spotify:
    auth = SpotifyOAuth(
        client_id=os.environ.get("SPOTIPY_CLIENT_ID"),
        client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.environ.get(
            "SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        ),
        scope=SCOPE,
        open_browser=True,
        cache_path=".cache-spotify",
    )
    return spotipy.Spotify(auth_manager=auth)


class SpotifyClient:
    def __init__(self, client: Optional[spotipy.Spotify] = None):
        self.sp = client or _build_client()

    def me(self) -> dict:
        return self.sp.current_user()

    def authenticate(self) -> dict:
        """OAuth 플로우를 강제 트리거하고 사용자 정보를 반환."""
        return self.me()

    def pull_liked(self, limit: Optional[int] = None) -> list[Track]:
        """내 '좋아요' 트랙을 모두 가져온다."""
        tracks: list[Track] = []
        offset = 0
        page_size = 50
        while True:
            page = self.sp.current_user_saved_tracks(limit=page_size, offset=offset)
            items = page.get("items", [])
            if not items:
                break
            for item in items:
                tr = item.get("track") or {}
                if not tr.get("id"):
                    continue
                tracks.append(
                    Track(
                        uri=tr["uri"],
                        name=tr.get("name", ""),
                        artists=[a["name"] for a in tr.get("artists", [])],
                        album=(tr.get("album") or {}).get("name", ""),
                        added_at=item.get("added_at", ""),
                    )
                )
                if limit and len(tracks) >= limit:
                    return tracks
            if len(items) < page_size:
                break
            offset += page_size
        return tracks

    def pull_playlists(self) -> list[dict]:
        """현재 사용자가 소유한 플레이리스트 메타 목록."""
        out: list[dict] = []
        offset = 0
        me_id = self.me()["id"]
        while True:
            page = self.sp.current_user_playlists(limit=50, offset=offset)
            items = page.get("items", [])
            if not items:
                break
            for pl in items:
                if pl.get("owner", {}).get("id") != me_id:
                    continue
                out.append(
                    {
                        "id": pl["id"],
                        "name": pl["name"],
                        "track_count": (pl.get("tracks") or {}).get("total", 0),
                    }
                )
            if len(items) < 50:
                break
            offset += 50
        return out

    def search_track(self, query: str, market: Optional[str] = "KR") -> Optional[Track]:
        """제목·아티스트 검색 → 첫 매치 반환."""
        result = self.sp.search(q=query, type="track", limit=1, market=market)
        items = (result.get("tracks") or {}).get("items", [])
        if not items:
            return None
        tr = items[0]
        return Track(
            uri=tr["uri"],
            name=tr.get("name", ""),
            artists=[a["name"] for a in tr.get("artists", [])],
            album=(tr.get("album") or {}).get("name", ""),
        )

    def create_playlist(
        self, name: str, track_uris: Iterable[str], description: str = "", public: bool = False
    ) -> dict:
        user_id = self.me()["id"]
        playlist = self.sp.user_playlist_create(
            user=user_id, name=name, public=public, description=description
        )
        uris = list(track_uris)
        for i in range(0, len(uris), 100):
            self.sp.playlist_add_items(playlist["id"], uris[i : i + 100])
        return playlist

    def replace_playlist_tracks(self, playlist_id: str, track_uris: Iterable[str]) -> None:
        uris = list(track_uris)
        if not uris:
            self.sp.playlist_replace_items(playlist_id, [])
            return
        self.sp.playlist_replace_items(playlist_id, uris[:100])
        for i in range(100, len(uris), 100):
            self.sp.playlist_add_items(playlist_id, uris[i : i + 100])
