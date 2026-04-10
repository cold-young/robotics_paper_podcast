"""
음성 합성 모듈
==============
Gemini 2.5 Flash TTS를 사용하여 팟캐스트 대본을 MP3로 합성합니다.
다중 화자(민수, 지연)를 네이티브로 지원합니다.

환경변수:
    LLM_API_KEY : Gemini API 키 (generate_script.py와 공유)
"""

import base64
import json
import os
import time
import urllib.request
import urllib.error
import wave
from pathlib import Path

LLM_API_KEY = os.environ.get("LLM_API_KEY", "AIzaSyCsGBKmc52Octa5pYp8l5_3JTsirfH8pII")
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"
)

# 호스트별 음성 설정
SPEAKER_VOICES = {
    "민수": "Orus",    # 남성 음성
    "지연": "Leda",    # 여성 음성
}

# TTS API 제한: RPM=3 이므로 호출 간 간격 필요
TTS_CALL_INTERVAL = 21  # seconds (60s / 3 RPM = 20s, 여유 1s 추가)
MAX_RETRIES = 3

# Gemini TTS 입력 토큰 제한 (약 8192 토큰 ≈ 5000자 한국어)
MAX_CHARS_PER_CHUNK = 4000


def _call_tts(text: str, speaker_voices: dict[str, str] | None = None) -> bytes:
    """
    Gemini TTS API를 호출하여 PCM 오디오 데이터를 반환합니다.

    Args:
        text: TTS할 텍스트 (다중 화자 형식: "Speaker: 대사" 줄바꿈 구분)
        speaker_voices: {speaker_name: voice_name} 매핑

    Returns:
        Raw PCM bytes (16-bit, 24kHz, mono)
    """
    if speaker_voices and len(speaker_voices) > 1:
        # 다중 화자 설정
        speech_config = {
            "multiSpeakerVoiceConfig": {
                "speakerVoiceConfigs": [
                    {
                        "speaker": name,
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": voice}
                        },
                    }
                    for name, voice in speaker_voices.items()
                ]
            }
        }
    else:
        # 단일 화자
        voice = list(speaker_voices.values())[0] if speaker_voices else "Kore"
        speech_config = {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": voice}
            }
        }

    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": speech_config,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    url = f"{TTS_ENDPOINT}?key={LLM_API_KEY}"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            audio_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            return base64.b64decode(audio_data)

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if e.code == 429:
                wait = TTS_CALL_INTERVAL * attempt
                print(f"    ⚠ 429 Rate Limit. {wait}초 대기 후 재시도...")
                time.sleep(wait)
                continue
            elif e.code == 503:
                print(f"    ⚠ 503 Service Unavailable. {TTS_CALL_INTERVAL}초 후 재시도...")
                time.sleep(TTS_CALL_INTERVAL)
                continue
            else:
                raise RuntimeError(f"TTS API 오류 (HTTP {e.code}): {body}") from e
        except urllib.error.URLError as e:
            print(f"    ⚠ 네트워크 오류: {e.reason}. 재시도...")
            time.sleep(5)
            continue

    raise RuntimeError(f"TTS API 호출 {MAX_RETRIES}회 실패")


def _pcm_to_wav(pcm_data: bytes, wav_path: str, sample_rate: int = 24000):
    """Raw PCM 데이터를 WAV 파일로 저장합니다."""
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def _dialogue_to_tts_text(dialogue: list[dict]) -> str:
    """대화 목록을 Gemini TTS 다중 화자 형식으로 변환합니다."""
    lines = []
    for turn in dialogue:
        speaker = turn["speaker"]
        text = turn["text"]
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _chunk_dialogue(dialogue: list[dict], max_chars: int = MAX_CHARS_PER_CHUNK) -> list[list[dict]]:
    """대화를 TTS 입력 제한에 맞게 청크로 분할합니다."""
    chunks = []
    current_chunk = []
    current_len = 0

    for turn in dialogue:
        turn_text = f"{turn['speaker']}: {turn['text']}\n"
        turn_len = len(turn_text)

        if current_len + turn_len > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_len = 0

        current_chunk.append(turn)
        current_len += turn_len

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def synthesize_podcast(script: dict, output_path: str) -> str:
    """
    팟캐스트 대본을 MP3 파일로 합성합니다.

    Args:
        script: generate_script에서 생성된 대본 dict
        output_path: 출력 MP3 파일 경로

    Returns:
        output_path
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError(
            "pydub가 필요합니다:\n"
            "  pip install pydub\n"
            "  (ffmpeg도 설치 필요: brew install ffmpeg)"
        )

    dialogue = script["dialogue"]

    # 대화에 등장하는 화자만 추출
    speakers_in_script = set(turn["speaker"] for turn in dialogue)
    voices = {s: SPEAKER_VOICES.get(s, "Kore") for s in speakers_in_script}

    # 대화를 청크로 분할
    chunks = _chunk_dialogue(dialogue)
    print(f"    총 {len(dialogue)}개 대사 → {len(chunks)}개 청크로 분할")

    all_pcm = bytearray()

    for i, chunk in enumerate(chunks):
        print(f"    [{i+1}/{len(chunks)}] 청크 합성 중 ({len(chunk)}개 대사)...")

        tts_text = _dialogue_to_tts_text(chunk)
        pcm_data = _call_tts(tts_text, voices)
        all_pcm.extend(pcm_data)

        # RPM 제한 준수: 마지막 청크가 아니면 대기
        if i < len(chunks) - 1:
            print(f"    ⏳ RPM 제한 대기 ({TTS_CALL_INTERVAL}초)...")
            time.sleep(TTS_CALL_INTERVAL)

    # PCM → WAV → MP3 변환
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    _pcm_to_wav(bytes(all_pcm), tmp_wav)

    audio = AudioSegment.from_wav(tmp_wav)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    audio.export(output_path, format="mp3", bitrate="128k")

    os.unlink(tmp_wav)
    return output_path


# ── CLI 테스트 ──
if __name__ == "__main__":
    test_script = {
        "title": "테스트 에피소드",
        "dialogue": [
            {"speaker": "민수", "text": "안녕하세요! 오늘의 팟캐스트를 시작합니다."},
            {"speaker": "지연", "text": "네, 오늘은 흥미로운 논문이 있어요."},
            {"speaker": "민수", "text": "감사합니다. 다음에 또 만나요!"},
        ],
    }
    out = synthesize_podcast(test_script, "test_output.mp3")
    print(f"Output: {out}")
