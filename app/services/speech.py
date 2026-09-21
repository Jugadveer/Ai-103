"""
Azure AI Speech - speech-to-text and text-to-speech.

Not wired into the API yet. The browser's Web Speech API is used as a
placeholder in the UI; these functions replace it once the Speech resource
is provisioned. Keeping the interface here means only app/main.py changes.
"""
from app import config
from app.core import logging as log


def _speech_config():
    import azure.cognitiveservices.speech as speechsdk
    cfg = speechsdk.SpeechConfig(
        subscription=config.AZURE_SPEECH_KEY,
        region=config.AZURE_SPEECH_REGION,
    )
    cfg.speech_synthesis_voice_name = config.AZURE_SPEECH_VOICE
    return cfg


def available() -> bool:
    return not config.MOCK_MODE and bool(config.AZURE_SPEECH_KEY)


def speech_to_text(audio_path: str) -> str:
    """Transcribe a WAV file. Returns '' if Speech is not configured."""
    if not available():
        return ""
    try:
        import azure.cognitiveservices.speech as speechsdk
        audio = speechsdk.AudioConfig(filename=audio_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=_speech_config(), audio_config=audio
        )
        result = recognizer.recognize_once()
        return result.text or ""
    except Exception as exc:
        print(f"[speech] STT failed ({exc})")
        return ""


def text_to_speech(text: str, out_path: str = "reply.wav") -> str:
    """Synthesise speech to a WAV file. Returns '' if not configured."""
    if not available():
        return ""
    try:
        import azure.cognitiveservices.speech as speechsdk
        audio = speechsdk.audio.AudioOutputConfig(filename=out_path)
        synth = speechsdk.SpeechSynthesizer(
            speech_config=_speech_config(), audio_config=audio
        )
        synth.speak_text_async(text).get()
        return out_path
    except Exception as exc:
        print(f"[speech] TTS failed ({exc})")
        return ""


def synthesize_bytes(text: str) -> bytes | None:
    """
    Synthesise speech and return WAV bytes, for serving over HTTP.

    Returns None when Speech is not configured or the call fails, so the
    caller can fall back to the browser's own voice.
    """
    if not available():
        return None
    try:
        import azure.cognitiveservices.speech as speechsdk
        from app.core.retry import with_retry

        # audio_config=None keeps the audio in memory instead of a file.
        synth = speechsdk.SpeechSynthesizer(
            speech_config=_speech_config(), audio_config=None
        )
        result = with_retry(lambda: synth.speak_text_async(text).get(),
                            label="azure_tts")
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return result.audio_data
        log.warn("tts_failed", reason=str(result.reason))
        return None
    except Exception as exc:
        log.warn("tts_error", error=str(exc)[:120])
        return None


def transcribe_wav(audio: bytes) -> tuple[str, str]:
    """
    Transcribe a WAV recording with Azure AI Speech.

    Returns (text, reason). An empty text with a reason lets the caller
    tell the user what actually happened rather than silently resetting
    the microphone button, which was the old behaviour and looked like
    the feature was broken.
    """
    if not available():
        return "", "speech_not_configured"

    import os
    import tempfile

    path = ""
    try:
        import azure.cognitiveservices.speech as speechsdk

        # The SDK reads from a file, so the upload is staged in temp and
        # removed immediately afterwards.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(audio)
            path = handle.name

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=_speech_config(),
            audio_config=speechsdk.AudioConfig(filename=path),
        )
        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            log.info("transcribed", chars=len(result.text))
            return result.text, "ok"
        if result.reason == speechsdk.ResultReason.NoMatch:
            return "", "no_speech"
        log.warn("transcribe_failed", reason=str(result.reason))
        return "", "failed"
    except Exception as exc:
        log.error("transcribe_error", error=str(exc)[:160])
        return "", "error"
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
