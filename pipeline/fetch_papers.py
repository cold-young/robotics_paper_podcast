"""
Paper Fetcher Module
====================
Parses the README.md from cold-young/robotics_paper_daily
and extracts the latest papers from the Dexterous section.
"""

import re
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo


REPO_OWNER = "cold-young"
REPO_NAME = "robotics_paper_daily"
REPO_BRANCH = "main"
README_PATH = "README.md"
REPO_RAW_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}/{README_PATH}"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def fetch_readme(ref: str = REPO_BRANCH) -> str:
    """Fetch README.md from GitHub raw URL."""
    url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{ref}/{README_PATH}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _fetch_json(url: str) -> object:
    """Fetch JSON from the GitHub API."""
    headers = {
        "User-Agent": "robotics-paper-podcast",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_links(links_raw: str) -> tuple[str, str, list[dict]]:
    """Extract Markdown links while preserving labels such as ArXiv/OpenReview."""
    links = [
        {"label": label.strip(), "url": url.strip()}
        for label, url in re.findall(r"\[([^\]]+)\]\((http[^)]+)\)", links_raw)
    ]

    arxiv_url = ""
    web_url = ""
    for link in links:
        label = link["label"].lower()
        if not arxiv_url and "arxiv" in label:
            arxiv_url = link["url"]
        elif not web_url and any(word in label for word in ("web", "project", "github", "code", "openreview")):
            web_url = link["url"]

    primary_url = arxiv_url or (links[0]["url"] if links else "")
    return primary_url, web_url, links


def parse_dexterous_section(readme: str) -> list[dict]:
    """
    Parse the paper table from the Dexterous section.

    Returns:
        list of dict with keys: date, title, abstract, authors, url, web
    """
    # Extract Dexterous section (## Dexterous ~ next ## section)
    dex_match = re.search(
        r"## Dexterous\b.*?\n(.*?)(?=\n## (?:Manipulation|VLA|$))",
        readme,
        re.DOTALL,
    )
    if not dex_match:
        return []

    section = dex_match.group(1)

    # Format A (current): <details> tag + backtick tags
    row_pattern_details = re.compile(
        r"\|\s*\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\|"                     # date
        r"\s*\*\*(.*?)\*\*"                                            # title
        r"((?:\s*`[^`]+`)*)"                                           # tags (optional)
        r"\s*<details><summary>Abstract</summary>(.*?)</details>"      # abstract
        r"\s*\|\s*(.*?)\s*\|"                                          # authors
        r"\s*(.*?)\s*\|",                                              # links
        re.DOTALL,
    )

    # Format B (legacy): inline Abstract
    row_pattern_inline = re.compile(
        r"\|\s*\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\|"   # date
        r"\s*\*\*(.*?)\*\*"                           # title
        r"\s*Abstract:\s*(.*?)\s*\|"                  # abstract (inline)
        r"\s*(.*?)\s*\|"                              # authors
        r"\s*(.*?)\s*\|",                             # links
        re.DOTALL,
    )

    papers = []

    # Try format A first
    for m in row_pattern_details.finditer(section):
        date_str = m.group(1).strip()
        title = m.group(2).strip()
        tags = [t.strip("` ") for t in re.findall(r"`([^`]+)`", m.group(3))]
        abstract = m.group(4).strip()
        authors = m.group(5).strip()
        links_raw = m.group(6).strip()

        # Clean abstract
        abstract = re.sub(r"<[^>]+>", "", abstract)
        abstract = re.sub(r"\s+", " ", abstract).strip()

        primary_url, web_url, links = _extract_links(links_raw)

        papers.append({
            "date": date_str,
            "title": title,
            "tags": tags,
            "abstract": abstract,
            "authors": authors,
            "url": primary_url,
            "web": web_url,
            "links": links,
        })

    # Fall back to format B if no results
    if not papers:
        for m in row_pattern_inline.finditer(section):
            date_str = m.group(1).strip()
            title = m.group(2).strip()
            abstract = m.group(3).strip()
            authors = m.group(4).strip()
            links_raw = m.group(5).strip()

            abstract = re.sub(r"<[^>]+>", "", abstract)
            abstract = re.sub(r"\s+", " ", abstract).strip()

            primary_url, web_url, links = _extract_links(links_raw)

            papers.append({
                "date": date_str,
                "title": title,
                "tags": [],
                "abstract": abstract,
                "authors": authors,
                "url": primary_url,
                "web": web_url,
                "links": links,
            })

    return papers


def fetch_latest_dexterous_papers(
    target_date: Optional[str] = None,
    max_papers: int = 5,
    allow_fallback: bool = True,
) -> list[dict]:
    """
    Return papers from the Dexterous section for a specific date (or most recent).

    Args:
        target_date: "YYYY-MM-DD" format. None uses the most recent date.
        max_papers: Maximum number of papers to return.
        allow_fallback: If True, use the most recent earlier date when the
            target date has no papers.

    Returns:
        list of paper dicts
    """
    readme = fetch_readme()
    all_papers = parse_dexterous_section(readme)

    if not all_papers:
        return []

    if target_date:
        # Filter by target date
        filtered = [p for p in all_papers if p["date"] == target_date]
        if filtered:
            return filtered[:max_papers]

        if allow_fallback:
            # If no papers on target date, use most recent before it
            earlier = [p for p in all_papers if p["date"] <= target_date]
            if earlier:
                latest_date = max(p["date"] for p in earlier)
                return [p for p in earlier if p["date"] == latest_date][:max_papers]
        return []

    # If target_date is None, use most recent date
    latest_date = max(p["date"] for p in all_papers)
    return [p for p in all_papers if p["date"] == latest_date][:max_papers]


# ── Multi-section parsing (used by send_telegram) ──────────────────────────

# Robotics-relevant sections (excludes HuggingFace Hot Papers)
ROBOTICS_SECTIONS = ["Dexterous", "Manipulation", "VLA", "Tactile", "Sim2Real", "LearnedControl"]


def _parse_paper_row(line: str, section: str = "") -> Optional[dict]:
    """Parse one README table row into a paper dict."""
    date_match = re.search(r"\*\*(\d{4}-\d{2}-\d{2})\*\*", line)
    if not date_match or "<details>" not in line:
        return None

    date_str = date_match.group(1)

    title = ""
    for item in re.findall(r"\*\*([^*]+)\*\*", line):
        if not re.match(r"\d{4}-\d{2}-\d{2}", item):
            title = item.strip()
            break

    tags = re.findall(r"`(\w+)`", line)

    abstract = ""
    det_match = re.search(
        r"<details><summary>Abstract</summary>(.*?)</details>", line, re.DOTALL
    )
    if det_match:
        abstract = det_match.group(1).strip()
        abstract = re.sub(r"<[^>]+>", "", abstract)
        abstract = re.sub(r"\s+", " ", abstract).strip()

    after_details = line.split("</details>")[-1] if "</details>" in line else ""
    after_parts = [p.strip() for p in after_details.split("|") if p.strip()]
    authors = after_parts[0] if len(after_parts) > 0 else ""
    links_raw = after_parts[1] if len(after_parts) > 1 else ""

    primary_url, web_url, links = _extract_links(links_raw)

    return {
        "date": date_str,
        "title": title,
        "tags": tags,
        "abstract": abstract,
        "authors": authors,
        "url": primary_url,
        "web": web_url,
        "links": links,
        "section": section,
    }


def parse_all_sections(readme: str) -> list[dict]:
    """
    Parse paper rows from ALL sections of the README.

    Unlike parse_dexterous_section(), this scans every line and records
    which '## Section' header it falls under, plus any inline backtick tags.

    Returns:
        list of dict with keys: date, title, abstract, authors, url, web, tags, section
    """
    papers = []
    current_section = ""

    for line in readme.split("\n"):
        # Detect section headers (## Dexterous, ## 🔥 HuggingFace Hot Papers, etc.)
        sec_match = re.match(r"^##\s+(.+)$", line.strip())
        if sec_match:
            current_section = sec_match.group(1).strip()
            continue

        paper = _parse_paper_row(line, current_section)
        if paper:
            papers.append(paper)

    return papers


def fetch_latest_papers(
    target_date: Optional[str] = None,
    sections: Optional[list[str]] = None,
    max_papers: int = 10,
    allow_fallback: bool = True,
) -> list[dict]:
    """
    Return papers from specified sections for a given date (or most recent).

    Unlike fetch_latest_dexterous_papers(), this supports multiple sections
    and deduplicates papers that appear in more than one section.

    Args:
        target_date: "YYYY-MM-DD" format. None → auto-detect most recent date.
        sections: List of section names to include (default: ROBOTICS_SECTIONS).
        max_papers: Maximum number of papers to return.
        allow_fallback: If True, use the most recent earlier date when the
            target date has no papers.

    Returns:
        list of paper dicts (deduplicated by arXiv URL)
    """
    if sections is None:
        sections = ROBOTICS_SECTIONS

    readme = fetch_readme()
    all_papers = parse_all_sections(readme)

    if not all_papers:
        return []

    # Section filter
    allowed = {s.lower() for s in sections}
    filtered = [
        p for p in all_papers
        if any(a in p["section"].lower() for a in allowed)
    ]

    if not filtered:
        return []

    # Date filter
    if target_date:
        dated = [p for p in filtered if p["date"] == target_date]
        if not dated:
            if allow_fallback:
                # Fall back to most recent date ≤ target_date
                earlier = [p for p in filtered if p["date"] <= target_date]
                if earlier:
                    latest_date = max(p["date"] for p in earlier)
                    dated = [p for p in earlier if p["date"] == latest_date]
                else:
                    return []
            else:
                return []
    else:
        latest_date = max(p["date"] for p in filtered)
        dated = [p for p in filtered if p["date"] == latest_date]

    # Deduplicate by arXiv URL (same paper can appear in multiple sections)
    seen = set()
    unique = []
    for p in dated:
        key = p["url"] or p["title"]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique[:max_papers]


def _paper_key(paper: dict) -> str:
    """Stable key for matching papers across README revisions."""
    return paper.get("url") or paper.get("title", "")


def _filter_sections(papers: list[dict], sections: Optional[list[str]]) -> list[dict]:
    """Filter papers to the requested README sections."""
    if sections is None:
        sections = ROBOTICS_SECTIONS

    allowed = {s.lower() for s in sections}
    return [
        p for p in papers
        if any(a in p.get("section", "").lower() for a in allowed)
    ]


def _dedupe_papers(papers: list[dict]) -> list[dict]:
    """Deduplicate papers while preserving order."""
    seen = set()
    unique = []
    for paper in papers:
        key = _paper_key(paper)
        if key and key not in seen:
            seen.add(key)
            unique.append(paper)
    return unique


def _day_bounds_utc(date_str: str, timezone_name: str) -> tuple[str, str]:
    """Return ISO UTC start/end timestamps for a local date."""
    tz = ZoneInfo(timezone_name)
    start_local = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end_utc = end_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return start_utc, end_utc


def _fetch_readme_commits(since: Optional[str] = None, until: Optional[str] = None, per_page: int = 100) -> list[dict]:
    """Fetch commits that touched README.md."""
    params = {"path": README_PATH, "per_page": str(per_page)}
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    url = f"{GITHUB_API_URL}/commits?{urlencode(params)}"
    data = _fetch_json(url)
    if isinstance(data, list):
        return data
    return []


def _fetch_commit(sha: str) -> dict:
    """Fetch one commit object from the GitHub API."""
    data = _fetch_json(f"{GITHUB_API_URL}/commits/{sha}")
    if isinstance(data, dict):
        return data
    return {}


def fetch_papers_updated_on(
    updated_date: str,
    sections: Optional[list[str]] = None,
    max_papers: int = 10,
    timezone_name: str = "Asia/Seoul",
) -> list[dict]:
    """
    Return papers added to robotics_paper_daily README during a local calendar day.

    This uses GitHub commit timestamps for README.md, then compares each README
    revision against its parent commit. Paper dates may be older than updated_date;
    updated_date describes when the upstream repo added them.
    """
    start_utc, end_utc = _day_bounds_utc(updated_date, timezone_name)
    todays_commits = _fetch_readme_commits(since=start_utc, until=end_utc)
    if not todays_commits:
        return []

    added_papers = []
    seen_added = set()

    for commit in reversed(todays_commits):
        commit_sha = commit["sha"]
        commit_data = _fetch_commit(commit_sha)
        parent_sha = ""
        parents = commit_data.get("parents", [])
        if parents:
            parent_sha = parents[0].get("sha", "")

        after_papers = _dedupe_papers(
            _filter_sections(parse_all_sections(fetch_readme(ref=commit_sha)), sections)
        )
        if parent_sha:
            before_papers = _dedupe_papers(
                _filter_sections(parse_all_sections(fetch_readme(ref=parent_sha)), sections)
            )
            before_keys = {_paper_key(p) for p in before_papers}
        else:
            before_keys = set()

        for paper in after_papers:
            key = _paper_key(paper)
            if key and key not in before_keys and key not in seen_added:
                seen_added.add(key)
                added_papers.append(paper)
                if len(added_papers) >= max_papers:
                    return added_papers

    return added_papers


# ── CLI test ──
if __name__ == "__main__":
    import sys

    if "--all" in sys.argv:
        papers = fetch_latest_papers()
        label = "All sections"
    else:
        papers = fetch_latest_dexterous_papers()
        label = "Dexterous only"

    print(f"[{label}] Found {len(papers)} papers "
          f"(date: {papers[0]['date'] if papers else 'N/A'})\n")
    for i, p in enumerate(papers, 1):
        print(f"{i}. [{p['date']}] {p['title']}")
        print(f"   Tags: {p.get('tags', [])}  Section: {p.get('section', '')}")
        print(f"   Authors: {p['authors']}")
        print(f"   URL: {p['url']}")
        print(f"   Abstract: {p['abstract'][:150]}...\n")
