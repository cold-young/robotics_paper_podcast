"""
논문 수집 모듈
=============
cold-young/robotics_paper_daily 의 README.md를 파싱하여
Dexterous 섹션의 최신 논문을 추출합니다.
"""

import re
import urllib.request
from typing import Optional


REPO_RAW_URL = (
    "https://raw.githubusercontent.com/cold-young/robotics_paper_daily/main/README.md"
)


def fetch_readme() -> str:
    """GitHub Raw URL에서 README.md를 가져옵니다."""
    req = urllib.request.Request(REPO_RAW_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_dexterous_section(readme: str) -> list[dict]:
    """
    README.md에서 Dexterous 섹션의 논문 테이블을 파싱합니다.

    Returns:
        list of dict with keys: date, title, abstract, authors, url, web
    """
    # Dexterous 섹션 추출 (## Dexterous ~ 다음 ## 섹션 전까지)
    dex_match = re.search(
        r"## Dexterous\b.*?\n(.*?)(?=\n## (?:Manipulation|VLA|$))",
        readme,
        re.DOTALL,
    )
    if not dex_match:
        return []

    section = dex_match.group(1)

    # ── 포맷 A (현재): <details> 태그 + 백틱 태그 ──
    # | **날짜** | **제목** `tag` <details><summary>Abstract</summary>초록</details> | 저자 | 링크 |
    row_pattern_details = re.compile(
        r"\|\s*\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\|"                     # 날짜
        r"\s*\*\*(.*?)\*\*"                                            # 제목
        r"((?:\s*`[^`]+`)*)"                                           # 태그 (옵션)
        r"\s*<details><summary>Abstract</summary>(.*?)</details>"      # 초록 (details 태그)
        r"\s*\|\s*(.*?)\s*\|"                                          # 저자
        r"\s*(.*?)\s*\|",                                              # 링크
        re.DOTALL,
    )

    # ── 포맷 B (이전): Abstract: 인라인 ──
    # | **날짜** | **제목** Abstract: 초록 | 저자 | 링크 |
    row_pattern_inline = re.compile(
        r"\|\s*\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\|"   # 날짜
        r"\s*\*\*(.*?)\*\*"                           # 제목
        r"\s*Abstract:\s*(.*?)\s*\|"                  # 초록 (인라인)
        r"\s*(.*?)\s*\|"                              # 저자
        r"\s*(.*?)\s*\|",                             # 링크
        re.DOTALL,
    )

    papers = []

    # 포맷 A 먼저 시도
    for m in row_pattern_details.finditer(section):
        date_str = m.group(1).strip()
        title = m.group(2).strip()
        tags = [t.strip("` ") for t in re.findall(r"`([^`]+)`", m.group(3))]
        abstract = m.group(4).strip()
        authors = m.group(5).strip()
        links_raw = m.group(6).strip()

        # 초록 정리
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

    # 포맷 A에서 결과가 없으면 포맷 B 시도
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
    Dexterous 섹션에서 특정 날짜(또는 가장 최근 날짜)의 논문을 반환합니다.

    Args:
        target_date: "YYYY-MM-DD" 형식. None이면 가장 최근 날짜 사용.
        max_papers: 최대 논문 수.

    Returns:
        list of paper dicts
    """
    readme = fetch_readme()
    all_papers = parse_dexterous_section(readme)

    if not all_papers:
        return []

    if target_date:
        # 해당 날짜 논문 필터
        filtered = [p for p in all_papers if p["date"] == target_date]
        if filtered:
            return filtered[:max_papers]

        # 해당 날짜 논문이 없으면 → 해당 날짜 이전 가장 최근 논문
        earlier = [p for p in all_papers if p["date"] <= target_date]
        if earlier:
            latest_date = max(p["date"] for p in earlier)
            return [p for p in earlier if p["date"] == latest_date][:max_papers]

    # target_date가 None이면 가장 최근 날짜
    latest_date = max(p["date"] for p in all_papers)
    return [p for p in all_papers if p["date"] == latest_date][:max_papers]


# ── CLI 테스트 ──
if __name__ == "__main__":
    papers = fetch_latest_dexterous_papers()
    print(f"Found {len(papers)} papers (date: {papers[0]['date'] if papers else 'N/A'})\n")
    for i, p in enumerate(papers, 1):
        print(f"{i}. [{p['date']}] {p['title']}")
        print(f"   Tags: {p.get('tags', [])}")
        print(f"   Authors: {p['authors']}")
        print(f"   URL: {p['url']}")
        print(f"   Abstract: {p['abstract'][:150]}...\n")
