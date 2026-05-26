"""
Podcast Script Generator
========================
Converts English paper metadata into a Korean podcast script using an LLM.

Supported LLM backends:
  - OpenAI-compatible API (default)
  - Fireworks AI
  - Anthropic Claude

Environment variables:
  LLM_API_KEY      : API key
  LLM_BASE_URL     : API endpoint (default: Gemini OpenAI-compatible)
  LLM_MODEL        : Model name (default: gemini-3.1-flash-lite-preview)
"""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any

# ── Config ──
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
# Fallback models (tried in order if primary model fails)
LLM_FALLBACK_MODELS = os.environ.get("LLM_FALLBACK_MODELS", "gemini-3.5-flash,gemini-2.5-flash-lite").split(",")

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


SYSTEM_PROMPT = """\
당신은 로보틱스 분야의 한국어 팟캐스트 진행자입니다.
두 명의 호스트가 자연스러운 대화 형식으로 오늘의 논문들을 소개합니다.

호스트 페르소나:
- 망망이(남): 수줍고 조심스럽지만 다정한 강아지 같은 성격. 논문을 차분하게 설명하고,
  어려운 내용도 부드럽게 풀어줌. "아, 이거 정말 대단한 것 같아요..." 같은 조심스러운 감탄을 자주 함.
  살짝 소심해서 자기 의견을 조심스럽게 내놓지만, 논문에 대한 애정이 묻어남.
- 뭉이(여): 귀엽고 엉뚱한 햄스터 같은 성격. 호기심이 폭발하고 리액션이 크며,
  엉뚱한 비유로 어려운 개념을 쉽게 만듦. "헐 이거 완전 대박 아니야?!" 같은 활발한 반응.
  가끔 엉뚱한 질문으로 망망이를 당황하게 만들지만, 그게 오히려 핵심을 찌르는 질문이 됨.

규칙:
1. 모든 대화는 한국어로 진행합니다.
2. 논문의 핵심 기여와 의미를 로보틱스 분야 대학원생 청자를 대상으로 설명합니다.
3. 전문 용어는 영어 원문을 병기합니다 (예: "손재주 조작(Dexterous Manipulation)").
4. 논문의 주요 방법론에 대해서 간단히 설명합니다.
5. 각 캐릭터의 페르소나가 대화에 자연스럽게 드러나야 합니다.
6. 각 논문 소개는 2분 분량으로 간결하게 합니다.
7. 인트로와 아웃트로를 포함합니다.

출력 형식 (JSON):
{
  "title": "에피소드 제목",
  "description": "에피소드 설명 (1-2문장)",
  "estimated_duration": "예상 시간",
  "dialogue": [
    {"speaker": "망망이", "text": "대사"},
    {"speaker": "뭉이", "text": "대사"},
    ...
  ]
}

JSON만 출력하세요. 다른 텍스트는 포함하지 마세요.
"""


def _build_user_prompt(papers: list[dict], target_date: str) -> str:
    """Build user prompt from paper list."""
    paper_descriptions = []
    for i, p in enumerate(papers, 1):
        desc = f"""
논문 {i}:
- 제목: {p['title']}
- 저자: {p['authors']}
- 초록: {p['abstract'][:1000]}
- URL: {p['url']}
""".strip()
        paper_descriptions.append(desc)

    return f"""오늘 날짜: {target_date}
오늘의 Dexterous Manipulation 관련 최신 논문 {len(papers)}편을 소개하는 팟캐스트를 만들어주세요.

{chr(10).join(paper_descriptions)}

위 논문들을 기반으로 한국어 팟캐스트 대본을 JSON 형식으로 생성해주세요."""


def _call_llm_once(system: str, user: str, model: str) -> str:
    """Call an OpenAI-compatible API once."""
    url = f"{LLM_BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        },
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


def _call_llm(system: str, user: str) -> str:
    """Call LLM with retry and model fallback."""
    models_to_try = [LLM_MODEL] + [m for m in LLM_FALLBACK_MODELS if m != LLM_MODEL]

    for model in models_to_try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"    -> LLM call: model={model} (attempt {attempt}/{MAX_RETRIES})")
                return _call_llm_once(system, user, model)
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if e.code == 503:
                    print(f"    ! 503 Service Unavailable. Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                elif e.code == 429:
                    print(f"    ! 429 Rate Limit / Quota exceeded. Switching model...")
                    break
                else:
                    raise RuntimeError(
                        f"LLM API error (HTTP {e.code}): {e.reason}\n{body}"
                    ) from e
            except urllib.error.URLError as e:
                print(f"    ! Network error: {e.reason}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue

        print(f"    x Model {model} failed, trying next model...")

    raise RuntimeError(
        f"All LLM models failed. Tried: {models_to_try}\n"
        "Possible causes:\n"
        "  1. API key is invalid or expired\n"
        "  2. Free tier quota exceeded (check Google AI Studio)\n"
        "  3. All models temporarily overloaded\n"
        "Fix: Check LLM_API_KEY env var or retry later"
    )


def _parse_llm_response(raw: str) -> dict:
    """Extract JSON from LLM response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    return json.loads(raw)


def generate_podcast_script(
    papers: list[dict],
    target_date: str,
) -> dict[str, Any]:
    """
    Generate a Korean podcast script from a list of papers.

    Returns:
        dict with keys: title, description, estimated_duration, dialogue
    """
    if not LLM_API_KEY:
        print("  ! LLM_API_KEY not set. Using fallback template script.")
        return _fallback_script(papers, target_date)

    user_prompt = _build_user_prompt(papers, target_date)
    raw_response = _call_llm(SYSTEM_PROMPT, user_prompt)
    script = _parse_llm_response(raw_response)

    # Validate structure
    assert "dialogue" in script, "Missing 'dialogue' key in LLM response"
    assert isinstance(script["dialogue"], list), "'dialogue' must be a list"

    return script


def _fallback_script(papers: list[dict], target_date: str) -> dict:
    """Template-based script generation when LLM API is unavailable."""
    dialogue = [
        {
            "speaker": "뭉이",
            "text": f"안녕하세요! 오늘은 {target_date}, Dexterous Manipulation 데일리 팟캐스트입니다.",
        },
        {
            "speaker": "망망이",
            "text": f"네, 오늘은 총 {len(papers)}편의 논문을 준비했어요. 바로 시작해볼까요?",
        },
    ]

    for i, p in enumerate(papers, 1):
        dialogue.append({
            "speaker": "뭉이",
            "text": f"{i}번째 논문은 '{p['title']}' 입니다. {p['authors']} 팀의 연구인데요.",
        })

        sentences = p["abstract"].split(". ")
        summary = ". ".join(sentences[:2]) + "."

        dialogue.append({
            "speaker": "망망이",
            "text": f"이 논문의 핵심은, {summary}",
        })
        dialogue.append({
            "speaker": "뭉이",
            "text": "정말 흥미로운 연구네요. 다음 논문도 살펴보겠습니다.",
        })

    dialogue.extend([
        {
            "speaker": "망망이",
            "text": "오늘 준비한 논문은 여기까지입니다!",
        },
        {
            "speaker": "뭉이",
            "text": "네, 다음 에피소드에서 또 만나요. 감사합니다!",
        },
    ])

    return {
        "title": f"Dexterous Manipulation Daily - {target_date}",
        "description": f"Covering {len(papers)} Dexterous Manipulation papers from arXiv on {target_date}.",
        "estimated_duration": f"{len(papers) * 2} min",
        "dialogue": dialogue,
    }


# ── CLI test ──
if __name__ == "__main__":
    test_papers = [
        {
            "title": "DexHiL: A Human-in-the-Loop Framework",
            "authors": "Wenzhao Lian Team",
            "abstract": "While VLA models have demonstrated promising generalization in robotic manipulation, deploying them on complex downstream tasks still demands effective post-training.",
            "url": "http://arxiv.org/abs/2603.09121",
        }
    ]
    script = generate_podcast_script(test_papers, "2026-03-10")
    print(json.dumps(script, ensure_ascii=False, indent=2))