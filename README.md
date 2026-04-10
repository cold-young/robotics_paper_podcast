# 🤖🎙️ Dexterous Manipulation Daily Podcast

arXiv Dexterous Manipulation 논문을 매일 자동으로 수집하여  
**한국어 AI 팟캐스트**로 변환하고 GitHub Pages에 배포합니다.

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
# 클론
git clone https://github.com/<your-username>/dex-podcast.git
cd dex-podcast

# 가상환경
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# ffmpeg (pydub 백엔드)
# Ubuntu: sudo apt install ffmpeg
# macOS:  brew install ffmpeg
```

### 2. 환경변수 설정

```bash
# LLM API (OpenAI, Fireworks, 또는 호환 API)
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"   # 또는 Fireworks 등
export LLM_MODEL="gpt-4o-mini"                      # 또는 원하는 모델
```

### 3. 실행

```bash
# 전체 파이프라인 실행
python -m pipeline.main

# 특정 날짜 지정
python -m pipeline.main --date 2026-03-10

# 스크립트만 생성 (TTS 생략, API 테스트용)
python -m pipeline.main --dry-run

# 논문 수집 테스트
python -m pipeline.fetch_papers
```

### 4. GitHub Actions 자동화

1. 이 레포를 GitHub에 push
2. Settings → Secrets에 추가:
   - `LLM_API_KEY`
   - `LLM_BASE_URL`
   - `LLM_MODEL`
3. Settings → Pages → Source: `gh-pages` branch
4. 매일 KST 08:00에 자동 실행 (수동 실행도 가능)

## 프로젝트 구조

```
dex-podcast/
├── pipeline/
│   ├── main.py              # 파이프라인 오케스트레이터
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
다른 키워드 섹션(Manipulation, VLA)을 파싱하도록 수정 가능합니다.

## Credits

- 논문 소스: [cold-young/robotics_paper_daily](https://github.com/cold-young/robotics_paper_daily)
- TTS: [MeloTTS](https://github.com/myshell-ai/MeloTTS) (MIT License)
- Inspired by: [open-notebooklm](https://github.com/gabrielchua/open-notebooklm)
