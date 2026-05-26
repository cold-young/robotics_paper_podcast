"""
Audio Synthesis Module
======================
Synthesizes podcast scripts to MP3 using Gemini 2.5 Flash TTS.
Supports multi-speaker voices natively.

Environment variables:
    LLM_API_KEY : Gemini API key (shared with generate_script.py)
"""

import base64
import json
import os
import tempfile
import time
import urllib.request
import urllib.error
import wave
from pathlib import Path

LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"
)

# Speaker voice config
SPEAKER_VOICES = {
    "망망이": "Puck",    # Male — soft, gentle tone (shy puppy)
    "뭉이": "Aoede",    # Female — bright, cheerful tone (quirky hamster)
}

# TTS API rate limit: RPM=3, so we need intervals between calls
TTS_CALL_INTERVAL = 21  # seconds (60s / 3 RPM = 20s + 1s margin)
MAX_RETRIES = 3

# Gemini TTS input token limit (~8192 tokens ≈ 5000 Korean chars)
MAX_CHARS_PER_CHUNK = 4000


def _call_tts(text: str, speaker_voices: dict[str, str] | None = None) -> bytes:
    """
    Call Gemini TTS API and return raw PCM audio data.

    Args:
        text: Text to synthesize (multi-speaker format: "Speaker: line" per line)
        speaker_voices: {speaker_name: voice_name} mapping

    Returns:
        Raw PCM bytes (16-bit, 24kHz, mono)
    """
    if speaker_voices and len(speaker_voices) > 1:
        # Multi-speaker config
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
        # Single speaker
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
                print(f"    ! 429 Rate Limit. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            elif e.code == 503:
                print(f"    ! 503 Service Unavailable. Retrying in {TTS_CALL_INTERVAL}s...")
                time.sleep(TTS_CALL_INTERVAL)
                continue
            else:
                raise RuntimeError(f"TTS API error (HTTP {e.code}): {body}") from e
        except urllib.error.URLError as e:
            print(f"    ! Network error: {e.reason}. Retrying...")
            time.sleep(5)
            continue

    raise RuntimeError(f"TTS API call failed after {MAX_RETRIES} attempts")


def _pcm_to_wav(pcm_data: bytes, wav_path: str, sample_rate: int = 24000):
    """Save raw PCM data as a WAV file."""
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def _dialogue_to_tts_text(dialogue: list[dict]) -> str:
    """Convert dialogue list to Gemini TTS multi-speaker format."""
    lines = []
    for turn in dialogue:
        speaker = turn["speaker"]
        text = turn["text"]
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _chunk_dialogue(dialogue: list[dict], max_chars: int = MAX_CHARS_PER_CHUNK) -> list[list[dict]]:
    """Split dialogue into chunks that fit within TTS input limits."""
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
    Synthesize a podcast script into an MP3 file.

    Args:
        script: Script dict from generate_script
        output_path: Output MP3 file path

    Returns:
        output_path
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError(
            "pydub is required:\n"
            "  pip install pydub\n"
            "  (ffmpeg also needed: brew install ffmpeg)"
        )

    dialogue = script["dialogue"]

    # Extract speakers present in the script
    speakers_in_script = set(turn["speaker"] for turn in dialogue)
    voices = {s: SPEAKER_VOICES.get(s, "Kore") for s in speakers_in_script}

    # Gemini TTS multi-speaker requires EXACTLY 2 voices.
    # Always provide both configured speakers regardless of script content.
    if len(voices) < 2:
        voices = dict(SPEAKER_VOICES)

    # Split dialogue into chunks
    chunks = _chunk_dialogue(dialogue)
    print(f"    {len(dialogue)} lines -> {len(chunks)} chunk(s)")

    all_pcm = bytearray()

    for i, chunk in enumerate(chunks):
        print(f"    [{i+1}/{len(chunks)}] Synthesizing chunk ({len(chunk)} lines)...")

        tts_text = _dialogue_to_tts_text(chunk)
        pcm_data = _call_tts(tts_text, voices)
        all_pcm.extend(pcm_data)

        # Respect RPM limit: wait between chunks
        if i < len(chunks) - 1:
            print(f"    Waiting for RPM limit ({TTS_CALL_INTERVAL}s)...")
            time.sleep(TTS_CALL_INTERVAL)

    # PCM -> WAV -> MP3
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    _pcm_to_wav(bytes(all_pcm), tmp_wav)

    audio = AudioSegment.from_wav(tmp_wav)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    audio.export(output_path, format="mp3", bitrate="128k")

    os.unlink(tmp_wav)
    return output_path


# ── CLI test ──
if __name__ == "__main__":
    test_script = {
        "title": "Test Episode",
        "dialogue": [
            {"speaker": "망망이", "text": "안녕하세요! 오늘의 팟캐스트를 시작합니다."},
            {"speaker": "뭉이", "text": "네, 오늘은 흥미로운 논문이 있어요."},
            {"speaker": "망망이", "text": "감사합니다. 다음에 또 만나요!"},
        ],
    }
    out = synthesize_podcast(test_script, "test_output.mp3")
    print(f"Output: {out}")