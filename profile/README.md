# OrgWiki

> **Compile your team's tribal knowledge into agent-readable context.**
>
> GitHub Organization 단위로 흩어진 암묵지를 자동 컴파일하여, 코딩 에이전트가 작업 직전에 정확한 만큼만 끌어다 쓰는 팀 컨텍스트 허브.

---

## 0. TL;DR

- **누가 쓰는가**: Claude Code, Codex, cmux 등 코딩 에이전트를 일상적으로 쓰는 팀.
- **무엇을 푸는가**: 에이전트가 매 세션마다 코드베이스를 처음부터 다시 학습하면서 토큰을 태우고, 코드에 안 적힌 암묵지(deprecated, ADR, 도메인 용어, 레포 간 의존)를 모르고 잘못된 코드를 짠다.
- **어떻게 푸는가**: GitHub Org에 wiki 전용 repo를 한 개 만들고, 다른 모든 repo의 `main` 브랜치 변경을 webhook으로 받아 인크리멘털하게 wiki를 갱신한다. 팀원의 에이전트는 **CLI + SKILL.md** 조합으로 wiki에서 필요한 페이지를 끌어 쓴다.
- **왜 CLI인가**: 행사 트랙이 명시한 "CLI 기반 개발자 도구" 정의에 정확히 부합. bash 실행 가능한 모든 에이전트(Claude Code, Codex, cmux, Cline, Aider 등)에서 동작. SKILL.md로 호출을 결정론적으로 강제 가능.
- **왜 지금**: Claude Code, Codex, cmux 같은 에이전트 코딩 환경이 표준이 되면서, "에이전트가 무엇을 보느냐"가 결과물 품질을 지배하게 됐다. 컨텍스트가 1급 시민이 된 시대.
- **트랙**: CMUX × AIM Hackathon — Developer Tooling.

---

## 1. 문제 정의 (Why)

### 1.1 코딩 에이전트가 매일 잃는 토큰과 시간

Claude Code / Codex를 한 달 이상 진지하게 써본 사람이라면 다음 시나리오를 일주일에 여러 번 겪는다:

- **재발견 비용**: 같은 모노레포에서 새 세션을 열 때마다 에이전트가 `find`, `grep`, `read`로 동일한 파일들을 다시 탐색한다. 어제 배운 "이 라이브러리는 deprecated"를 오늘 모른다.
- **암묵지 누락**: 코드에 없는 정보가 결정에 영향을 준다. "왜 이 모듈은 V2 SDK를 안 쓰지?" → Slack 어딘가의 결정. 에이전트는 모름. 그래서 deprecated된 V1 SDK로 새 코드를 짠다.
- **레포 간 단절**: 한 레포의 변경이 다른 레포에 미치는 영향을 에이전트가 알 길이 없다. `core-types`의 `User` 인터페이스가 바뀌어도 `auth-service`에서 작업하는 에이전트는 모른다.
- **신입의 페인 = 에이전트의 페인**: 신입이 묻는 질문 = 에이전트가 모르는 것. 둘 다 같은 곳에서 막히고, 둘 다 매번 같은 답을 찾아 헤맨다.

### 1.2 기존 솔루션이 부족한 이유

| 솔루션 | 한계 |
|---|---|
| 잘 쓴 README | 정적이고 사람이 직접 유지해야 함. 결국 stale. |
| `CLAUDE.md` / `AGENTS.md` | 단일 레포 단위. 멀티 레포에서는 정보 분산. |
| Greptile, Sourcegraph Cody | *코드 자체*를 검색해줌. 코드에 없는 결정·관습·암묵지는 못 줌. |
| Devin DeepWiki | 자동 wiki 생성. 단일 레포 + 사람이 읽는 용도. 에이전트 소비 최적화 아님. |
| RAG 챗봇 | 매 쿼리마다 raw chunk를 다시 합성. 누적되는 시너지 없음. |
| Slack/Notion 검색 | 신호 대 잡음 비 낮음. 컨텍스트 단편적. |

### 1.3 인사이트: 컨텍스트는 컴파일되어야 한다

Karpathy의 *llm-wiki* 패턴이 던지는 핵심 통찰:

> **The wiki is a persistent, compounding artifact. Knowledge is compiled once and then kept current, not re-derived on every query.**

이 통찰을 *개인 KB*가 아니라 *팀 코드베이스*에 적용하면 — 그게 OrgWiki다.

---

## 2. 솔루션 컨셉 (What)

### 2.1 한 문장 정의

**OrgWiki는 GitHub Organization의 모든 main 브랜치 변경을 자동으로 흡수해, 코딩 에이전트가 CLI 한 번으로 끌어다 쓰는 팀 컨텍스트 허브를 git repo로 유지하는 시스템이다.**

### 2.2 형태

- 팀은 평소처럼 GitHub Org에 repo들을 운영한다 (변경 없음).
- Org 안에 `wiki`라는 새 repo를 하나 만든다.
- 다른 repo들의 `main`에 push가 일어나면 OrgWiki 서버가 webhook을 받는다.
- 서버가 변경 영향 범위를 분석하고, 영향받는 wiki 페이지만 갱신해서 wiki repo에 commit/PR한다.
- 팀원의 Claude Code / Codex / cmux는 작업 시작 시 **SKILL.md**의 정책에 따라 자동으로 `orgwiki` CLI를 호출해 관련 페이지를 끌어온다. 사람도 같은 CLI로 직접 질의 가능.

### 2.3 핵심 설계 원칙

1. **Git이 진실이다**. wiki도 git repo. 모든 변경에 author/timestamp/diff가 자동 기록됨.
2. **Incremental over total**. 전체 재생성은 토큰 폭탄. 변경된 파일이 영향을 주는 페이지만 갱신.
3. **에이전트는 의미만, 코드는 기계적인 일을**. 인덱스 갱신, 링크 정합성, 영향도 계산은 결정론적 코드. 에이전트는 글 쓰는 일만.
4. **Provenance가 1급 시민**. 모든 wiki 페이지는 출처 file path + commit SHA + line range를 인용한다. stale 자동 감지를 위해서도 필수.
5. **사람이 마지막 게이트**. 자동 머지는 확신도 높은 변경에만. 나머지는 PR로 올림. wiki는 LLM의 자유 작문 공간이 아니라 검토 가능한 문서다.
6. **에이전트 소비 우선**. 사람이 보기 좋은 것보다 에이전트가 정확히 인용하기 좋게. 메타데이터·링크·구조화 우선.
7. **CLI는 보편 인터페이스**. 어떤 에이전트든 `bash`를 실행할 수 있으면 OrgWiki를 쓸 수 있다. MCP, IDE 플러그인, 브라우저 확장 같은 환경 종속을 만들지 않는다.

---

## 3. Karpathy llm-wiki와의 관계 및 차별화

OrgWiki는 Karpathy 패턴의 *팀 + 코드베이스 + 에이전트* 변형이다.

| | Karpathy llm-wiki | OrgWiki |
|---|---|---|
| 1차 소비자 | 사람 (Obsidian) | 코딩 에이전트 (CLI 경유) |
| 단위 | 개인 | 팀 / 조직 |
| 소스 | 사람이 큐레이션한 자료 | Org 내 모든 repo의 `main` |
| 트리거 | 사람이 ingest 명령 | git push (webhook) |
| 출력 | 마크다운 (읽기용) | 마크다운 + 구조화 메타 (검색·인용용) |
| 검증 | 사람이 신뢰 | provenance + stale 감지 + PR 리뷰 |
| 페인 | "RAG가 매번 재발견" | "에이전트가 매 세션 재학습 + 암묵지 모름" |

기존 비슷한 시도와의 차별:

- **eliavamar의 `repositories-wiki`**: 단일 레포 + 사람이 읽는 wiki. OrgWiki는 멀티 레포 + 레포 간 관계가 1급 + 에이전트 소비 최적화 + push-driven 자동 sync.
- **Devin DeepWiki**: 자동 wiki 생성에서 가장 가까운 제품. 차이는 (1) Org 단위, (2) 에이전트 소비, (3) push-driven incremental, (4) 결과가 git repo로 외화되어 audit/검열 가능.
- **`llms.txt`**: 정적 단일 파일을 사람이 작성. OrgWiki는 동적 다파일을 에이전트가 유지.

---

## 4. 아키텍처

### 4.1 3-Layer 모델

```
┌──────────────────────────────────────────────────────────┐
│  Layer 1: Source-of-Truth (변경 없음)                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│  │ org/repo-A │  │ org/repo-B │  │ org/repo-C │  ...     │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘          │
│        │ webhook       │               │                 │
│        └───────────────┴───────────────┘                 │
│                       ▼                                  │
├──────────────────────────────────────────────────────────┤
│  Layer 2: OrgWiki Maintainer (서버)                      │
│   ┌────────────────────────────────────────────────────┐ │
│   │ 1. diff 수신 → 변경 파일 목록 추출                 │ │
│   │ 2. 영향도 분석 (역인덱스: file → page)             │ │
│   │ 3. 영향받는 페이지마다 작은 컨텍스트로 에이전트    │ │
│   │ 4. 갱신 결과를 wiki repo에 commit/PR               │ │
│   │ 5. 인덱스/로그/링크 정합성 자동 갱신 (코드)        │ │
│   └────────────────────────────────────────────────────┘ │
│                       ▼                                  │
├──────────────────────────────────────────────────────────┤
│  Layer 3: Wiki Repo (org/wiki, git repo)                 │
│   ├── CLAUDE.md          (스키마)                        │
│   ├── index.md           (카탈로그)                      │
│   ├── log.md             (append-only 변경 이력)         │
│   ├── repos/             (레포별 페이지)                 │
│   ├── concepts/          (레포 가로지르는 개념)          │
│   ├── decisions/         (ADR)                           │
│   └── glossary.md        (사내 용어)                     │
└──────────────────────────────────────────────────────────┘
                          ▲
                          │  HTTPS API
                          │
                  ┌───────┴────────┐
                  │  orgwiki CLI   │
                  └───────┬────────┘
                          ▲
                          │  bash 호출
              ┌───────────┴───────────┐
              │      SKILL.md         │  (정책 강제)
              └───────────┬───────────┘
                          ▲
              Claude Code / Codex / cmux
              (팀원 로컬 작업)
```

### 4.2 컴포넌트 책임

**Wiki Maintainer 서버** (Cloudflare Worker / Fly.io)
- GitHub App으로 등록. webhook 수신.
- Job queue로 ingest 작업 비동기 처리.
- 에이전트 호출: Claude Sonnet (글쓰기), Gemini Flash (영향도 분석) — 해커톤 크레딧 활용.
- wiki repo에 PR 작성. 자동 머지 정책 + 사람 리뷰 정책.
- 동시에 **CLI를 위한 read API**를 노출 (`GET /search`, `GET /pages/:path`, `GET /related`).

**Wiki Repo** (org/wiki)
- 단순 git repo. 어떤 인프라도 강제하지 않음.
- 검색은 별도 인덱스 서비스가 담당 (BM25 + 벡터). 인덱스가 없어도 grep으로 동작.

**클라이언트 측 — CLI + SKILL.md만**
- **`orgwiki` CLI**: 에이전트와 사람이 동일하게 쓰는 단일 인터페이스. 환경 종속 없음.
- **SKILL.md**: 에이전트가 작업 시작 시 자동 로드. CLI를 *언제·어떻게* 호출할지 결정론적으로 강제하는 정책 문서.

### 4.3 왜 CLI + SKILL만인가 (다른 채널을 의도적으로 잘랐다)

| 옵션 | 평가 | 결정 |
|---|---|---|
| **CLI + SKILL** | 보편 호환, 결정론적 호출, 데모 시각화 강함, 9시간 안에 완성 가능 | **채택** |
| MCP server | Claude Code 외 호환성 제한, 무대 시각화 약함, 등록·디버깅 위험 | Phase 2로 미룸 |
| IDE 플러그인 | 환경별 분기, "터미널만으로" 트랙 정의에 역행 | 안 함 |
| 웹 대시보드 | 트랙 정의에 부합 안 함, 9시간 안에 임팩트 못 냄 | 안 함 |

**결정 근거**: 행사 모토 *"IDE 없이, 터미널과 AI 코딩 에이전트만으로"* + cmux 미학 + bash가 모든 에이전트의 공통 분모. CLI 하나로 모든 에이전트를 커버하는 게 최대 가치.

---

## 5. Wiki Repo의 구조

### 5.1 디렉터리 레이아웃

```
org-wiki/
├── CLAUDE.md                           # 스키마: wiki를 어떻게 쓰고 유지하는지
├── README.md                           # 사람용 입문서
├── index.md                            # 전체 카탈로그
├── log.md                              # append-only 변경 이력
│
├── repos/                              # 레포별 페이지
│   ├── auth-service/
│   │   ├── overview.md                 # 무엇을 하는 서비스인가
│   │   ├── architecture.md             # 모듈/레이어 구조
│   │   ├── api.md                      # 외부 API 표면
│   │   ├── conventions.md              # 코드 스타일/네이밍 규약
│   │   ├── gotchas.md                  # 함정·deprecated·이상한 결정
│   │   └── dependencies.md             # 다른 repo와의 의존
│   ├── core-types/
│   └── billing-service/
│
├── concepts/                           # 레포 가로지르는 개념
│   ├── authentication-flow.md          # 여러 repo가 엮인 흐름
│   ├── billing-domain-model.md
│   └── tenant-isolation-model.md
│
├── decisions/                          # ADR (Architecture Decision Records)
│   ├── 2026-03-15-pgvector-migration.md
│   ├── 2026-04-02-payment-v2-migration.md
│   └── 2026-04-20-deprecate-graphql-gateway.md
│
├── glossary.md                         # 사내 용어집
└── meta/                               # 시스템 자체의 메타데이터
    ├── file-page-index.json            # 역인덱스: file → pages
    ├── stale.md                        # 갱신 필요 페이지 목록
    └── orphans.md                      # 어디서도 링크되지 않는 페이지
```

### 5.2 페이지 형식 (예시: `repos/auth-service/gotchas.md`)

```markdown
---
repo: auth-service
last_synced_at: 2026-04-26T08:14:22Z
last_synced_commit: a3f12b3c
sources:
  - path: src/handlers/login.ts
    range: L45-L120
    sha: a3f12b3c
  - path: src/middleware/session.ts
    range: L1-L80
    sha: a3f12b3c
confidence: high
---

# auth-service · Gotchas

## V1 Payment SDK는 deprecated

**근거**: [decisions/2026-04-02-payment-v2-migration.md](../../decisions/2026-04-02-payment-v2-migration.md)

`src/handlers/login.ts`의 결제 연동 코드는 V1 SDK를 호출하지만,
V2 마이그레이션이 진행 중이다. **새 코드는 V2 어댑터를 사용해야 한다**.

V1 함수: `chargeUser()` ← 신규 사용 금지
V2 함수: `payments.v2.charge()` ← 사용

> 출처: src/handlers/login.ts#L45-L78 (commit a3f12b3c)
> 관련: decisions/2026-04-02

## 세션 만료는 Redis TTL이 아니라 JWT exp가 진실

(...)
```

**페이지 설계의 핵심**:
- frontmatter로 메타데이터 (소스, 신뢰도, 최종 동기화 시점)
- 본문에는 항상 출처 인용 (file + line + commit SHA)
- 다른 페이지로의 링크는 절대 경로 + 명확한 의도

### 5.3 `CLAUDE.md` 스키마 초안 (wiki repo 안)

```markdown
# OrgWiki Schema

## Layers
1. Raw sources: org's repositories. Read-only. Never modify.
2. This wiki: maintained by OrgWiki agent + team.
3. Schema: this file.

## Page types and rules
- repos/<n>/overview.md — high-level summary, max 500 words
- repos/<n>/gotchas.md — known traps, deprecations, weird decisions. Each item must cite source.
- decisions/YYYY-MM-DD-*.md — ADR. Append-only. Never edit past decisions; supersede with new ones.
- concepts/*.md — cross-repo concepts. Must link to repo pages.

## Citation requirement
Every factual claim must cite either:
  (a) source code: `src: <repo>@<sha>:<path>#L<start>-L<end>`
  (b) another wiki page (relative link)
  (c) external URL (use sparingly)

If you cannot cite, do not write the claim. Mark as `[NEEDS HUMAN INPUT]` instead.

## When to create vs update vs supersede
- New file in source: consider creating a page only if it introduces a new concept worth documenting.
- Modified file: update existing pages whose `sources` reference that file.
- Deleted file: mark dependent pages as `[STALE]`, do not auto-delete.

## Banned behaviors
- Do not summarize code that already self-documents.
- Do not invent rationale for decisions you cannot find evidence for.
- Do not consolidate contradicting sources without flagging.
```

---

## 6. Sync 메커니즘 — Incremental Ingest

### 6.1 흐름

```
push to org/repo-A:main
    │
    ▼
GitHub webhook → OrgWiki server
    │
    ▼
[1] 변경 파일 목록 추출 (git diff)
    │
    ▼
[2] 역인덱스 조회 (meta/file-page-index.json)
    "src/handlers/login.ts" → [
        "repos/auth-service/api.md",
        "repos/auth-service/gotchas.md",
        "concepts/authentication-flow.md"
    ]
    │
    ▼
[3] 영향받는 각 페이지마다:
    ├─ 현재 페이지 본문 + 변경된 source 코드 → 작은 컨텍스트
    ├─ 에이전트에게 "이 변경이 이 페이지에 어떤 영향을 주는가?" 질의
    └─ 갱신 패치 생성 (또는 "변경 없음" 결정)
    │
    ▼
[4] 인덱스/로그 갱신 (코드, LLM 아님)
    ├─ index.md 카탈로그 업데이트
    ├─ log.md에 entry 추가
    └─ meta/file-page-index.json 갱신
    │
    ▼
[5] wiki repo에 PR 생성 (또는 자동 머지)
    ├─ 작은 변경 + 신뢰도 high → 자동 머지
    └─ 그 외 → 사람 리뷰
```

### 6.2 영향도 분석의 깊이

세 단계로 영향 범위를 점진적으로 확장:

1. **직접 영향**: 역인덱스에 등록된 페이지.
2. **링크 영향**: 직접 영향 페이지를 링크하는 다른 페이지 (cross-ref 무결성).
3. **개념 영향**: 변경 파일이 속한 디렉터리/모듈에 매핑된 concepts/* 페이지.

해커톤 MVP는 1단계만 구현. 2-3단계는 lint pass에서 잡음.

### 6.3 대용량 변경 / 첫 ingest 처리

- **첫 등록 시**: 전체 인덱싱은 작은 repo만. 큰 repo는 디렉터리 단위로 chunk 처리. 사람이 우선순위 지정 가능.
- **massive PR (수백 파일)**: 자동 ingest 안 함. 알림만. 사람이 트리거.

### 6.4 토큰 예산

페이지 갱신 1회당 입력 ~5K 토큰, 출력 ~1K 토큰을 상한으로 잡음. 평균 push 1회당 1-3페이지 갱신 예상. Claude Sonnet 기준 push당 $0.05~0.15. Org 단위 연 사용량 관리 가능 수준.

---

## 7. 클라이언트 인터페이스 — CLI + SKILL.md

OrgWiki의 클라이언트 측은 **두 개의 파일로 끝난다**: `orgwiki` 바이너리 하나, `SKILL.md` 한 장. 어떤 에이전트, 어떤 환경에서도 동일하게 동작.

### 7.1 CLI 사양

설치:
```bash
npm install -g orgwiki-cli
# 또는
brew install orgwiki
```

설정 (한 번만):
```bash
orgwiki login          # GitHub OAuth, Org 권한
orgwiki use <org-name> # 활성 Org 선택
```

핵심 명령어:

| 명령어 | 시그니처 | 용도 |
|---|---|---|
| `orgwiki ask` | `<question>` | 자연어 질의. 답변 + 출처 페이지 링크. |
| `orgwiki context` | `<file...>` | 작업 중인 파일과 관련된 wiki 페이지 본문을 stdout으로 dump. **에이전트가 가장 자주 부르는 명령**. |
| `orgwiki search` | `<query>` | 키워드 검색. 페이지 경로 + 발췌 목록. |
| `orgwiki read` | `<page-path>` | 특정 페이지 본문 출력 (cat과 비슷). |
| `orgwiki gotchas` | `<repo>` | 해당 repo의 함정 섹션만 골라서 출력. |
| `orgwiki adr` | `[--topic <t>]` | ADR 검색/나열. |
| `orgwiki lint` | (없음) | wiki 헬스체크 (stale, orphan, broken refs). |
| `orgwiki propose` | `--topic <t>` | 새 페이지 작성 제안 (사람이 트리거). |
| `orgwiki status` | (없음) | 마지막 sync 시점, 대기 중 PR 수 등. |

설계 원칙:
- **모든 출력은 stdout 마크다운**. 에이전트가 그대로 컨텍스트에 담을 수 있게.
- **모든 응답에 출처 포함**. `> src: org/repo-A@a3f12b3c:src/handlers/login.ts#L45-L78` 형태.
- **종료 코드로 신호**: 0 (성공), 1 (없음), 2 (네트워크 오류), 3 (인증 오류). SKILL이 분기 가능.
- **`--json` 플래그**: 구조화된 응답이 필요할 때.
- **stateless**: 매 호출이 독립적. 세션 관리 없음.

호출 예시:
```bash
$ orgwiki ask "결제 환불 로직 어디에 있어?"
환불 처리는 두 곳에 있습니다.

1. **billing-service/src/refund.ts** — 메인 환불 핸들러.
   V1 결제로 진행된 건만 처리. V2는 미구현.
   > src: org/billing-service@7c8d2a1:src/refund.ts#L1-L80

2. **auth-service/src/handlers/cancel.ts** — 구독 취소 시 자동 환불.
   > src: org/auth-service@a3f12b3c:src/handlers/cancel.ts#L120-L155

⚠️ 관련 ADR: decisions/2026-04-02-payment-v2-migration.md
   V2 마이그레이션 진행 중. 새 환불 코드는 V2 어댑터를 거쳐야 합니다.

[더 보기]: orgwiki read decisions/2026-04-02-payment-v2-migration.md
```

```bash
$ orgwiki context src/payment/refund.ts
# 관련 페이지 3개를 마크다운으로 dump
# (에이전트가 그대로 자기 컨텍스트에 담음)
```

### 7.2 SKILL.md — 진짜 차별화는 여기서

CLI를 만드는 건 쉽다. 진짜 무기는 **에이전트가 CLI를 *언제·어떻게* 호출할지를 결정론적으로 강제하는 SKILL.md**다. 좋은 SKILL이 데모의 박수 포인트를 만든다.

#### 7.2.1 SKILL.md 풀 초안

```markdown
# OrgWiki Skill

This codebase is part of an organization that maintains an OrgWiki at org/wiki.
You MUST use the `orgwiki` CLI before, during, and after non-trivial work.

## Rule 1 — Pre-flight (before any non-trivial change)

Before writing or modifying code:

1. List the files you plan to read or modify.
2. Run `orgwiki context <files>` to fetch relevant wiki pages.
3. Read the gotchas section in full. Treat it as authoritative.
4. If your plan contradicts an ADR (in decisions/), STOP and surface it
   to the user BEFORE writing any code. Do not silently violate decisions.

You MUST NOT skip this step on the assumption that "I already know this codebase."
The wiki encodes decisions and conventions that are not in the code itself.

## Rule 2 — During work

When you encounter:

- An unfamiliar pattern → run `orgwiki search <pattern>` before assuming it's a mistake.
- A deprecation marker in code → trust the wiki's gotchas page over the code comment
  (the wiki is more current; the code comment may be stale).
- A naming convention dispute → defer to `orgwiki read repos/<repo>/conventions.md`.
- A request to add a new dependency → run `orgwiki search <library-name>`. The team
  may have an explicit decision against it.

## Rule 3 — Citation discipline

When you reference something the wiki told you, cite it in your response to the user:

  > Per `repos/auth-service/gotchas.md`: V1 SDK is deprecated.

This makes your reasoning auditable. The user should be able to verify your claims.

## Rule 4 — Post-flight

After completing your work:

- If you discovered a new gotcha, convention, or design decision that is NOT in the wiki,
  mention it to the user and offer to propose a wiki update via `orgwiki propose`.
- If your changes touched files referenced in wiki page sources, mention which wiki
  pages may need updating.

## Rule 5 — When the wiki disagrees with the code

If the wiki says one thing and the code does another:

1. Default: trust the wiki. The code may be a stale leftover.
2. Surface the conflict to the user explicitly. Do not silently pick one.
3. After resolution, suggest updating either the code or the wiki.

## Rule 6 — When the wiki has nothing to say

If `orgwiki context` returns no relevant pages:

1. Proceed cautiously. Treat the area as undocumented.
2. After completing the change, strongly consider proposing a new wiki page.

## Hard prohibitions

- Do NOT proceed with work that contradicts an ADR without explicit user approval.
- Do NOT cite the wiki for claims it does not actually make.
- Do NOT update wiki pages directly. Use `orgwiki propose` and let the maintainer
  agent and human review handle it.

## CLI cheatsheet

| Need                          | Command                              |
|-------------------------------|--------------------------------------|
| Context for files I'll touch  | orgwiki context <files...>           |
| Question in natural language  | orgwiki ask "<question>"             |
| Search by keyword             | orgwiki search <query>               |
| Read a known page             | orgwiki read <path>                  |
| All gotchas for a repo        | orgwiki gotchas <repo>               |
| Find an ADR                   | orgwiki adr --topic <t>              |
| Suggest a new wiki page       | orgwiki propose --topic <t>          |
```

#### 7.2.2 SKILL이 만드는 행동 차이

같은 사용자 요청 *"환불 핸들러 추가해줘"*에 대한 응답:

**SKILL 없을 때**:
```
좋아요, 환불 핸들러를 추가하겠습니다.
[chargeUser() 함수를 import해서 환불 코드 작성]
```

**SKILL 있을 때**:
```
환불 핸들러를 추가하기 전에 관련 컨텍스트를 확인하겠습니다.

$ orgwiki context src/payment/

확인 결과:
- decisions/2026-04-02-payment-v2-migration.md에 따르면 V2 SDK로 마이그레이션 중입니다.
- repos/billing-service/gotchas.md에 V1 chargeUser()는 신규 사용 금지로 명시돼 있습니다.

따라서 두 가지 선택지가 있습니다:
  1. V2 어댑터를 먼저 만들고 그 위에 환불을 구현한다 (권장)
  2. 임시로 V1을 쓰되, 마이그레이션 시 다시 작성할 것을 명시한다

어느 방향으로 갈까요?
```

이 차이가 데모에서 박수를 만든다.

### 7.3 사람이 직접 쓰는 시나리오

CLI는 에이전트만의 도구가 아니다. 사람이 같은 도구를 그대로 쓴다:

- **신입 온보딩**: `orgwiki ask "이 회사에서 인증 어떻게 굴러가요?"` → 한 줄로 시작점.
- **PR 리뷰 직전**: `orgwiki context <변경된 파일>` → 리뷰어가 놓칠 수 있는 컨텍스트 한눈에.
- **Slack 대안**: 같은 질문이 반복되는 채널을 CLI 한 번으로 대체.
- **회의 직전**: `orgwiki adr --topic billing` → 어제까지의 결정을 빠르게 복기.

**한 도구가 사람과 에이전트 모두에게 작동한다는 게 CLI의 본질적 강점**. MCP는 에이전트 전용. CLI는 보편.

---

## 8. 검증, 신뢰, drift 관리

### 8.1 위험: LLM이 wiki를 부패시키는 시나리오

논문 *"LLMs Corrupt Your Documents When You Delegate"*가 정곡. wiki가 거짓말로 차면 에이전트한테 거짓을 먹이는 꼴.

### 8.2 방어 5층

1. **Provenance 강제**
   - 모든 페이지 frontmatter에 `sources` 필드 (파일 경로 + line range + commit SHA).
   - 본문 내 사실 진술도 인라인 인용 가능.

2. **Stale 자동 감지**
   - sync 시점에 frontmatter의 `sources` 라인이 실제 파일에서 바뀌었는지 검증.
   - 바뀌었는데 페이지 미갱신이면 `[STALE]` 자동 마킹 + `meta/stale.md`에 기록.

3. **PR 게이트**
   - 자동 머지는 (a) 페이지 신규 생성, (b) frontmatter 메타데이터 갱신, (c) 신뢰도 high인 단순 추가에 한정.
   - 그 외(기존 사실 변경, 모순 해결, 갱신 폭이 큼)는 PR로 사람 리뷰.

4. **Lint pass**
   - 페이지 간 모순 (같은 사실에 다른 진술), 고아 페이지, 누락된 cross-ref, 빈 출처 등 정기 점검.
   - `orgwiki lint` 명령어 + CI에서 자동 실행.

5. **"모르면 모른다"**
   - SKILL/CLAUDE.md에서 강제: 출처 못 찾으면 `[NEEDS HUMAN INPUT]`로 두고 사람한테 물어봄.
   - 추측으로 빈 칸 메우는 행동 금지.

### 8.3 측정 가능한 신뢰 지표

해커톤 데모에서 보여줄 수 있는 metric:
- **Citation coverage**: 페이지 내 사실 진술 중 출처 인용 비율 (목표 95%+)
- **Stale rate**: 전체 페이지 중 stale로 마킹된 비율 (낮을수록 좋음)
- **CLI call rate**: 에이전트 작업 중 `orgwiki context` 호출 비율 (SKILL이 잘 동작하는지 지표)
- **Override rate**: 에이전트가 "wiki와 코드가 다른데?" 라고 사용자에게 묻는 빈도

---

## 9. 해커톤 MVP 스코프 (CMUX × AIM, 4월 26일, 9시-18시)

### 9.1 잘라낼 것 (할 수 있어도 안 함)

- 자체 검색 인프라 (대신 grep + 인메모리 BM25)
- 자체 UI / 대시보드
- 멀티 organization
- 권한 시스템 / 사용자 인증
- 비용 추적 / 사용량 관리
- production-grade webhook 큐 (대신 단순 Express 서버)
- **MCP server, IDE 플러그인, 웹 클라이언트** — Phase 2 이후

### 9.2 유지할 것 (이게 데모 핵심)

1. 단일 GitHub Org + 데모용 repo 2-3개 (시드 데이터 포함)
2. webhook 받는 서버 (Cloudflare Worker 또는 Express on Fly.io)
3. 변경 파일 → 영향받는 페이지 갱신 → wiki repo PR 생성
4. **`orgwiki` CLI**: 최소 5개 명령어 (`ask`, `context`, `read`, `gotchas`, `lint`)
5. **SKILL.md**: 잘 다듬은 풀버전. 데모에서 핵심 무기.
6. 시드 데이터: 데모용 repo 2-3개에 일부러 함정과 ADR을 심어둠.

### 9.3 9시간 일정 (팀 4인 가정)

CLI + SKILL 단일 트랙으로 가면서 작업이 단순해져 트랙을 2개로 줄임.

| 시간 | 작업 |
|---|---|
| 09:00-09:30 | 킥오프, 역할 분담, 모노레포 skeleton |
| 09:30-12:30 | **트랙 A (백엔드, 인원 2)**: webhook 서버 + ingest 파이프라인 + wiki API |
| 09:30-12:30 | **트랙 B (클라이언트 + 시드, 인원 2)**: CLI 뼈대, SKILL.md 작성, 시드 repo 컨텐츠 작성 |
| 12:30-13:30 | 점심 + 통합 1차 (CLI ↔ 서버 wire-up) |
| 13:30-15:30 | 통합 2차: webhook → wiki 갱신 → CLI에서 새 내용 읽힘 확인. 데모 시나리오 검증. |
| 15:30-17:00 | 데모 리허설 3회 이상. 슬라이드 제작. 백업 시나리오 영상 녹화. |
| 17:00-18:00 | 제출, 슬라이드 마무리 |
| 18:00 | 제출 마감 |
| 19:30 | 파이널 피칭 (선정 시) |

### 9.4 절대 안 되는 것

- 무대에서 webhook이 진짜로 안 가는 경우 → **백업 영상 필수**.
- 인터넷 끊김 대비 → **로컬 mock webhook trigger 명령** 준비.
- 에이전트 응답 느림 대비 → **사전 캐시된 응답** 옵션 준비.

---

## 10. 데모 스토리보드 (3분)

### 10.1 시나리오: "신입의 첫 PR"

**[0:00-0:30] 페인 셋업**
- 화면: 한국 IT 회사의 가상 GitHub Org. 7개 repo. Slack에 "결제 환불 어떻게 처리해요?" 같은 신입 질문이 쌓임.
- 내레이션: "어제 입사한 신입이 결제 환불 핸들러를 추가하라고 받았다. 코드만 봐서는 V1 SDK가 멀쩡해 보인다. 실제로는 이미 deprecated됐고 V2 마이그레이션 중이다. 코드에 그 표시는 어디에도 없다."

**[0:30-1:00] OrgWiki repo 공개**
- 화면: org/wiki repo. `decisions/2026-04-02-payment-v2-migration.md`, `repos/billing-service/gotchas.md`가 이미 존재.
- 내레이션: "OrgWiki는 매 push마다 이런 페이지를 자동 갱신해놨다. 사람이 쓴 게 아니라 에이전트가 코드 변경을 보고 컴파일했다."

**[1:00-2:00] 라이브 데모 — CLI + SKILL이 작동하는 모습**
- 화면: 신입의 노트북에서 Claude Code 실행. SKILL.md가 프로젝트에 들어 있음.
- 사용자 입력: "환불 핸들러 추가해줘"
- 에이전트의 행동을 터미널에서 그대로 보여줌:
  ```
  $ orgwiki context src/payment/handlers/
  [관련 페이지 3개 출력]
  ```
- 그 다음 에이전트가 사용자에게 응답:
  > "ADR-2026-04에 따르면 V2 SDK로 마이그레이션 중입니다. 현재 코드엔 V1만 있어서, V2 어댑터를 먼저 만들까요? 아니면 임시로 V1로 가실 건가요? V2 어댑터를 권장합니다."
- 박수 포인트.

**[2:00-2:30] 라이브 sync**
- 화면: 다른 멤버가 `billing-service`에 새 ADR을 push.
- 30초 안에 OrgWiki webhook이 발동되어 wiki repo에 PR이 자동 생성되는 모습.
- 내레이션: "팀이 하던 일을 그대로 하면, wiki는 자동으로 따라간다."

**[2:30-3:00] 마무리**
- 한 줄 요약: *"Compile your team's tribal knowledge into agent-readable context."*
- 한 슬라이드: cmux와의 보완 관계 ("cmux는 *세션 안의 환경*, OrgWiki는 *세션을 시작할 때 끌어오는 환경*").
- 호출: 오픈소스. GitHub App 1클릭 설치. 어떤 에이전트든 SKILL.md 한 장이면 끝.

### 10.2 백업 시나리오

- webhook 안 갈 경우: 사전 녹화한 30초 영상.
- 에이전트 응답 느릴 경우: 캐시된 응답을 mock으로 반환하는 토글.
- 인터넷 죽을 경우: 로컬 모든 컴포넌트만으로 시연 (GitHub은 read-only로 fallback).

---

## 11. 기술 스택

### 11.1 후보안

| 컴포넌트 | 1순위 | 2순위 | 이유 |
|---|---|---|---|
| Webhook 서버 | Cloudflare Workers | Express on Fly.io | edge에서 빠르게 받기, 비용 무료 |
| Job queue | Cloudflare Queues | Redis on Upstash | 단순함 |
| Wiki repo I/O | `@octokit/rest` (Node) | `gh` CLI shell-out | 안정성 |
| LLM | Claude Sonnet 4.5 (글쓰기), Gemini 2.5 Flash (영향도 분석) | GPT-4o | 해커톤 크레딧 활용, 작업별 비용 최적화 |
| Wiki API | Hono on Cloudflare Worker | Express | 단순한 read API만 노출 |
| **CLI** | **TypeScript + commander** (`npm install -g`) | **Go + cobra** | TS와 모놀리식 |
| 검색 | 인메모리 lunr (BM25) + 단순 임베딩 | qdrant | MVP 단계 |
| 인덱스 저장 | wiki repo 내 JSON | KV store | git이 진실 원칙 유지 |

### 11.2 모놀리식 vs 분리

해커톤 동안엔 **monorepo 1개**로 가기. `packages/server`, `packages/cli`, `packages/agent-prompts`, `packages/seed-repos`. 배포 후 분리.

---

## 12. 누가 쓸까 / 누가 안 쓸까

### 12.1 적합한 팀

- 코딩 에이전트(Claude Code, Codex, cmux)를 일상적으로 쓰는 팀
- 5+ 명, 3+ repo, 활발한 코드베이스
- 결정·관습이 코드에 안 적혀 있는 게 진짜 페인
- 기존에 README/Notion으로 시도했지만 stale로 실패한 경험

### 12.2 안 맞는 팀

- 솔로 개발자 → 그냥 README + CLAUDE.md로 충분
- 모노레포 단일 repo → eliavamar의 repositories-wiki가 더 가벼움
- 코딩 에이전트를 안 쓰는 팀 → 가치 제안 자체가 안 닿음
- 보안상 외부 LLM에 코드 전송 불가 → 자체 호스팅 변종 필요 (로드맵)

### 12.3 솔직한 약점

- **에이전트가 SKILL을 매번 잘 따르리라는 보장 없음**: 모델에 따라 정책 따르는 정도가 다름. → CLI call rate metric으로 추적 + SKILL 튜닝.
- **첫 인덱싱 비용**: 큰 코드베이스의 cold start는 LLM 비용 큼. → 점진적 onboarding UX.
- **사람 검토 부담**: 자동 머지 비율을 잘 못 맞추면 PR 폭주로 팀이 지침. → 신뢰도 임계치 튜닝이 핵심 운영 변수.
- **"그래서 README보다 뭐가 다른데?"**에 대한 공격: 답은 *자동 유지*와 *에이전트 소비 최적화*. 페인이 충분히 큰 팀에게만 답이 강함.

---

## 13. 향후 로드맵 (해커톤 이후)

### Phase 1 (MVP 다듬기, 1-2주)
- 첫 onboarding UX (clone → install GitHub App → 자동 시드 PR)
- 신뢰도 점수 calibration
- 비용/사용량 대시보드 (간단)

### Phase 2 (확장 채널, 1-2개월)
- **MCP server**: CLI를 thin wrapper로 감싸 MCP 표준 노출. Claude Code 네이티브 통합.
- **VS Code / Cursor 확장**: CLI 호출을 GUI로.
- **Slack 봇**: `/orgwiki ask` 명령어로 채널에서 직접.

> CLI를 핵심에 두고 다른 채널은 모두 CLI를 호출하는 wrapper로 만든다. 핵심 로직 중복 없음.

### Phase 3 (검증과 신뢰, 분기 단위)
- Citation coverage / stale rate 자동 metric
- 페이지 간 모순 자동 감지
- "이 페이지 진짜야?" 사람 어노테이션 흐름

### Phase 4 (자체 호스팅 / 엔터프라이즈)
- 자체 호스팅 옵션 (Docker compose)
- 사내 LLM 게이트웨이 통합
- SAML/SSO

### Phase 5 (확장)
- Slack / Linear / Jira ingest (코드 외 소스)
- 회의록 → ADR 자동 제안
- 다른 에이전트 환경 (cmux, OpenHands, Cline) 공식 SDK

---

## 14. 부록 A — 자주 받을 질문

**Q. 그냥 Greptile / Sourcegraph Cody 아니야?**
A. 걔네는 *코드*를 검색해줌. OrgWiki는 *코드에 없는 결정·관습·암묵지*를 외화함. 둘은 보완재. 실제로 에이전트가 둘 다 호출하는 워크플로우도 가능.

**Q. Devin DeepWiki와 차이는?**
A. (1) Org 단위, (2) 에이전트 소비 최적화, (3) push-driven incremental, (4) 결과가 git repo로 외화되어 검열 가능, (5) 오픈소스 지향, (6) CLI라 어떤 에이전트든 호환.

**Q. `llms.txt`로 충분하지 않아?**
A. `llms.txt`는 정적/단일/사람작성. 팀 스케일에서 stale을 못 막음. OrgWiki는 동적/다파일/에이전트유지 + 사람 게이트.

**Q. 왜 MCP server를 안 만들었어?**
A. 9시간 안에 임팩트 있는 데모를 만드는 게 우선. CLI 하나면 Claude Code, Codex, cmux, Cline 모두에서 동작하고 시각화도 더 강함. MCP는 Phase 2에서 CLI 위에 thin wrapper로 추가 예정.

**Q. 왜 IDE 플러그인 안 만들었어?**
A. 행사 트랙이 명시한 "터미널 워크플로우, IDE 없이"에 정면으로 부합하기 위함. 그리고 에이전트가 IDE에 종속되면 cmux 같은 새로운 환경에서 못 쓴다.

**Q. wiki가 거짓말하면?**
A. 모든 페이지에 출처. stale 자동 감지. PR 게이트. lint pass. 그래도 거짓말이 들어오면 git log로 추적해서 롤백 가능. 사람이 마지막 게이트인 건 의도된 설계.

**Q. 비용은?**
A. push당 평균 $0.05-0.15 (Claude Sonnet 기준, 1-3페이지 갱신). 팀 단위 월 $50-200 예상. 자체 호스팅 옵션 + 모델 선택으로 조정 가능.

**Q. 에이전트가 SKILL을 무시하면?**
A. 무시 가능성 있음. 그래서 metric이 필요. CLI call rate를 추적. 낮으면 SKILL 튜닝 또는 강제 (CLAUDE.md에 hard rule). 또한 SKILL을 사용자 측 `CLAUDE.md`에 inline으로 박는 옵션 제공.

**Q. 보안 — 코드를 외부 LLM에 보내는 거잖아?**
A. MVP는 그렇음. 자체 호스팅 + 사내 LLM 옵션이 Phase 4. 또한 ingest 시 토큰 단위로 마스킹할 수 있는 옵션 (시크릿 패턴 자동 redaction).

---

## 15. 부록 B — 용어집

| 용어 | 정의 |
|---|---|
| **Org / Organization** | GitHub Organization. 팀의 코드 공간. |
| **Wiki repo** | OrgWiki가 유지하는 마크다운 git repo. Org 안에 위치. |
| **Source repo** | 평소 작업하는 일반 코드 repo. Wiki의 입력. |
| **Page** | wiki repo 내 하나의 마크다운 파일. frontmatter + 본문. |
| **Source range** | 페이지가 인용한 파일의 line range + commit SHA. provenance의 단위. |
| **Stale** | source가 바뀌었는데 페이지가 안 따라간 상태. |
| **Confidence** | 페이지 frontmatter의 신뢰도 (low / medium / high). 자동 머지 게이트. |
| **Influence map** | 파일 → 페이지 역인덱스. incremental sync의 핵심. |
| **SKILL.md** | 에이전트가 작업 시작 시 자동 로드하는 정책 문서. CLI 호출 규칙을 정의. |
| **CLI call rate** | 에이전트가 작업 중 `orgwiki` CLI를 부른 비율. SKILL이 잘 동작하는지 지표. |
| **ADR** | Architecture Decision Record. 시간 순으로 누적되는 결정 기록. |
| **Gotcha** | 코드만 보면 모르는 함정. OrgWiki의 가장 가치 있는 페이지 타입. |

---

## 16. 부록 C — 한 줄로 표현한 핵심들

- **What**: GitHub Org의 모든 main 변경을 자동 흡수하는, CLI + SKILL로 에이전트가 끌어 쓰는 마크다운 wiki.
- **Why**: 코딩 에이전트가 매 세션 재학습하는 비용과 암묵지 누락 비용이 크다.
- **How**: webhook으로 받아서 incremental하게 영향 페이지만 갱신하고, `orgwiki` CLI 한 줄과 SKILL.md 한 장으로 에이전트가 끌어 쓴다.
- **Why git**: audit, 롤백, 사람 게이트. wiki 자체가 LLM의 자유 작문 공간이 되면 안 된다.
- **Why incremental**: 토큰. 에이전트는 의미적 작업만, 기계적 일은 코드.
- **Why CLI**: 보편 호환 (어떤 에이전트든 bash 실행 가능), 결정론적 호출 (SKILL로 강제 가능), 사람도 같은 도구를 쓴다.
- **Why no MCP yet**: CLI 하나로 모든 에이전트 커버. MCP는 Phase 2에서 CLI 위 thin wrapper로 추가.
- **Why now**: cmux 같은 에이전트 환경이 표준이 되면서 컨텍스트가 1급 시민이 됐다.
- **Differentiator**: Org 단위 + 에이전트 소비 최적화 + push-driven + git-native audit + CLI 보편성.
- **Verb**: *Compile your team's tribal knowledge into agent-readable context.*

---

*문서 버전: 0.2 · 2026-04-26 · CLI + SKILL 단일 트랙으로 정리 · CMUX × AIM Hackathon Seoul 제출 준비용*
