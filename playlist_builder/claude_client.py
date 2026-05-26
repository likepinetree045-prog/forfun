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


@dataclass
class Recommendation:
    title: str
    artist: str
    reason: str

    def search_query(self) -> str:
        return f"track:{self.title} artist:{self.artist}"


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
