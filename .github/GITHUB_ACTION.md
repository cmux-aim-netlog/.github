# GitHub Action Guide (.github)

이 파일은 `piki init`으로 자동 생성되었습니다.

## 목적
- `.github` 에서 `main` 대상 PR merge 시 `wiki` 저장소로 이벤트를 전달합니다.

## 필수 시크릿 (Org-level Actions secret 권장)
- `GITHUB_TOKEN`: source repo `contents:read` + wiki repo `contents:write` 권한이 있는 GitHub 토큰.
- `GEMINI_API_KEY`: Gemini API key. `wiki` 의 ingest workflow가 LLM 호출 시 사용.

## 워크플로우
- 트리거 (source side): `.github/.github/workflows/piki-sync.yml` — `pull_request.closed` + `merged == true` + `base.ref == main` → `repository_dispatch` to `wiki`.
- ingest (wiki side): `wiki/.github/workflows/piki-ingest.yml` — `repository_dispatch` 또는 `workflow_dispatch` 로 실행.

Organization: `cmux-aim-netlog`
