"""
Azure AI Speech - speech-to-text and text-to-speech.

Not wired into the API yet. The browser's Web Speech API is used as a
placeholder in the UI; these functions replace it once the Speech resource
is provisioned. Keeping the interface here means only app/main.py changes.
"""
from app import config


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
