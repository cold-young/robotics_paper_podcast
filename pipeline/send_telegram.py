"""
Telegram Notification Module
=============================
Sends paper TL;DR summaries to Telegram after the podcast pipeline runs.
Reuses fetch_papers for data and the LLM config from generate_script for summaries.

Environment variables:
    TELEGRAM_BOT_TOKEN  - BotFather token
    TELEGRAM_CHAT_ID    - Target chat / channel ID
    LLM_API_KEY         - (shared with generate_script) for TL;DR generation
    LLM_BASE_URL        - (shared with generate_script)
    LLM_MODEL           - (shared with generate_script)

Usage:
    # As part of the pipeline (called from main.py)
    from pipeline.send_telegram import send_paper_updates
    send_paper_updates(papers, target_date)

    # Standalone
    python -m pipeline.send_telegram
    python -m pipeline.send_telegram --date 2026-05-14
    python -m pipeline.send_telegram --dry-run
"""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional

from pipeline.generate_script import _call_llm


# ── Config ──────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()

TLDR_SYSTEM_PROMPT = """\
당신은 로보틱스 분야 전문 연구원입니다.
주어진 논문 제목과 초록을 읽고, 한국어로 2~3문장의 TL;DR 요약을 작성하세요.
- 핵심 기여(contribution)와 성능 결과를 포함
- 전문 용어는 영어 그대로 유지 (예: dexterous manipulation, sim-to-real)
- 번역체가 아닌 자연스러운 한국어로 작성
- Markdown이나 특수 포맷 없이 plain text로 작성
"""


# ── TL;DR Generation ────────────────────────────────────────────────────────

def generate_tldr(paper: dict) -> str:
    """Generate a Korean TL;DR summary for a single paper using the shared LLM."""
    if not LLM_API_KEY:
        return paper["abstract"][:200] + "..."

    user_msg = f"제목: {paper['title']}\n\n초록: {paper['abstract']}"
    try:
        raw = _call_llm(TLDR_SYSTEM_PROMPT, user_msg)
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        return raw.strip()
    except Exception as e:
        print(f"    ! TL;DR failed ({paper['title'][:40]}): {e}")
        return paper["abstract"][:200] + "..."


def enrich_with_tldr(papers: list[dict]) -> list[dict]:
    """Add a 'tldr_ko' key to each paper dict."""
    for i, paper in enumerate(papers):
        print(f"    [{i+1}/{len(papers)}] {paper['title'][:50]}...")
        paper["tldr_ko"] = generate_tldr(paper)
        time.sleep(0.3)
    return papers


# ── Telegram Sending ────────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    """Escape special chars for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _send_message(text: str) -> bool:
    """Send a single message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"    ! Telegram send failed: {e}")
        return False


def _format_header(date_str: str, count: int) -> str:
    return (
        f"🤖 <b>Robotics Paper Daily</b>\n"
        f"📅 {date_str}  |  📝 {count}편 업데이트\n"
        f"{'─' * 25}"
    )


def _format_paper(paper: dict, idx: int, total: int) -> str:
    title = _escape_html(paper["title"])
    authors = _escape_html(paper["authors"])
    tldr = _escape_html(paper.get("tldr_ko", paper["abstract"][:200]))

    tag_str = " ".join(f"#{t}" for t in paper.get("tags", []))

    links = ""
    if paper.get("url"):
        links = f'<a href="{paper["url"]}">📄 arXiv</a>'
    if paper.get("web"):
        links += f' | <a href="{paper["web"]}">🌐 Project</a>'

    msg = (
        f"[{idx}/{total}] <b>{title}</b>\n"
        f"👥 {authors}\n"
    )
    if tag_str:
        msg += f"{tag_str}\n"
    msg += f"{links}\n\n💡 <b>TL;DR</b>\n{tldr}"
    return msg


# ── Public API ───────────────────────────────────────────────────────────────

def send_paper_updates(
    papers: list[dict],
    target_date: str,
    dry_run: bool = False,
) -> bool:
    """
    Send paper TL;DR summaries to Telegram.

    Args:
        papers: list of paper dicts (from fetch_papers)
        target_date: date string for the header
        dry_run: if True, print to console instead of sending

    Returns:
        True if successful (or dry_run)
    """
    if not papers:
        msg = f"📅 {target_date}: 오늘 업데이트된 논문이 없습니다."
        if dry_run:
            print(msg)
        else:
            _send_message(msg)
        return True

    # Generate TL;DR for each paper
    print("  Generating TL;DR summaries...")
    enrich_with_tldr(papers)

    if dry_run:
        print(f"\n{'='*60}")
        print(_format_header(target_date, len(papers)))
        print(f"{'='*60}\n")
        for i, p in enumerate(papers, 1):
            print(_format_paper(p, i, len(papers)))
            print(f"\n{'─'*40}\n")
        return True

    # Validate credentials
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set. Skipping.")
        return False

    # Send header
    _send_message(_format_header(target_date, len(papers)))
    time.sleep(0.3)

    # Send each paper
    for i, paper in enumerate(papers, 1):
        msg = _format_paper(paper, i, len(papers))
        if len(msg) > 4000:
            msg = msg[:3997] + "..."
        _send_message(msg)
        time.sleep(0.3)

    print(f"  + Telegram: {len(papers)}편 전송 완료")
    return True


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from pipeline.fetch_papers import fetch_latest_papers

    parser = argparse.ArgumentParser(description="Send paper updates to Telegram")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print to console only")
    parser.add_argument(
        "--sections", type=str, nargs="*", default=None,
        help="Sections to include (default: all robotics sections)",
    )
    args = parser.parse_args()

    print("Fetching papers...")
    papers = fetch_latest_papers(target_date=args.date, sections=args.sections)

    actual_date = papers[0]["date"] if papers else (args.date or "N/A")
    print(f"Found {len(papers)} papers for {actual_date}")

    send_paper_updates(papers, actual_date, dry_run=args.dry_run)