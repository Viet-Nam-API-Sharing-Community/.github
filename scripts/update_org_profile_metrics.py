#!/usr/bin/env python3
"""Generate dynamic GitHub organization profile metrics.

This script is intended to live inside an organization's `.github` repository.
It scans public repositories for the configured organization, aggregates
repository language data, identifies high-signal repositories, infers technical
capabilities, and rewrites the generated block in `profile/README.md`.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "profile" / "README.md"
START = "<!-- ORG-PROFILE-METRICS:START -->"
END = "<!-- ORG-PROFILE-METRICS:END -->"
FALLBACK_LANGUAGE_BYTES = 100_000

ORG_LOGIN = os.environ.get("ORG_LOGIN", "Viet-Nam-API-Sharing-Community")
ORG_LABEL = os.environ.get("ORG_LABEL", "Vietnam API Sharing Community")
ORG_POSITIONING = os.environ.get(
    "ORG_POSITIONING",
    "open API references, integration SDKs, banking automation, and developer enablement",
)

LANGUAGE_COLORS = {
    "Python": "3776AB",
    "TypeScript": "3178C6",
    "JavaScript": "F7DF1E",
    "PHP": "777BB4",
    "Shell": "4EAA25",
    "Dockerfile": "2496ED",
    "HTML": "E34F26",
    "CSS": "1572B6",
    "Go": "00ADD8",
    "C++": "00599C",
    "C#": "512BD4",
    "C": "A8B9CC",
    "Java": "ED8B00",
    "Rust": "000000",
    "Ruby": "CC342D",
    "Jupyter Notebook": "F37626",
    "Blade": "F7523F",
    "PowerShell": "5391FE",
    "Makefile": "427819",
    "SCSS": "CC6699",
}

TECH_RULES = {
    "Python": ["Python", "FastAPI", "Automation", "SDK Engineering"],
    "TypeScript": ["TypeScript", "Node.js", "Developer Platforms", "VS Code Extension"],
    "JavaScript": ["JavaScript", "Web UI", "Automation", "Cloud Dashboard"],
    "PHP": ["PHP", "Laravel", "Control Panel", "Backend Engineering"],
    "Shell": ["Shell", "Linux", "Provisioning", "Operations Automation"],
    "Dockerfile": ["Docker", "Containerization", "Deployment Automation"],
    "Go": ["Go", "Cloud Native", "CLI Engineering"],
    "C++": ["C++", "Systems Engineering", "Performance"],
    "C#": ["C#", ".NET", "Desktop/Backend Engineering"],
    "HTML": ["HTML", "Documentation", "Static UI"],
    "CSS": ["CSS", "Frontend", "UI Engineering"],
}

TOPIC_TECH = {
    "ai": "AI Engineering",
    "artificial-intelligence": "AI Engineering",
    "llm": "LLM / Local AI",
    "nvidia": "NVIDIA GPU",
    "dgx": "NVIDIA DGX Spark",
    "cloud": "Cloud Platform",
    "kubernetes": "Kubernetes / K3s",
    "k3s": "Kubernetes / K3s",
    "proxmox": "Proxmox",
    "docker": "Docker",
    "api": "API Integration",
    "fastapi": "FastAPI",
    "banking": "Banking API",
    "automation": "Automation",
    "devtools": "Developer Tools",
    "vscode": "VS Code Extension",
    "gpu": "GPU Infrastructure",
}


@dataclass(frozen=True)
class Repo:
    owner: str
    name: str
    full_name: str
    html_url: str
    description: str
    language: str | None
    stargazers_count: int
    forks_count: int
    topics: tuple[str, ...]
    archived: bool
    fork: bool
    updated_at: str


class GitHubClient:
    def __init__(self) -> None:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{ORG_LOGIN}-profile-metrics",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get_json(self, url: str) -> Any:
        request = urllib.request.Request(url, headers=self.headers)
        last_error: RuntimeError | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                message = error.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"GitHub API error {error.code} for {url}: {message}")
                if error.code not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                    raise last_error from error
                retry_after = error.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(min(delay, 10))
        if last_error:
            raise last_error
        raise RuntimeError(f"GitHub API request failed for {url}")

    def list_org_repos(self, login: str) -> list[Repo]:
        repos: list[Repo] = []
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {
                    "type": "public",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                }
            )
            data = self.get_json(f"https://api.github.com/orgs/{login}/repos?{query}")
            if not data:
                break
            for item in data:
                repos.append(
                    Repo(
                        owner=item["owner"]["login"],
                        name=item["name"],
                        full_name=item["full_name"],
                        html_url=item["html_url"],
                        description=item.get("description") or "",
                        language=item.get("language"),
                        stargazers_count=item.get("stargazers_count", 0),
                        forks_count=item.get("forks_count", 0),
                        topics=tuple(item.get("topics", [])),
                        archived=bool(item.get("archived", False)),
                        fork=bool(item.get("fork", False)),
                        updated_at=item.get("updated_at") or "",
                    )
                )
            if len(data) < 100:
                break
            page += 1
        return repos

    def repo_languages(self, full_name: str) -> dict[str, int]:
        return self.get_json(f"https://api.github.com/repos/{full_name}/languages")


def percentage(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(value * 100 / total, 1)


def progress_bar(pct: float) -> str:
    filled = max(1, min(20, round(pct / 5))) if pct > 0 else 0
    return "█" * filled + "░" * (20 - filled)


def repo_score(repo: Repo) -> int:
    topic_bonus = len(repo.topics) * 3
    description_bonus = 5 if repo.description else 0
    archive_penalty = -100 if repo.archived else 0
    fork_penalty = -20 if repo.fork else 0
    return repo.stargazers_count * 6 + repo.forks_count * 3 + topic_bonus + description_bonus + archive_penalty + fork_penalty


def render_language_badges(language_bytes: Counter[str]) -> str:
    logo_map = {
        "C++": "cplusplus",
        "C#": "dotnet",
        "Jupyter Notebook": "jupyter",
        "Shell": "gnubash",
        "Dockerfile": "docker",
    }
    badges: list[str] = []
    for language, _ in language_bytes.most_common(12):
        color = LANGUAGE_COLORS.get(language, "64748B")
        logo = logo_map.get(language, language.lower().replace(" ", ""))
        logo_color = "000" if language in {"JavaScript", "Linux"} else "white"
        safe_label = language.replace("-", "--").replace(" ", "%20").replace("#", "%23").replace("+", "%2B")
        badges.append(
            f"![{language}](https://img.shields.io/badge/{safe_label}-{color}?style=for-the-badge&logo={logo}&logoColor={logo_color})"
        )
    return "\n".join(badges)


def render_language_rows(language_bytes: Counter[str]) -> list[str]:
    total = sum(language_bytes.values())
    rows = ["| Language | Usage | Share |", "|---|---:|---|"]
    for language, count in language_bytes.most_common(12):
        pct = percentage(count, total)
        rows.append(f"| **{language}** | `{progress_bar(pct)}` | **{pct}%** |")
    return rows


def infer_capabilities(language_bytes: Counter[str], topics: Counter[str]) -> list[str]:
    derived: list[str] = []
    for language, _ in language_bytes.most_common(10):
        derived.extend(TECH_RULES.get(language, [language]))
    for topic, _ in topics.most_common(30):
        normalized = topic.lower()
        if normalized in TOPIC_TECH:
            derived.append(TOPIC_TECH[normalized])

    unique: list[str] = []
    seen: set[str] = set()
    for item in derived:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def render_capability_rows(capabilities: list[str]) -> list[str]:
    categories = {
        "Languages & backend": [
            item
            for item in capabilities
            if item
            in {
                "Python",
                "TypeScript",
                "JavaScript",
                "PHP",
                "Go",
                "Node.js",
                "FastAPI",
                "SDK Engineering",
                "Laravel",
                "Backend Engineering",
            }
        ],
        "Cloud / DevOps / infrastructure": [
            item
            for item in capabilities
            if item
            in {
                "Docker",
                "Containerization",
                "Deployment Automation",
                "Linux",
                "Provisioning",
                "Operations Automation",
                "Cloud Platform",
                "Kubernetes / K3s",
                "Proxmox",
                "NVIDIA GPU",
                "NVIDIA DGX Spark",
                "GPU Infrastructure",
            }
        ],
        "AI / automation / developer tooling": [
            item
            for item in capabilities
            if item
            in {
                "AI Engineering",
                "LLM / Local AI",
                "Automation",
                "Developer Tools",
                "Developer Platforms",
                "VS Code Extension",
                "CLI Engineering",
            }
        ],
        "API / documentation / community": [
            item
            for item in capabilities
            if item in {"API Integration", "Banking API", "Documentation", "Static UI"}
        ],
    }
    rows = ["| Auto-detected capability | Signal |", "|---|---|"]
    for category, items in categories.items():
        signal = " · ".join(items[:10]) if items else "Updating from repository metadata"
        rows.append(f"| **{category}** | {signal} |")
    return rows


def render_featured_repos(repos: list[Repo]) -> list[str]:
    rows = ["| Repository | Engineering signal |", "|---|---|"]
    for repo in sorted(repos, key=repo_score, reverse=True)[:8]:
        signal_parts: list[str] = []
        if repo.language:
            signal_parts.append(repo.language)
        if repo.description:
            signal_parts.append(repo.description.rstrip("."))
        if repo.topics:
            signal_parts.append(" · ".join(repo.topics[:3]))
        if repo.stargazers_count:
            signal_parts.append(f"⭐ {repo.stargazers_count}")
        if repo.forks_count:
            signal_parts.append(f"⑂ {repo.forks_count}")
        signal = " · ".join(signal_parts) or "Recently updated public repository"
        rows.append(f"| [`{repo.name}`]({repo.html_url}) | {signal} |")
    return rows


def aggregate() -> tuple[list[Repo], Counter[str], Counter[str]]:
    client = GitHubClient()
    repos = client.list_org_repos(ORG_LOGIN)
    language_bytes: Counter[str] = Counter()
    topics: Counter[str] = Counter()
    for repo in repos:
        topics.update(repo.topics)
        try:
            language_bytes.update(client.repo_languages(repo.full_name))
        except RuntimeError as error:
            print(f"warning: cannot fetch languages for {repo.full_name}: {error}", file=sys.stderr)
            if repo.language:
                language_bytes[repo.language] += FALLBACK_LANGUAGE_BYTES
        time.sleep(0.15)
    return repos, language_bytes, topics


def render_block(repos: list[Repo], language_bytes: Counter[str], topics: Counter[str]) -> str:
    total_repos = len(repos)
    active_repos = sum(1 for repo in repos if not repo.archived and not repo.fork)
    total_stars = sum(repo.stargazers_count for repo in repos)
    total_forks = sum(repo.forks_count for repo in repos)
    top_language = language_bytes.most_common(1)[0][0] if language_bytes else "Updating"
    latest_update = max((repo.updated_at for repo in repos if repo.updated_at), default="Updating")[:10]
    refreshed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    capabilities = infer_capabilities(language_bytes, topics)

    lines = [
        START,
        "",
        "<div align=\"center\">",
        "",
        render_language_badges(language_bytes),
        "",
        "</div>",
        "",
        f"> Auto-generated organization intelligence for **{ORG_LABEL}**. This profile scans public repositories, language coverage, repository signals, and inferred capabilities for: **{ORG_POSITIONING}**.",
        "",
        "### Real-time organization signals",
        "",
        "| Live signal | Value |",
        "|---|---:|",
        f"| Public repositories monitored | **{total_repos}** |",
        f"| Active source repositories | **{active_repos}** |",
        f"| Detected source languages | **{len(language_bytes)}** |",
        f"| Aggregate public stars | **{total_stars}** |",
        f"| Aggregate public forks | **{total_forks}** |",
        f"| Leading language by code volume | **{top_language}** |",
        f"| Most recent public repository update | **{latest_update}** |",
        "",
        "### Dynamic language coverage",
        "",
        *render_language_rows(language_bytes),
        "",
        "### Auto-detected technology stack",
        "",
        *render_capability_rows(capabilities),
        "",
        "### High-signal repositories",
        "",
        *render_featured_repos(repos),
        "",
        f"<sub>Last metrics refresh: GitHub Actions scheduled/manual update · {refreshed_at}. Detected {len(language_bytes)} languages from GitHub repository language data.</sub>",
        "",
        END,
    ]
    return "\n".join(lines)


def replace_block(readme: str, block: str) -> str:
    if START not in readme or END not in readme:
        raise RuntimeError(f"profile/README.md must contain {START} and {END} markers")
    before = readme.split(START, 1)[0]
    after = readme.split(END, 1)[1]
    return before + block + after


def main() -> int:
    repos, language_bytes, topics = aggregate()
    if not repos or not language_bytes:
        print("Skipped profile update because GitHub returned no repository/language data", file=sys.stderr)
        return 0
    block = render_block(repos, language_bytes, topics)
    original = README.read_text(encoding="utf-8")
    updated = replace_block(original, block)
    README.write_text(updated, encoding="utf-8", newline="\n")
    print(f"Updated {ORG_LABEL} organization profile metrics for {len(repos)} repositories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
