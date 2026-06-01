"""
Site Builder Module
===================
Generates/updates GitHub Pages HTML based on episode metadata.
"""

import json
import shutil
from pathlib import Path


EPISODES_JSON = "episodes.json"
MAX_EPISODES = 5


def _load_episodes(site_dir: str) -> list[dict]:
    """Load existing episode list."""
    path = Path(site_dir) / EPISODES_JSON
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_episodes(episodes: list[dict], site_dir: str):
    """Save episode list."""
    path = Path(site_dir) / EPISODES_JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)


def _episode_sort_key(episode: dict) -> str:
    """Sort episodes by date string, newest first."""
    return episode.get("date", "")


def _prune_audio_files(site_path: Path, kept_episodes: list[dict]) -> None:
    """Delete MP3 files that are no longer referenced by the kept episodes."""
    episodes_dir = site_path / "episodes"
    if not episodes_dir.exists():
        return

    kept_audio = {
        (site_path / ep["audio_file"]).resolve()
        for ep in kept_episodes
        if ep.get("audio_file")
    }

    for mp3_path in episodes_dir.glob("*.mp3"):
        if mp3_path.resolve() not in kept_audio:
            mp3_path.unlink()


def build_site(episode_meta: dict, site_dir: str, audio_src_path: str):
    """
    Add a new episode to the site.

    Args:
        episode_meta: Episode metadata dict
        site_dir: GitHub Pages root directory
        audio_src_path: Path to the synthesized MP3 file
    """
    site_path = Path(site_dir)
    episodes_dir = site_path / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    # Copy audio file
    audio_filename = f"episode_{episode_meta['date']}.mp3"
    audio_dest = episodes_dir / audio_filename
    shutil.copy2(audio_src_path, audio_dest)
    episode_meta["audio_file"] = f"episodes/{audio_filename}"

    # Update episode list (prevent duplicates), then keep the latest 5 days.
    episodes = _load_episodes(site_dir)
    episodes = [ep for ep in episodes if ep["date"] != episode_meta["date"]]
    episodes.insert(0, episode_meta)
    episodes = sorted(episodes, key=_episode_sort_key, reverse=True)[:MAX_EPISODES]
    _save_episodes(episodes, site_dir)
    _prune_audio_files(site_path, episodes)

    # Generate index.html
    _generate_index_html(site_path, episodes)


def _generate_index_html(site_path: Path, episodes: list[dict]):
    """Generate index.html."""
    html = f"""\
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dexterous Manipulation Daily Podcast</title>
  <style>
    :root {{
      --bg: #0f0f0f;
      --surface: #1a1a2e;
      --primary: #6c63ff;
      --primary-dim: #4a44b3;
      --text: #e0e0e0;
      --text-muted: #888;
      --border: #2a2a3e;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'Pretendard', -apple-system, 'Noto Sans KR', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    .container {{
      max-width: 720px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}
    header {{
      text-align: center;
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    header h1 {{
      font-size: 1.6rem;
      font-weight: 700;
      margin-bottom: 0.3rem;
      background: linear-gradient(135deg, #6c63ff, #48cfcb);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    header p {{
      color: var(--text-muted);
      font-size: 0.9rem;
    }}

    /* ── Player ── */
    .player {{
      background: var(--surface);
      border-radius: 16px;
      padding: 1.8rem;
      margin-bottom: 2rem;
      border: 1px solid var(--border);
    }}
    .player-title {{
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 0.3rem;
    }}
    .player-date {{
      color: var(--text-muted);
      font-size: 0.82rem;
      margin-bottom: 1rem;
    }}
    audio {{
      width: 100%;
      margin-bottom: 1rem;
      border-radius: 8px;
    }}
    audio::-webkit-media-controls-panel {{
      background: #222;
    }}

    /* ── Paper Links ── */
    .papers {{
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }}
    .papers a {{
      color: var(--primary);
      text-decoration: none;
      font-size: 0.85rem;
      padding: 0.3rem 0;
      transition: color 0.2s;
    }}
    .papers a:hover {{
      color: #48cfcb;
    }}

    /* ── Episode List ── */
    .episode-list {{
      list-style: none;
    }}
    .episode-list li {{
      padding: 1rem 0;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      transition: background 0.15s;
    }}
    .episode-list li:hover {{
      background: rgba(108, 99, 255, 0.06);
    }}
    .episode-list li.active {{
      border-left: 3px solid var(--primary);
      padding-left: 1rem;
    }}
    .ep-title {{
      font-weight: 600;
      font-size: 0.95rem;
      margin-bottom: 0.2rem;
    }}
    .ep-meta {{
      color: var(--text-muted);
      font-size: 0.8rem;
    }}
    h2 {{
      font-size: 1rem;
      font-weight: 600;
      margin-bottom: 1rem;
      color: var(--text-muted);
    }}
    footer {{
      text-align: center;
      margin-top: 3rem;
      color: var(--text-muted);
      font-size: 0.75rem;
    }}
    footer a {{ color: var(--primary); text-decoration: none; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Dexterous Manipulation Daily</h1>
      <p>AI-powered Korean podcast from arXiv papers</p>
    </header>

    <div class="player" id="player">
      <div class="player-title" id="player-title">Select an episode</div>
      <div class="player-date" id="player-date"></div>
      <audio controls id="audio-el">
        <source id="audio-src" src="" type="audio/mpeg">
      </audio>
      <div class="papers" id="paper-links"></div>
    </div>

    <h2>Episodes</h2>
    <ul class="episode-list" id="episode-list"></ul>

    <footer>
      Powered by <a href="https://github.com/cold-young/robotics_paper_daily">robotics_paper_daily</a>
      + Gemini TTS
    </footer>
  </div>

  <script>
    let episodes = [];

    async function loadEpisodes() {{
      const resp = await fetch('episodes.json');
      episodes = await resp.json();
      renderList();
      if (episodes.length > 0) selectEpisode(0);
    }}

    function renderList() {{
      const ul = document.getElementById('episode-list');
      ul.innerHTML = episodes.map((ep, i) => `
        <li onclick="selectEpisode(${{i}})" id="ep-${{i}}">
          <div class="ep-title">${{ep.title}}</div>
          <div class="ep-meta">${{ep.date}} · ${{ep.duration || ''}}</div>
        </li>
      `).join('');
    }}

    function selectEpisode(idx) {{
      const ep = episodes[idx];
      document.getElementById('player-title').textContent = ep.title;
      document.getElementById('player-date').textContent = `${{ep.date}} · ${{ep.duration || ''}}`;
      const audioEl = document.getElementById('audio-el');
      document.getElementById('audio-src').src = ep.audio_file;
      audioEl.load();

      // Paper links
      const linksDiv = document.getElementById('paper-links');
      if (ep.papers && ep.papers.length > 0) {{
        linksDiv.innerHTML = ep.papers.map(p =>
          `<a href="${{p.url}}" target="_blank">${{p.title}}</a>`
        ).join('');
      }} else {{
        linksDiv.innerHTML = '';
      }}

      // Active state
      document.querySelectorAll('.episode-list li').forEach(li => li.classList.remove('active'));
      document.getElementById(`ep-${{idx}}`).classList.add('active');
    }}

    loadEpisodes();
  </script>
</body>
</html>"""

    (site_path / "index.html").write_text(html, encoding="utf-8")
