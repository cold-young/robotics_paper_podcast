"""
Dexterous Manipulation Daily Podcast Pipeline
==============================================
arXiv papers (robotics_paper_daily) -> Korean podcast -> GitHub Pages

Usage:
    python -m pipeline.main                    # Latest available batch
    python -m pipeline.main --date 2026-03-10  # Specific publish date
    python -m pipeline.main --dry-run          # Script only (skip TTS)
    python -m pipeline.main --force            # Rebuild even if already published

Notes:
    - The episode is keyed on the papers' actual arXiv *publish date*, NOT the
      day the Action happens to run. arXiv publish dates lag the calendar day by
      1-3 days, so matching "today" used to skip the podcast on most days.
    - Telegram notifications scan a rolling lookback window of upstream commits
      (see fetch_recently_added_papers) instead of a single calendar day, which
      is robust to the gap between the Action run time and upstream commit times.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.fetch_papers import (
    fetch_latest_dexterous_papers,
    fetch_recently_added_papers,
)
from pipeline.generate_script import generate_podcast_script
from pipeline.synthesize_audio import synthesize_podcast
from pipeline.build_site import build_site
from pipeline.send_telegram import send_paper_updates


def _already_published(episode_date: str, site_dir: str) -> bool:
    """Return True if an episode for episode_date already exists in the site."""
    episodes_json = Path(site_dir) / "episodes.json"
    try:
        episodes = json.loads(episodes_json.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    if isinstance(episodes, dict):  # tolerate {"episodes": [...]} shape
        episodes = episodes.get("episodes", [])
    return any(ep.get("date") == episode_date for ep in episodes)


def main():
    parser = argparse.ArgumentParser(description="Dexterous Manipulation Daily Podcast")
    parser.add_argument("--date", type=str, default=None,
                        help="Target publish date (YYYY-MM-DD). Omit to use the latest available batch.")
    parser.add_argument("--dry-run", action="store_true", help="Generate script only, skip TTS")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if an episode for this date already exists")
    parser.add_argument("--output-dir", type=str, default="output", help="Output directory")
    parser.add_argument("--site-dir", type=str, default="site", help="GitHub Pages site directory")
    parser.add_argument("--max-papers", type=int, default=5, help="Max papers per episode")
    parser.add_argument("--telegram-max-papers", type=int, default=10, help="Max papers per Telegram update")
    parser.add_argument("--telegram-lookback-hours", type=int, default=48,
                        help="How far back to scan upstream commits for newly-added papers")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram notification")
    args = parser.parse_args()

    # run_date is only a label (header text + Telegram message date); it never
    # gates which papers are selected.
    run_date = args.date or datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"  Dexterous Manipulation Daily Podcast")
    print(f"  Run date (KST): {run_date}")
    print(f"{'='*60}\n")

    # ── Step 1: Fetch papers ──
    print("[1/5] Fetching latest Dexterous papers...")
    # target_date=None -> newest available batch; an explicit --date selects that
    # date. allow_fallback tolerates the publish-date lag (today rarely equals the
    # newest publish date).
    papers = fetch_latest_dexterous_papers(
        target_date=args.date,
        max_papers=args.max_papers,
        allow_fallback=True,
    )

    if not papers:
        print("  ! No Dexterous papers found. Skipping podcast.")
        _run_telegram(args, run_date)
        return

    # The episode is keyed on the actual publish date of the batch.
    episode_date = papers[0]["date"]
    print(f"  + Found {len(papers)} papers (publish date: {episode_date})\n")
    for i, p in enumerate(papers, 1):
        print(f"    {i}. {p['title'][:70]}...")

    # Skip regeneration if this batch was already published (auto mode only,
    # unless --force). build_site dedupes the list, but this also avoids paying
    # for redundant LLM + TTS calls every run.
    if not args.force and args.date is None and _already_published(episode_date, args.site_dir):
        print(f"\n  Latest batch ({episode_date}) already published. Skipping podcast generation.")
        _run_telegram(args, run_date)
        return

    # ── Step 2: Generate podcast script ──
    print(f"\n[2/5] Generating Korean podcast script...")
    script = generate_podcast_script(papers, episode_date)

    script_path = output_dir / f"script_{episode_date}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"  + Script saved to {script_path}")

    if args.dry_run:
        print("\n[DRY RUN] Skipping TTS and site build.")
        print("\n--- Script Preview ---")
        for turn in script["dialogue"][:6]:
            print(f"  [{turn['speaker']}] {turn['text'][:80]}...")
        # Still send Telegram even in dry-run (unless --no-telegram)
        _run_telegram(args, run_date)
        return

    # ── Steps 3-4: Podcast generation (may fail independently of Telegram) ──
    podcast_error = None
    try:
        # ── Step 3: Synthesize audio ──
        print(f"\n[3/5] Synthesizing audio with Gemini TTS...")
        audio_path = output_dir / f"episode_{episode_date}.mp3"
        synthesize_podcast(script, str(audio_path))
        print(f"  + Audio saved to {audio_path}")

        # ── Step 4: Build site ──
        print(f"\n[4/5] Building podcast site...")
        episode_meta = {
            "date": episode_date,
            "title": script["title"],
            "description": script["description"],
            "papers": [{"title": p["title"], "url": p["url"]} for p in papers],
            "audio_file": f"episodes/episode_{episode_date}.mp3",
            "duration": script.get("estimated_duration", "5-10 min"),
        }
        build_site(episode_meta, args.site_dir, str(audio_path))
        print(f"  + Site updated at {args.site_dir}/")

        print(f"\n  Podcast pipeline complete!")
        print(f"  Audio: {audio_path}")
        print(f"  Site:  {args.site_dir}/index.html")

    except Exception as e:
        podcast_error = e
        print(f"\n  ⚠ Podcast generation failed: {e}")
        print(f"  Continuing to Telegram notification...\n")

    # ── Step 5: Telegram notification (always runs) ──
    _run_telegram(args, run_date)

    # Re-raise podcast error so GitHub Actions marks the job as failed
    if podcast_error:
        raise podcast_error


def _run_telegram(args, label_date: str):
    """Run Telegram notification step.

    Uses a rolling lookback window of upstream commits rather than a single
    calendar day, so it tolerates the lag between the Action run time and the
    upstream repo's daily commits. Duplicate sends are prevented downstream by
    output/sent_papers.json.
    """
    if args.no_telegram:
        print("\n[5/5] Telegram notification skipped (--no-telegram)")
        return

    print(f"\n[5/5] Sending Telegram notifications...")
    try:
        tg_papers = fetch_recently_added_papers(
            lookback_hours=args.telegram_lookback_hours,
            max_papers=args.telegram_max_papers,
        )
        send_paper_updates(tg_papers, label_date, max_papers=args.telegram_max_papers)
    except Exception as e:
        print(f"  ⚠ Telegram notification failed: {e}")


if __name__ == "__main__":
    main()
