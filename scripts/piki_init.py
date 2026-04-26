import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _read_env(name: str, required: bool = True, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if required and not value:
        print(f"[ERROR] Missing required environment variable: {name}")
        sys.exit(1)
    return value


def _github_request(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"message": text}
        return exc.code, parsed


def _render_template(path: Path, values: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _get_file_sha(owner: str, repo: str, file_path: str, branch: str, token: str) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
    status, response = _github_request("GET", url, token)
    if status == 200:
        return response.get("sha")
    if status == 404:
        return None
    raise RuntimeError(f"Failed to read {owner}/{repo}:{file_path} ({status}) -> {response}")


def _upsert_file(
    owner: str,
    repo: str,
    file_path: str,
    branch: str,
    content: str,
    commit_message: str,
    token: str,
    force_overwrite: bool,
    dry_run: bool,
) -> str:
    if dry_run:
        print(f"[DRY-RUN] {owner}/{repo}:{file_path} (branch={branch})")
        return "planned"

    existing_sha = _get_file_sha(owner, repo, file_path, branch, token)
    if existing_sha and not force_overwrite:
        return "skipped"

    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    status, response = _github_request("PUT", url, token, payload)
    if status not in (200, 201):
        raise RuntimeError(f"Failed to write {owner}/{repo}:{file_path} ({status}) -> {response}")
    return "updated" if existing_sha else "created"


def main() -> None:
    org = _read_env("INPUT_ORG")
    wiki_repo = _read_env("INPUT_WIKI_REPO")
    source_repos_csv = _read_env("INPUT_SOURCE_REPOS")
    wiki_branch = _read_env("INPUT_WIKI_BRANCH", required=False, default="main")
    branch = _read_env("INPUT_BASE_BRANCH", required=False, default="main")
    force_overwrite = _read_env("INPUT_FORCE_OVERWRITE", required=False, default="false").lower() == "true"
    dry_run = _read_env("INPUT_DRY_RUN", required=False, default="false").lower() == "true"
    token = _read_env("GITHUB_TOKEN", required=not dry_run)

    source_repos = [name.strip() for name in source_repos_csv.split(",") if name.strip()]
    if not source_repos:
        print("[ERROR] INPUT_SOURCE_REPOS has no valid repository names.")
        sys.exit(1)

    root = Path(__file__).resolve().parent.parent
    wiki_readme_template_path = root / "templates" / "piki.wiki.README.md.tmpl"
    wiki_schema_template_path = root / "templates" / "piki.wiki.CLAUDE.md.tmpl"
    wiki_index_template_path = root / "templates" / "piki.wiki.index.md.tmpl"
    wiki_log_template_path = root / "templates" / "piki.wiki.log.md.tmpl"
    workflow_template_path = root / "templates" / "piki.repo.workflow.yml.tmpl"

    wiki_readme_template = _render_template(
        wiki_readme_template_path,
        {
            "ORG": org,
            "WIKI_REPO": wiki_repo,
        },
    )
    wiki_schema_template = _render_template(
        wiki_schema_template_path,
        {"ORG": org, "WIKI_REPO": wiki_repo},
    )
    wiki_index_template = _render_template(
        wiki_index_template_path,
        {"ORG": org, "WIKI_REPO": wiki_repo},
    )
    wiki_log_template = _render_template(
        wiki_log_template_path,
        {"ORG": org},
    )
    workflow_template = _render_template(
        workflow_template_path,
        {
            "ORG": org,
            "WIKI_REPO": wiki_repo,
            "WIKI_BRANCH": wiki_branch,
        },
    )
    wiki_dispatch_workflow = _render_template(
        root / "templates" / "piki.wiki.dispatch.workflow.yml.tmpl",
        {"ORG": org},
    )

    has_error = False
    print(f"\n[INFO] Initializing single wiki repository: {org}/{wiki_repo}")
    try:
        wiki_files = [
            ("README.md", wiki_readme_template, "chore(piki): initialize wiki repository"),
            ("CLAUDE.md", wiki_schema_template, "chore(piki): add wiki schema"),
            ("index.md", wiki_index_template, "chore(piki): add wiki index"),
            ("log.md", wiki_log_template, "chore(piki): add wiki sync log"),
            ("meta/file-page-index.json", "{}\n", "chore(piki): add initial file-page index"),
            ("meta/stale.md", "# Stale Pages\n\n- (none)\n", "chore(piki): add stale tracker"),
            ("meta/orphans.md", "# Orphan Pages\n\n- (none)\n", "chore(piki): add orphan tracker"),
            (
                ".github/workflows/piki-repo-dispatch.yml",
                wiki_dispatch_workflow,
                "chore(piki): add repository_dispatch ingest trigger",
            ),
        ]
        for file_path, content, message in wiki_files:
            result = _upsert_file(
                owner=org,
                repo=wiki_repo,
                file_path=file_path,
                branch=branch,
                content=content,
                commit_message=message,
                token=token,
                force_overwrite=force_overwrite,
                dry_run=dry_run,
            )
            print(f"[OK] {org}/{wiki_repo}:{file_path}={result}")
    except Exception as exc:  # pylint: disable=broad-except
        has_error = True
        print(f"[ERROR] {org}/{wiki_repo}: {exc}")

    for repo in source_repos:
        full_name = f"{org}/{repo}"
        print(f"\n[INFO] Installing PR trigger workflow in {full_name}")
        try:
            workflow_result = _upsert_file(
                owner=org,
                repo=repo,
                file_path=".github/workflows/piki-sync.yml",
                branch=branch,
                content=workflow_template.replace("{{REPO}}", repo),
                commit_message="chore(piki): add PR-to-main sync trigger workflow",
                token=token,
                force_overwrite=force_overwrite,
                dry_run=dry_run,
            )
            print(f"[OK] {full_name} | .github/workflows/piki-sync.yml={workflow_result}")
        except Exception as exc:  # pylint: disable=broad-except
            has_error = True
            print(f"[ERROR] {full_name}: {exc}")

    if has_error:
        sys.exit(1)
    print("\n[DONE] piki init completed.")


if __name__ == "__main__":
    main()
