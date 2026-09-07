#!/usr/bin/env python3
"""Refresh profile README: latest posts from site RSS, pinned/flagship repos, focus line."""

from __future__ import annotations

import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
FOCUS_FILE = ROOT / "focus.txt"

# Prefer business + innovation for operator positioning; merge by pubDate.
RSS_FEEDS = [
    "https://www.paulgravette.com/business?format=rss",
    "https://www.paulgravette.com/innovation?format=rss",
    "https://www.paulgravette.com/money?format=rss",
]

# Fallback flagship list if API unavailable
DEFAULT_REPOS = [
    ("pe-operating-kit", "Templates PE operators and CEOs actually use — 100-day plans, board/LP updates, diligence"),
    ("operator-playbook", "Practical checklists for operators shipping companies"),
    ("launch-checklist", "Distribution and launch playbook for founders and portfolio teams"),
]

MAX_POSTS = 5


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "paulgravette-profile-readme/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_rss(data: bytes) -> list[tuple[datetime, str, str]]:
    root = ET.fromstring(data)
    items: list[tuple[datetime, str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        try:
            # RFC 2822-ish
            dt = datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            dt = datetime.now(timezone.utc)
        items.append((dt, title, link))
    return items


def latest_posts() -> list[tuple[str, str]]:
    all_items: list[tuple[datetime, str, str]] = []
    seen: set[str] = set()
    for feed in RSS_FEEDS:
        try:
            for dt, title, link in parse_rss(fetch(feed)):
                if link in seen:
                    continue
                seen.add(link)
                all_items.append((dt, title, link))
        except Exception as e:
            print(f"warn: feed {feed}: {e}")
    all_items.sort(key=lambda x: x[0], reverse=True)
    return [(t, u) for _, t, u in all_items[:MAX_POSTS]]


def flagship_repos() -> list[tuple[str, str]]:
    token = os.environ.get("GITHUB_TOKEN", "")
    owner = "paul-gravette"
    # Prefer explicit pin list file if present
    pin_file = ROOT / "pinned-repos.txt"
    if pin_file.exists():
        lines = [ln.strip() for ln in pin_file.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        out: list[tuple[str, str]] = []
        for line in lines:
            if "|" in line:
                name, desc = line.split("|", 1)
                out.append((name.strip(), desc.strip()))
            else:
                out.append((line, ""))
        if out:
            return out
    # Else try GitHub API for public repos (non-fork, recently pushed)
    try:
        import json

        req = urllib.request.Request(
            f"https://api.github.com/users/{owner}/repos?sort=updated&per_page=10",
            headers={
                "User-Agent": "paulgravette-profile-readme/1.0",
                "Accept": "application/vnd.github+json",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            repos = json.loads(resp.read().decode())
        out = []
        for r in repos:
            if r.get("fork") or r.get("name") == owner:
                continue
            if r.get("private"):
                continue
            out.append((r["name"], (r.get("description") or "").strip()))
            if len(out) >= 4:
                break
        return out or DEFAULT_REPOS
    except Exception as e:
        print(f"warn: repos api: {e}")
        return DEFAULT_REPOS


def replace_block(text: str, name: str, body: str) -> str:
    pattern = rf"(<!--{name}:START-->)(.*?)(<!--{name}:END-->)"
    return re.sub(pattern, rf"\1\n{body}\n\3", text, flags=re.S)


def main() -> None:
    readme = README.read_text(encoding="utf-8")
    focus = FOCUS_FILE.read_text(encoding="utf-8").strip() if FOCUS_FILE.exists() else ""
    posts = latest_posts()
    repos = flagship_repos()

    posts_md = "\n".join(f"- [{t}]({u})" for t, u in posts) if posts else "_No posts found._"
    repos_md = "\n".join(
        f"- **[{name}](https://github.com/paul-gravette/{name})** — {desc}" if desc else f"- **[{name}](https://github.com/paul-gravette/{name})**"
        for name, desc in repos
    )

    readme = replace_block(readme, "FOCUS", focus)
    readme = replace_block(readme, "POSTS", posts_md)
    readme = replace_block(readme, "REPOS", repos_md)
    README.write_text(readme, encoding="utf-8")
    print(f"Updated README: {len(posts)} posts, {len(repos)} repos, focus={focus!r}")


if __name__ == "__main__":
    main()
