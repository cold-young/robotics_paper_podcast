"""
Dexterous Manipulation Daily Podcast Pipeline
==============================================
arXiv 논문 (robotics_paper_daily) → 한국어 팟캐스트 → GitHub Pages

Usage:
    python -m pipeline.main                    # 오늘 날짜 기준 실행
    python -m pipeline.main --date 2026-03-10  # 특정 날짜 실행
    python -m pipeline.main --dry-run          # 스크립트만 생성 (TTS 생략)
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from pipeline.fetch_papers import fetch_latest_dexterous_papers
from pipeline.generate_script import generate_podcast_script
from pipeline.synthesize_audio import synthesize_podcast
from pipeline.build_site import build_site


def main():
    parser = argparse.ArgumentParser(description="Dexterous Manipulation Daily Podcast")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Generate script only, skip TTS")
    parser.add_argument("--output-dir", type=str, default="output", help="Output directory")
    parser.add_argument("--site-dir", type=str, default="site", help="GitHub Pages site directory")
    parser.add_argument("--max-papers", type=int, default=5, help="Max papers per episode")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"  Dexterous Manipulation Daily Podcast")
    print(f"  Date: {target_date}")
    print(f"{'='*60}\n")

    # ── Step 1: 논문 수집 ──
    print("[1/4] Fetching latest Dexterous papers...")
    papers = fetch_latest_dexterous_papers(target_date=target_date, max_papers=args.max_papers)

    if not papers:
        print("  ⚠ No papers found for this date. Exiting.")
        return

    print(f"  ✓ Found {len(papers)} papers\n")
    for i, p in enumerate(papers, 1):
        print(f"    {i}. {p['title'][:70]}...")

    # ── Step 2: 팟캐스트 스크립트 생성 ──
    print(f"\n[2/4] Generating Korean podcast script...")
    script = generate_podcast_script(papers, target_date)

    script_path = output_dir / f"script_{target_date}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Script saved to {script_path}")

    if args.dry_run:
        print("\n[DRY RUN] Skipping TTS and site build.")
        print("\n--- Script Preview ---")
        for turn in script["dialogue"][:6]:
            print(f"  [{turn['speaker']}] {turn['text'][:80]}...")
        return

    # ── Step 3: 음성 합성 ──
    print(f"\n[3/4] Synthesizing audio with MeloTTS (Korean)...")
    audio_path = output_dir / f"episode_{target_date}.mp3"
    synthesize_podcast(script, str(audio_path))
    print(f"  ✓ Audio saved to {audio_path}")

    # ── Step 4: 사이트 빌드 ──
    print(f"\n[4/4] Building podcast site...")
    episode_meta = {
        "date": target_date,
        "title": script["title"],
        "description": script["description"],
        "papers": [{"title": p["title"], "url": p["url"]} for p in papers],
        "audio_file": f"episodes/episode_{target_date}.mp3",
        "duration": script.get("estimated_duration", "5-10분"),
    }
    build_site(episode_meta, args.site_dir, str(audio_path))
    print(f"  ✓ Site updated at {args.site_dir}/")

    print(f"\n{'='*60}")
    print(f"  ✅ Pipeline complete!")
    print(f"  Audio: {audio_path}")
    print(f"  Site:  {args.site_dir}/index.html")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
