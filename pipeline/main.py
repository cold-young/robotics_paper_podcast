"""
Dexterous Manipulation Daily Podcast Pipeline
==============================================
arXiv papers (robotics_paper_daily) -> Korean podcast -> GitHub Pages

Usage:
    python -m pipeline.main                    # Run for today
    python -m pipeline.main --date 2026-03-10  # Run for specific date
    python -m pipeline.main --dry-run          # Script only (skip TTS)
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from pipeline.fetch_papers import fetch_latest_dexterous_papers, fetch_latest_papers
from pipeline.generate_script import generate_podcast_script
from pipeline.synthesize_audio import synthesize_podcast
from pipeline.build_site import build_site
from pipeline.send_telegram import send_paper_updates


def main():
    parser = argparse.ArgumentParser(description="Dexterous Manipulation Daily Podcast")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Generate script only, skip TTS")
    parser.add_argument("--output-dir", type=str, default="output", help="Output directory")
    parser.add_argument("--site-dir", type=str, default="site", help="GitHub Pages site directory")
    parser.add_argument("--max-papers", type=int, default=5, help="Max papers per episode")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram notification")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"  Dexterous Manipulation Daily Podcast")
    print(f"  Date: {target_date}")
    print(f"{'='*60}\n")

    # ── Step 1: Fetch papers ──
    print("[1/4] Fetching latest Dexterous papers...")
    papers = fetch_latest_dexterous_papers(target_date=target_date, max_papers=args.max_papers)

    if not papers:
        print("  ! No papers found for this date. Exiting.")
        return

    print(f"  + Found {len(papers)} papers\n")
    for i, p in enumerate(papers, 1):
        print(f"    {i}. {p['title'][:70]}...")

    # ── Step 2: Generate podcast script ──
    print(f"\n[2/4] Generating Korean podcast script...")
    script = generate_podcast_script(papers, target_date)

    script_path = output_dir / f"script_{target_date}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"  + Script saved to {script_path}")

    if args.dry_run:
        print("\n[DRY RUN] Skipping TTS and site build.")
        print("\n--- Script Preview ---")
        for turn in script["dialogue"][:6]:
            print(f"  [{turn['speaker']}] {turn['text'][:80]}...")
        return

    # ── Step 3: Synthesize audio ──
    print(f"\n[3/4] Synthesizing audio with Gemini TTS...")
    audio_path = output_dir / f"episode_{target_date}.mp3"
    synthesize_podcast(script, str(audio_path))
    print(f"  + Audio saved to {audio_path}")

    # ── Step 4: Build site ──
    print(f"\n[4/4] Building podcast site...")
    episode_meta = {
        "date": target_date,
        "title": script["title"],
        "description": script["description"],
        "papers": [{"title": p["title"], "url": p["url"]} for p in papers],
        "audio_file": f"episodes/episode_{target_date}.mp3",
        "duration": script.get("estimated_duration", "5-10 min"),
    }
    build_site(episode_meta, args.site_dir, str(audio_path))
    print(f"  + Site updated at {args.site_dir}/")

    print(f"\n{'='*60}")
    print(f"  Pipeline complete!")
    print(f"  Audio: {audio_path}")
    print(f"  Site:  {args.site_dir}/index.html")
    print(f"{'='*60}")

    # ── Step 5: Telegram notification ──
    if not args.no_telegram:
        print(f"\n[5/5] Sending Telegram notifications...")
        tg_papers = fetch_latest_papers(target_date=target_date)
        actual_date = tg_papers[0]["date"] if tg_papers else target_date
        send_paper_updates(tg_papers, actual_date)
    else:
        print("\n[5/5] Telegram notification skipped (--no-telegram)")


if __name__ == "__main__":
    main()