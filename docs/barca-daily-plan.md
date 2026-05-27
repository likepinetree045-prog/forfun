# 바르샤 데일리 인포 봇 — 기획서

## Context

매일 아침 FC Barcelona 정보(라 리가·챔스·코파 일정·결과, 라 리가 순위, 선수 소식)를 **한국어로 요약**해 본인 이메일로 받는 **개인용 도구**. Vercel에 배포.

**사용자 선택 정리**:
- 정보: 리그 순위 / 경기 일정·결과 / 선수 소식
- 대회: 라 리가 + UEFA 챔피언스리그 + 코파 델 레이
- 채널: 이메일
- 사용자 범위: 본인 혼자
- 요약: Claude로 자동 한국어 요약
- 리포트 구조: 매일 아침 일일 브리핑 + 경기 다음날 별도 결과 리포트

---

## 🎓 스포티파이 도구에서 살릴 교훈

1. **외부 API 정책 사전 검증** — 멜론(공식 API 없음), Spotify(2026 마이그레이션으로 endpoint 통째로 변경). 축구 API도 무료 티어 한도·인증 방식·정책 변경 가능성을 **개발 시작 전에 한 번 호출해보고** 확인.
2. **인증 단순화** — 본인용이라 OAuth/계정 시스템 X. API 키만 Vercel env vars에.
3. **무료 인프라 우선** — Vercel Hobby + 무료 티어 API + Resend.
4. **디버그 정보 처음부터** — 이메일 푸터에 빌드 SHA·fetch 시각 표시. 최근 N일치 raw 데이터를 KV에 보관. 수동 트리거 URL.
5. **빠른 반복** — Vercel preview deploy로 PR마다 별도 URL.
6. **시크릿은 절대 git에 X** — `.env.local` gitignore, Vercel env vars 사용.

---

## ⚙️ 기능

### 📬 A. 데일리 브리핑 (매일 KST 08:00)

이메일 1통:

- **🗓️ 향후 7일 경기**: 라 리가·챔스·코파 통합, 상대팀·일시(KST)·대회·홈/원정
- **🏆 라 리가 순위**: 바르샤 위치 + 1·2·3위 + 라이벌(레알/아틀레티코)과의 승점차
- **🌍 챔스 조별·KO 현황**: 바르샤가 속한 그룹/대진 상태
- **🥇 코파 토너먼트 진행**: 현재 라운드, 다음 상대 확정 시 표시
- **🧑‍⚕️ 선수 소식**: 부상자 명단, 출장 정지, 주요 이적·계약 뉴스
- **🇰🇷 Claude 요약**: 위 데이터를 4–5문장 한국어 헤더로

### ⚽ B. 경기 후 리포트 (경기 다음날 KST 10:00, 별도)

라 리가·챔스·코파 경기가 있었던 날의 다음날 아침에 별도 발송:

- **결과 헤드라인**: 스코어, 홈/원정, 대회
- **득점자·도움**: 시간순
- **주요 이벤트**: 퇴장·페널티·VAR·교체 핵심
- **선발 라인업**: 포메이션 + 11명
- **팀 통계**: 점유율·슈팅·xG·코너·파울
- **MVP·평점**: 매체별 평점 평균이 있으면 표시
- **Claude 요약**: 경기 흐름 한국어 5-6문장 평
- 경기가 없었던 날에는 **발송 안 함** (cron은 매일 돌지만 빈손이면 조용히 종료)

---

## 🔬 데이터 소스 검증 (개발 시작 전 필수)

| 항목 | 후보 | Quota | 인증 | 확인할 것 |
|---|---|---|---|---|
| 일정·순위·라인업·통계 | **API-Football** (api-sports.io) | 100 req/day 무료 | API 키 | 라 리가/챔스/코파 모두 한 번 호출 |
| | football-data.org | 10 req/min 무료 | API 키 | 백업 |
| 이적·뉴스 | **FCB 공식 RSS** | 무제한 | 없음 | RSS 파싱 + 한국어 처리 |
| | NewsAPI | 100 req/day | API 키 | RSS 부족 시 보조 |
| 한국어 요약 | **Claude API** (`claude-haiku-4-5`) | per token | API 키 | 프롬프트 캐싱으로 비용 최소화 |
| 이메일 | **Resend** | 100 email/day 무료 | API 키 | 도메인 없이 `onresend.com` 발신 가능 |

**Quota 예상**:
- 데일리 브리핑: 매일 4-5 req (일정/순위/챔스/코파/부상자)
- 포스트매치: 경기 있는 날만 3-4 req (결과/라인업/통계)
- 월 평균 ≈ 일 6 req × 30 = 180 req/월. 무료 한도 100 req/일 안에 충분.

**🚨 개발 시작 전 반드시 할 일**:
1. API-Football 가입 → 본인 키로 바르샤 팀 ID(`529`) 라 리가/챔스/코파 한 번씩 호출 → 응답 형식 직접 확인
2. FCB 공식 사이트 RSS URL 찾기, 파싱 테스트
3. Resend 가입 → 본인 이메일에 테스트 발송

---

## 🛠️ 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 프레임워크 | **Next.js 15 (App Router)** | Vercel 1순위 호환 |
| 호스팅 | **Vercel Hobby** | $0 |
| 스케줄링 | **Vercel Cron Jobs** | `vercel.json`에 cron 2개 |
| 데이터 페치 | API-Football + FCB RSS | TypeScript fetch |
| LLM | `@anthropic-ai/sdk`, `claude-haiku-4-5` | 프롬프트 캐싱 적용 |
| 이메일 | `resend` SDK + React Email | 깔끔한 템플릿 |
| 저장 | **Vercel KV** | 최근 14일치 raw + 요약 (디버그·롤백) |
| 시크릿 | Vercel env vars | `.env.local` gitignore |

**프롬프트 캐싱 핵심**: 시스템 프롬프트(요약 규칙) + 시즌 컨텍스트(팀 ID·선수 명단·과거 N경기 흐름)를 캐시 → 매일 변하는 raw 데이터만 새로 보냄 → 비용 80%+ 절감.

---

## 🏗️ 아키텍처

```
[Vercel Cron #1] 매일 UTC 23:00 (= KST 08:00)
       ↓ GET /api/daily
[/api/daily route]
       ├─→ API-Football  (라 리가 순위, 향후 7일 일정, 챔스/코파 현황, 부상자)
       ├─→ FCB RSS       (이적·뉴스)
       ↓
   raw JSON  ─→  Vercel KV (최근 14일)
       ↓
[Claude API]  4-5문장 한국어 헤더 (프롬프트 캐싱)
       ↓
[Resend]      본인 이메일로 발송


[Vercel Cron #2] 매일 UTC 01:00 (= KST 10:00)
       ↓ GET /api/post-match
[/api/post-match route]
       ├─ 어제 경기 있었는지 체크 (API-Football fixtures 어제 날짜 + 바르샤)
       │   ├─ 없으면 200 OK 반환 후 종료 (조용히)
       │   └─ 있으면 진행 ↓
       ├─→ API-Football  (결과·라인업·통계·이벤트)
       ↓
   raw JSON  ─→  Vercel KV
       ↓
[Claude API]  5-6문장 경기 리뷰
       ↓
[Resend]      본인 이메일로 발송
```

---

## 📁 디렉토리 구조

```
barca-daily/
├── app/
│   ├── api/
│   │   ├── daily/route.ts          # Cron #1 — 일일 브리핑
│   │   ├── post-match/route.ts     # Cron #2 — 경기 다음날 리포트
│   │   └── trigger/route.ts        # 수동 트리거 (CRON_SECRET 인증)
│   └── page.tsx                    # 최근 N일 리포트 웹 뷰 (옵션)
├── lib/
│   ├── football.ts                 # API-Football 클라이언트
│   ├── rss.ts                      # FCB RSS 파서
│   ├── claude.ts                   # 요약 (캐싱 적용)
│   ├── mailer.ts                   # Resend 래퍼
│   └── kv.ts                       # Vercel KV 헬퍼
├── emails/
│   ├── DailyBriefing.tsx           # React Email — 데일리
│   └── MatchRecap.tsx              # React Email — 경기 후
├── vercel.json                     # cron 2개 정의
├── .env.example
├── .env.local                      # git X (gitignore)
└── README.md
```

**`vercel.json`**:
```json
{
  "crons": [
    { "path": "/api/daily",      "schedule": "0 23 * * *" },
    { "path": "/api/post-match", "schedule": "0 1 * * *" }
  ]
}
```
- `0 23 * * *` (UTC) = 매일 KST 08:00
- `0 1 * * *`  (UTC) = 매일 KST 10:00

---

## 🔐 환경 변수 (`.env.local` + Vercel env vars)

```bash
APIFOOTBALL_KEY=...
ANTHROPIC_API_KEY=...
RESEND_API_KEY=...
RECIPIENT_EMAIL=eunsjani@corca.ai
CRON_SECRET=...              # 수동 트리거 인증용
KV_REST_API_URL=...          # Vercel KV
KV_REST_API_TOKEN=...
```

---

## 🐛 디버그·모니터링 (스포티파이 교훈)

- 이메일 본문 푸터에 **빌드 SHA + 데이터 fetch 시각 + 사용 모델 + 호출 시 cron**(daily/post-match) 작게 표시
- KV에 최근 14일치 raw + 요약 보관 → 문제 생기면 즉시 확인
- **수동 트리거**: `GET /api/trigger?type=daily&secret=<CRON_SECRET>` 또는 `?type=post-match` 로 cron 안 기다리고 테스트 가능
- **첫 1주**는 매일 직접 받아 데이터 정확도 확인 → 안정되면 잊고 받기만
- API 실패 시 fallback 메일 ("⚠️ API-Football 호출 실패: 응답 status 503") 발송 → 침묵 방지
- 포스트매치는 "경기 있었음 → 발송" / "경기 없었음 → KV에 '오늘은 경기 없음' 기록만"으로 cron 동작 가시화

---

## 🗓️ 로드맵 (총 ~1주)

| Day | 작업 |
|---|---|
| 1 | API-Football 가입, Postman/cURL로 바르샤 라 리가·챔스·코파 데이터 호출 검증 |
| 2 | Next.js 셋업, `/api/daily` 만들어 raw 데이터 콘솔 출력. Vercel 배포 + Cron #1 동작 확인 |
| 3 | Resend 연결, 단순 텍스트 이메일 발송 확인. 데일리 브리핑 React Email 템플릿 작성 |
| 4 | Claude 요약 추가, 프롬프트 다듬기, 캐싱 적용 |
| 5 | `/api/post-match` 구현 + Cron #2 등록. 경기 있는 날·없는 날 모두 테스트 |
| 6 | 경기 후 리포트 템플릿 + KV 저장 + 에러 알림 + 수동 트리거 라우트 |
| 7+ | 1주 자동 운영 + 정확도 모니터, 데이터 소스 보강 |

---

## 🚫 범위 밖 (v1 제외)

- 다른 사용자 가입/구독 시스템
- 실시간 알림 (경기 중 골)
- 웹 푸시
- 모바일 앱
- 한국어 외 언어
- 통계 시각화 차트
- 챗봇 인터페이스
- 라 리가 외 다른 팀 정보

---

## 💰 비용 추정

| 항목 | 월 비용 |
|---|---|
| Vercel Hobby | $0 |
| API-Football 무료 (월 ~180 req, 한도 일 100) | $0 |
| Claude API (haiku, daily 1회 + post-match 평균 12회/월, 캐싱 포함) | ~$0.2 |
| Resend (월 ~42통, 한도 일 100) | $0 |
| Vercel KV 무료 티어 | $0 |
| **합계** | **~$0.2/월** |

---

## ✅ 진행 전 결정 사항 (사용자)

1. [ ] API-Football 가입 + API 키 발급 → 한 번 호출 테스트
2. [ ] Resend 가입 + API 키 발급
3. [ ] Anthropic API 키 발급
4. [ ] GitHub에 새 리포 만들기 (`barca-daily` 추천)
5. [ ] Vercel 가입 + GitHub 연결

이 5개 준비되면 코드 작성 시작.

---

## 🤔 미결정 디테일

- **새 리포 vs `forfun` 합치기**: 도메인 다르므로 새 리포 추천
- **포스트매치 발송 시간 KST 10:00 OK?** (경기가 KST 05:00 끝나면 5시간 후. 더 빠르게 09:00도 가능)
- **데일리에 경기 결과 미니 섹션도 둘지?** (포스트매치 안 본 경우 대비) — 일단 안 두는 게 깔끔
- **이메일 발신 도메인**: 기본 `onresend.com` 그대로 vs 본인 도메인 인증
