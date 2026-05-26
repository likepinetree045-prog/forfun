from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from anthropic import Anthropic

from .models import Track

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """너는 사용자가 좋아하는 곡 목록을 보고 비슷한 분위기·맥락의 곡을 추천하는 음악 큐레이터다.

규칙:
1. 시드 트랙의 아티스트·장르·태그·사용자 메모를 종합해 분위기를 파악한다.
2. 시드 트랙에 이미 있는 곡은 다시 추천하지 않는다.
3. 가능한 한 Spotify에서 검색 가능한 정확한 표기를 사용한다 (한글/영문 표기는 원곡 기준).
4. 출력은 반드시 JSON 배열만 반환한다. 다른 설명 텍스트는 출력하지 않는다.

출력 스키마:
[
  {"title": "곡 제목", "artist": "주 아티스트", "reason": "추천 이유 한 줄"}
]
"""


CLASSIFY_SYSTEM_PROMPT = """너는 사용자의 좋아요 트랙 목록을 받아서 적당한 수의 플레이리스트 카테고리로 분류하는 음악 큐레이터다.

규칙:
1. 입력은 인덱스가 붙은 트랙 리스트다. 각 트랙은 `{"i": 정수 인덱스, "title": ..., "artist": ...}` 형태.
2. 카테고리는 분위기·장르·맥락(시간대·계절·활동) 등 사용자가 실제로 플레이할 만한 단위로 묶는다.
3. 카테고리 이름은 한국어로 짧고 직관적이게 (예: "여름 드라이브", "새벽 인디", "운동 EDM").
4. 한 트랙은 가장 잘 어울리는 한 카테고리에만 배정한다. 모호하면 가장 강한 인상의 카테고리로 보낸다.
5. 너무 작은 카테고리(3곡 미만)는 만들지 않는다. 곡이 적으면 인접한 카테고리에 합친다.
6. 출력은 반드시 다음 JSON만 반환한다. 다른 텍스트는 출력하지 않는다.

출력 스키마:
{
  "categories": [
    {
      "name": "카테고리명",
      "description": "한 줄 설명 (어떤 분위기·맥락인지)",
      "track_indices": [0, 3, 7, ...]
    }
  ]
}
"""


@dataclass
class Recommendation:
    title: str
    artist: str
    reason: str

    def search_query(self) -> str:
        return f"track:{self.title} artist:{self.artist}"


@dataclass
class Category:
    name: str
    description: str
    track_uris: list[str]


class ClaudeClient:
    def __init__(self, model: str = DEFAULT_MODEL, client: Optional[Anthropic] = None):
        self.model = model
        self.client = client or Anthropic()

    def recommend(
        self,
        seeds: Iterable[Track],
        n: int = 10,
        mood: str = "",
    ) -> list[Recommendation]:
        seed_list = list(seeds)
        if not seed_list:
            raise ValueError("시드 트랙이 비어있습니다")

        seed_payload = [
            {
                "title": t.name,
                "artist": ", ".join(t.artists),
                "tags": t.tags,
                "rating": t.rating,
                "note": t.note,
            }
            for t in seed_list
        ]

        user_msg = (
            f"다음은 사용자가 좋아하는 시드 트랙들이다 (총 {len(seed_payload)}곡).\n"
            f"시드:\n{json.dumps(seed_payload, ensure_ascii=False, indent=2)}\n\n"
            f"분위기 힌트: {mood or '(없음)'}\n"
            f"위 시드들과 어울리는 곡 {n}개를 JSON 배열로 추천하라."
        )

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        return _parse_recommendations(text)

    def classify_tracks(
        self,
        tracks: list[Track],
        num_categories: Optional[int] = None,
        style_hint: str = "",
    ) -> list[Category]:
        if not tracks:
            raise ValueError("분류할 트랙이 비어있습니다")

        payload = [
            {"i": i, "title": t.name, "artist": ", ".join(t.artists)}
            for i, t in enumerate(tracks)
        ]

        if num_categories is None:
            cat_hint = "곡 수에 맞춰 5~8개"
        else:
            cat_hint = f"정확히 {num_categories}개"

        user_msg = (
            f"다음은 사용자의 좋아요 트랙 {len(tracks)}곡이다.\n"
            f"카테고리 개수 가이드: {cat_hint}.\n"
            f"분류 스타일 힌트: {style_hint or '(자유 — 분위기와 맥락 위주)'}\n\n"
            f"트랙:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "위 규칙대로 JSON으로만 응답하라."
        )

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": CLASSIFY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        return _parse_classification(text, tracks)


def _parse_recommendations(text: str) -> list[Recommendation]:
    """LLM 응답에서 JSON 배열을 추출해 Recommendation 리스트로 변환."""
    candidates = _extract_json_array(text)
    if candidates is None:
        raise ValueError(f"Claude 응답에서 JSON 배열을 찾지 못함: {text[:200]}")
    out: list[Recommendation] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "").strip()
        artist = item.get("artist", "").strip()
        if not title or not artist:
            continue
        out.append(
            Recommendation(
                title=title,
                artist=artist,
                reason=item.get("reason", "").strip(),
            )
        )
    return out


def _extract_json_array(text: str):
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # 코드펜스에 감싸 있을 수 있음
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    # 본문 중 첫 배열
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return None


def _parse_classification(text: str, tracks: list[Track]) -> list[Category]:
    """LLM 분류 응답 → Category 리스트. track_indices를 실제 URI로 매핑."""
    obj = _extract_json_object(text)
    if obj is None or "categories" not in obj:
        raise ValueError(f"Claude 응답에서 categories JSON을 찾지 못함: {text[:200]}")

    n = len(tracks)
    out: list[Category] = []
    seen_uris: set[str] = set()  # 한 곡은 한 카테고리에만

    for item in obj.get("categories", []):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        indices = item.get("track_indices") or []
        uris: list[str] = []
        for idx in indices:
            if not isinstance(idx, int) or idx < 0 or idx >= n:
                continue
            uri = tracks[idx].uri
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            uris.append(uri)
        if not uris:
            continue
        out.append(
            Category(
                name=name,
                description=(item.get("description") or "").strip(),
                track_uris=uris,
            )
        )
    return out


def _extract_json_object(text: str):
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None
