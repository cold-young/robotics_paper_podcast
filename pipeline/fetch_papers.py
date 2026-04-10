"""
Paper Fetcher Module
====================
Parses the README.md from cold-young/robotics_paper_daily
and extracts the latest papers from the Dexterous section.
"""

import re
import urllib.request
from typing import Optional


REPO_RAW_URL = (
    "https://raw.githubusercontent.com/cold-young/robotics_paper_daily/main/README.md"
)


def fetch_readme() -> str:
    """Fetch README.md from GitHub raw URL."""
    req = urllib.request.Request(REPO_RAW_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


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

        arxiv_match = re.search(r"\[ArXiv\]\((http[^)]+)\)", links_raw)
        web_match = re.search(r"\[Web\]\((http[^)]+)\)", links_raw)

        papers.append({
            "date": date_str,
            "title": title,
            "tags": tags,
            "abstract": abstract,
            "authors": authors,
            "url": arxiv_match.group(1) if arxiv_match else "",
            "web": web_match.group(1) if web_match else "",
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

            arxiv_match = re.search(r"\[ArXiv\]\((http[^)]+)\)", links_raw)
            web_match = re.search(r"\[Web\]\((http[^)]+)\)", links_raw)

            papers.append({
                "date": date_str,
                "title": title,
                "tags": [],
                "abstract": abstract,
                "authors": authors,
                "url": arxiv_match.group(1) if arxiv_match else "",
                "web": web_match.group(1) if web_match else "",
            })

    return papers


def fetch_latest_dexterous_papers(
    target_date: Optional[str] = None,
    max_papers: int = 5,
) -> list[dict]:
    """
    Return papers from the Dexterous section for a specific date (or most recent).

    Args:
        target_date: "YYYY-MM-DD" format. None uses the most recent date.
        max_papers: Maximum number of papers to return.

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

        # If no papers on target date, use most recent before it
        earlier = [p for p in all_papers if p["date"] <= target_date]
        if earlier:
            latest_date = max(p["date"] for p in earlier)
            return [p for p in earlier if p["date"] == latest_date][:max_papers]

    # If target_date is None, use most recent date
    latest_date = max(p["date"] for p in all_papers)
    return [p for p in all_papers if p["date"] == latest_date][:max_papers]


# ── CLI test ──
if __name__ == "__main__":
    papers = fetch_latest_dexterous_papers()
    print(f"Found {len(papers)} papers (date: {papers[0]['date'] if papers else 'N/A'})\n")
    for i, p in enumerate(papers, 1):
        print(f"{i}. [{p['date']}] {p['title']}")
        print(f"   Tags: {p.get('tags', [])}")
        print(f"   Authors: {p['authors']}")
        print(f"   URL: {p['url']}")
        print(f"   Abstract: {p['abstract'][:150]}...\n")
