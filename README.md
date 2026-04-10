# 🤖🎙️ Dexterous Manipulation Daily Podcast

arXiv Dexterous Manipulation Podcast (KOR)

## Pipeline

```
robotics_paper_daily (Dexterous 섹션)
    ↓  GitHub Raw URL 파싱
논문 제목 + 초록 추출
    ↓  LLM (OpenAI-compatible API)
한국어 팟캐스트 대본 생성
    ↓  MeloTTS (Korean)
MP3 음성 합성
    ↓  GitHub Pages
웹 팟캐스트 플레이어 배포
```

## Quick Start

### 1. 환경 설정

```bash
git clone https://github.com/<your-username>/dex-podcast.git
cd dex-podcast

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Ubuntu: sudo apt install ffmpeg
# macOS:  brew install ffmpeg
```

### 2. 환경변수 설정

```bash
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"  
export LLM_MODEL="gpt-4o-mini"                      
```

### 3. 실행

```bash
python -m pipeline.main

python -m pipeline.main --date 2026-03-10

python -m pipeline.main --dry-run

python -m pipeline.fetch_papers
```

### 4. GitHub Actions

1. Github Push
2. Settings → Secrets:
   - `LLM_API_KEY`
   - `LLM_BASE_URL`
   - `LLM_MODEL`
3. Settings → Pages → Source: `gh-pages` branch
4. KST 08:00 Action

## Project Structure

```
dex-podcast/
├── pipeline/
│   ├── main.py              
│   ├── fetch_papers.py       # 논문 수집 (README.md 파싱)
│   ├── generate_script.py    # LLM 한국어 대본 생성
│   ├── synthesize_audio.py   # MeloTTS 음성 합성
│   └── build_site.py         # GitHub Pages 빌드
├── site/                     # GitHub Pages 소스
│   ├── index.html
│   ├── episodes.json
│   └── episodes/             # MP3 파일들
├── .github/workflows/
│   └── daily_podcast.yml     # 자동화 워크플로우
├── requirements.txt
└── README.md
```

## 커스터마이징

### LLM 백엔드 변경
`LLM_BASE_URL` 환경변수로 다양한 API를 사용할 수 있습니다:
- OpenAI: `https://api.openai.com/v1`
- Fireworks: `https://api.fireworks.ai/inference/v1`
- Together: `https://api.together.xyz/v1`
- Local (Ollama): `http://localhost:11434/v1`

### 논문 소스 변경
`fetch_papers.py`의 `REPO_RAW_URL`을 변경하거나,  
(Manipulation, VLA)을 파싱하도록 수정 가능합니다.

## Credits

- Ref: [cold-young/robotics_paper_daily](https://github.com/cold-young/robotics_paper_daily)
- TTS: [MeloTTS](https://github.com/myshell-ai/MeloTTS) (MIT License)
- Inspired by: [open-notebooklm](https://github.com/gabrielchua/open-notebooklm)
