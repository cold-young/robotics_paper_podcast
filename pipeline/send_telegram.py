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
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.generate_script import _call_llm


# ── Config ──────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()

# Tracks which papers have already been sent, to avoid duplicate notifications.
# This file must be committed back to the repo by the workflow to persist across runs.
SENT_STATE_PATH = os.environ.get("TELEGRAM_SENT_STATE", "output/sent_papers.json")

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


# ── Sent-state tracking (duplicate prevention) ───────────────────────────────

def _paper_key(paper: dict) -> str:
    """Stable unique key for a paper (arXiv URL, or title fallback)."""
    return paper.get("url") or paper.get("title", "")


def _load_sent_keys() -> set[str]:
    """Load the set of already-sent paper keys from disk."""
    try:
        with open(SENT_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("sent_keys", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_sent_keys(keys: set[str]) -> None:
    """Persist the set of sent paper keys to disk (keeps most recent 2000)."""
    os.makedirs(os.path.dirname(SENT_STATE_PATH) or ".", exist_ok=True)
    # Cap the list so the file doesn't grow forever
    trimmed = list(keys)[-2000:]
    with open(SENT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"sent_keys": trimmed}, f, ensure_ascii=False, indent=2)


# ── Public API ───────────────────────────────────────────────────────────────

def send_paper_updates(
    papers: list[dict],
    target_date: str,
    dry_run: bool = False,
    max_papers: int = 10,
) -> bool:
    """
    Send paper TL;DR summaries to Telegram.

    Args:
        papers: list of paper dicts (from fetch_papers)
        target_date: date string for the header
        dry_run: if True, print to console instead of sending
        max_papers: maximum number of new papers to send

    Returns:
        True if successful (or dry_run)
    """
    if not papers:
        # arxiv가 멈췄거나 새 논문이 없는 경우: 조용히 종료 (매일 "없음" 스팸 방지)
        print(f"  No papers for {target_date}. Nothing to send.")
        return True

    # ── 중복 방지: 이미 보낸 논문 제외 ──
    sent_keys = _load_sent_keys()
    new_papers = [p for p in papers if _paper_key(p) not in sent_keys]

    if not new_papers:
        print(f"  All {len(papers)} papers for {target_date} were already sent. Skipping.")
        return True

    if len(new_papers) < len(papers):
        print(f"  {len(papers) - len(new_papers)}편은 이미 전송됨 → 신규 {len(new_papers)}편만 전송")

    papers = new_papers[:max_papers]

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

    # 전송 성공한 논문을 sent 상태에 기록
    sent_keys.update(_paper_key(p) for p in papers)
    _save_sent_keys(sent_keys)

    print(f"  + Telegram: {len(papers)}편 전송 완료")
    return True


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from pipeline.fetch_papers import fetch_papers_updated_on

    parser = argparse.ArgumentParser(description="Send paper updates to Telegram")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print to console only")
    parser.add_argument("--max-papers", type=int, default=10, help="Max papers to send")
    parser.add_argument(
        "--sections", type=str, nargs="*", default=None,
        help="Sections to include (default: all robotics sections)",
    )
    args = parser.parse_args()

    target_date = args.date or datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")

    print("Fetching papers...")
    papers = fetch_papers_updated_on(
        updated_date=target_date,
        sections=args.sections,
        max_papers=args.max_papers,
    )

    print(f"Found {len(papers)} papers updated on {target_date}")

    send_paper_updates(papers, target_date, dry_run=args.dry_run, max_papers=args.max_papers)
