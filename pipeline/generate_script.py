"""
팟캐스트 스크립트 생성 모듈
===========================
LLM을 사용하여 영어 논문 정보를 한국어 팟캐스트 대본으로 변환합니다.

지원 LLM 백엔드:
  - OpenAI-compatible API (default)
  - Fireworks AI
  - Anthropic Claude

환경변수:
  LLM_API_KEY      : API 키
  LLM_BASE_URL     : API 엔드포인트 (default: https://api.openai.com/v1)
  LLM_MODEL        : 모델명 (default: gpt-4o-mini)
"""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any

# export LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
# export LLM_MODEL="gemini-2.5-flash"
# ── Config ──
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite-preview")
# 폴백 모델 목록 (첫 번째 모델 실패 시 순서대로 시도)
LLM_FALLBACK_MODELS = os.environ.get("LLM_FALLBACK_MODELS", "gemini-3-flash-preview").split(",")

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


SYSTEM_PROMPT = """\
당신은 로보틱스 분야의 한국어 팟캐스트 진행자입니다.
두 명의 호스트(민수, 지연)가 자연스러운 대화 형식으로 오늘의 논문들을 소개합니다.

규칙:
1. 모든 대화는 한국어로 진행합니다.
2. 논문의 핵심 기여와 의미를 비전문가도 이해할 수 있게 설명합니다.
3. 전문 용어는 영어 원문을 병기합니다 (예: "손재주 조작(Dexterous Manipulation)").
4. 호스트 간에 자연스러운 리액션과 질문을 포함합니다.
5. 각 논문 소개는 1-2분 분량으로 간결하게 합니다.
6. 인트로와 아웃트로를 포함합니다.

출력 형식 (JSON):
{
  "title": "에피소드 제목",
  "description": "에피소드 설명 (1-2문장)",
  "estimated_duration": "예상 시간",
  "dialogue": [
    {"speaker": "민수", "text": "대사"},
    {"speaker": "지연", "text": "대사"},
    ...
  ]
}

JSON만 출력하세요. 다른 텍스트는 포함하지 마세요.
"""


def _build_user_prompt(papers: list[dict], target_date: str) -> str:
    """논문 목록을 기반으로 user prompt를 구성합니다."""
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
오늘의 Dexterous Manipulation 관련 arXiv 논문 {len(papers)}편을 소개하는 팟캐스트를 만들어주세요.

{chr(10).join(paper_descriptions)}

위 논문들을 기반으로 한국어 팟캐스트 대본을 JSON 형식으로 생성해주세요."""


def _call_llm_once(system: str, user: str, model: str) -> str:
    """OpenAI-compatible API를 한 번 호출합니다."""
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
    """재시도 및 모델 폴백을 포함한 LLM 호출."""
    models_to_try = [LLM_MODEL] + [m for m in LLM_FALLBACK_MODELS if m != LLM_MODEL]

    for model in models_to_try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"    → LLM 호출: model={model} (시도 {attempt}/{MAX_RETRIES})")
                return _call_llm_once(system, user, model)
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if e.code == 503:
                    print(f"    ⚠ 503 Service Unavailable (모델 과부하). {RETRY_DELAY}초 후 재시도...")
                    time.sleep(RETRY_DELAY)
                    continue
                elif e.code == 429:
                    print(f"    ⚠ 429 Rate Limit / Quota 초과. 다음 모델로 전환...")
                    break  # 이 모델은 포기, 다음 모델 시도
                else:
                    raise RuntimeError(
                        f"LLM API 오류 (HTTP {e.code}): {e.reason}\n{body}"
                    ) from e
            except urllib.error.URLError as e:
                print(f"    ⚠ 네트워크 오류: {e.reason}. {RETRY_DELAY}초 후 재시도...")
                time.sleep(RETRY_DELAY)
                continue

        print(f"    ✗ 모델 {model} 실패, 다음 모델 시도...")

    raise RuntimeError(
        f"모든 LLM 모델 호출 실패. 시도한 모델: {models_to_try}\n"
        "가능한 원인:\n"
        "  1. API 키가 올바르지 않거나 만료됨\n"
        "  2. 무료 tier 할당량 초과 (Google AI Studio에서 확인)\n"
        "  3. 모든 모델이 일시적 과부하 상태\n"
        "해결: LLM_API_KEY 환경변수 확인 또는 잠시 후 재시도"
    )


def _parse_llm_response(raw: str) -> dict:
    """LLM 응답에서 JSON을 추출합니다."""
    # ```json ... ``` 블록 제거
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
    논문 목록으로부터 한국어 팟캐스트 대본을 생성합니다.

    Returns:
        dict with keys: title, description, estimated_duration, dialogue
    """
    if not LLM_API_KEY:
        print("  ⚠ LLM_API_KEY not set. Using fallback template script.")
        return _fallback_script(papers, target_date)

    user_prompt = _build_user_prompt(papers, target_date)
    raw_response = _call_llm(SYSTEM_PROMPT, user_prompt)
    script = _parse_llm_response(raw_response)

    # Validate structure
    assert "dialogue" in script, "Missing 'dialogue' key in LLM response"
    assert isinstance(script["dialogue"], list), "'dialogue' must be a list"

    return script


def _fallback_script(papers: list[dict], target_date: str) -> dict:
    """LLM API가 없을 때 사용하는 템플릿 기반 대본 생성."""
    dialogue = [
        {
            "speaker": "민수",
            "text": f"안녕하세요! 오늘은 {target_date}, Dexterous Manipulation 데일리 팟캐스트입니다.",
        },
        {
            "speaker": "지연",
            "text": f"네, 오늘은 총 {len(papers)}편의 논문을 준비했어요. 바로 시작해볼까요?",
        },
    ]

    for i, p in enumerate(papers, 1):
        dialogue.append({
            "speaker": "민수",
            "text": f"{i}번째 논문은 '{p['title']}' 입니다. {p['authors']} 팀의 연구인데요.",
        })

        # 초록에서 첫 2문장 추출
        sentences = p["abstract"].split(". ")
        summary = ". ".join(sentences[:2]) + "."

        dialogue.append({
            "speaker": "지연",
            "text": f"이 논문의 핵심은, {summary}",
        })
        dialogue.append({
            "speaker": "민수",
            "text": "정말 흥미로운 연구네요. 다음 논문도 살펴보겠습니다.",
        })

    dialogue.extend([
        {
            "speaker": "지연",
            "text": "오늘 준비한 논문은 여기까지입니다!",
        },
        {
            "speaker": "민수",
            "text": "네, 다음 에피소드에서 또 만나요. 감사합니다!",
        },
    ])

    return {
        "title": f"Dexterous Manipulation 데일리 - {target_date}",
        "description": f"{target_date} arXiv에 올라온 Dexterous Manipulation 논문 {len(papers)}편을 소개합니다.",
        "estimated_duration": f"{len(papers) * 2}분",
        "dialogue": dialogue,
    }


# ── CLI 테스트 ──
if __name__ == "__main__":
    # 테스트용 더미 논문
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
