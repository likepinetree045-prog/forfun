# playlist-builder (`pb`)

좋아하는 곡을 **태그·평점·메모로 큐레이션**하고, **Claude AI 추천**을 더해
**Spotify 플레이리스트로 만드는 CLI**.

> **왜 멜론이 아닌가**: 멜론은 공식 공개 API가 사실상 없습니다(Open API 종료, 외부 개발자 프로그램 없음).
> 비공식 스크래퍼는 약관 위반·불안정성·인증 불가 문제가 있어, 본 도구는 공식 OAuth가 있는 **Spotify Web API**를 채택했습니다.
> Spotify의 `recommendations`·`audio-features`도 2024년 11월부터 신규 앱에서 차단되어,
> 추천은 **Claude API(LLM)** 로 처리한 뒤 Spotify 검색으로 매칭하는 구조입니다.

---

## 빠른 시작

### 1. 의존성 설치

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. API 키 발급

| 서비스 | 발급 위치 | 필요한 이유 |
|---|---|---|
| Spotify | https://developer.spotify.com/dashboard | 라이브러리 조회, 플레이리스트 생성 |
| Anthropic | https://console.anthropic.com | Claude AI 추천 |

Spotify 앱 생성 시 **Redirect URI**를 다음으로 등록:
```
http://127.0.0.1:8888/callback
```

### 3. 환경변수 설정

```bash
cp .env.example .env
# 에디터로 .env 열어 키 입력
```

### 4. 로그인 & 라이브러리 가져오기

```bash
pb auth         # 브라우저에서 Spotify OAuth
pb pull         # 좋아요·내 플레이리스트를 로컬 캐시로
```

---

## 큐레이션 흐름

```
좋아요 가져오기 → 태그·평점 부여 → 기준대로 필터링 → (옵션) AI 추천 → Spotify에 플레이리스트 생성
   pb pull         pb tag            pb list           pb recommend       pb playlist create
```

### 태그 부여

```bash
# 곡 검색해서 태그 부여
pb tag "Blinding Lights" --tag 드라이브 --tag 신스팝 --rating 5

# 태깅 안 된 곡을 순회하며 입력 (대화형)
pb tag --interactive
```

### 필터링

```bash
pb list --tag 여름 --tag 드라이브 --min-rating 4
pb list --any-tag 인디 --any-tag 새벽
```

### AI 추천 미리보기

```bash
pb recommend --seed-tag 여름 -n 10 --mood "햇살, 창문 열고"
```

### Spotify에 플레이리스트 생성

```bash
# 내 라이브러리 + AI 추천 5곡을 합쳐 새 플리 생성
pb playlist create "여름 드라이브 2026" \
  --tag 여름 --tag 드라이브 \
  --min-rating 4 \
  --ai 5 \
  --mood "햇살, 창문 열고"

# 저장된 기준으로 기존 플리 동기화
pb playlist sync "여름 드라이브 2026"
```

---

## 데이터 모델

`data/library.json`에 모든 큐레이션 데이터가 보관됩니다 (gitignore됨).

```json
{
  "tracks": {
    "spotify:track:<id>": {
      "name": "Blinding Lights",
      "artists": ["The Weeknd"],
      "album": "After Hours",
      "added_at": "2026-04-01T12:00:00Z",
      "tags": ["드라이브", "신스팝"],
      "rating": 5,
      "note": "달릴 때"
    }
  },
  "playlists": {
    "여름 드라이브 2026": {
      "spotify_id": "...",
      "criteria": { "tags": ["여름"], "min_rating": 4, "ai_count": 5 },
      "last_synced": "..."
    }
  }
}
```

샘플 형식은 [`data/library.example.json`](data/library.example.json) 참조.

---

## 명령어 레퍼런스

| 명령 | 동작 |
|---|---|
| `pb auth` | Spotify OAuth 로그인 |
| `pb pull [--limit N]` | 좋아요·플레이리스트 메타 동기화 |
| `pb tag <query> [--tag X] [--rating N] [--note "..."]` | 곡에 태그/평점/메모 부여 |
| `pb tag --interactive` | 태깅 안 된 곡 순회하며 입력 |
| `pb list [--tag X] [--any-tag Y] [--min-rating N] [--limit N]` | 필터링 출력 |
| `pb recommend --seed-tag X [-n 10] [--mood "..."]` | Claude 추천 → Spotify 매칭 |
| `pb playlist create <name> --tag X [--ai N]` | 큐레이션해서 Spotify에 새 플리 생성 |
| `pb playlist sync <name>` | 저장된 기준으로 기존 플리 갱신 |

---

## 개발

```bash
pip install -e ".[dev]"
pytest
```

순수 로직(`library`, `curator`, `claude_client._parse_recommendations`)은 단위 테스트로 검증.
Spotify·Claude API 호출은 실제 키가 필요하므로 수동 검증 가이드만 제공.

### 검증 시나리오

1. `pb auth` → 브라우저 OAuth → `.cache-spotify` 생성 확인
2. `pb pull` → `data/library.json`에 좋아요 곡들이 채워지는지
3. `pb tag --interactive`로 5~10곡 태그 부여
4. `pb list --tag <태그>` → 부여한 곡이 출력되는지
5. `pb recommend --seed-tag <태그> -n 5` → Claude 응답 + Spotify 매칭 결과
6. `pb playlist create "테스트 플리" --tag <태그> --ai 3` → Spotify 앱에서 확인
7. `pb playlist sync "테스트 플리"` → 트랙 갱신

---

## 범위 밖 (v1 제외)

- 웹/모바일 UI
- 멜론·유튜브 등 타 서비스 동기화
- 다중 사용자 / 클라우드 동기화
- 자동 스케줄링
- Spotify가 차단한 `audio-features` 기반 정량 분석
