"""
Checks every Azure service the app can use and reports what is live.

Run:  python -m scripts.check_azure

Prints one line per service. Nothing here echoes a key - only whether the
service answered. Safe to run in front of an audience.
"""
import sys

from app import config

OK = "  OK  "
FAIL = " FAIL "
SKIP = " SKIP "


def line(status: str, name: str, detail: str = "") -> None:
    print(f"[{status}] {name:<22} {detail}")


def check_openai() -> bool:
    if not (config.AZURE_OPENAI_API_KEY and config.AZURE_OPENAI_ENDPOINT):
        line(SKIP, "Azure OpenAI", "no key in .env - using fallback routing")
        return False
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=config.AZURE_OPENAI_API_KEY,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )
        resp = client.chat.completions.create(
            model=config.AZURE_OPENAI_DEPLOYMENT,
            messages=[{"role": "user", "content": "Reply with the word: ready"}],
            max_tokens=5,
        )
        reply = (resp.choices[0].message.content or "").strip()
        line(OK, "Azure OpenAI",
             f"{config.AZURE_OPENAI_DEPLOYMENT} replied {reply!r}")
        return True
    except Exception as exc:
        line(FAIL, "Azure OpenAI", str(exc)[:110])
        return False


def check_speech() -> bool:
    if not config.AZURE_SPEECH_KEY:
        line(SKIP, "Azure AI Speech", "no key - browser speech used instead")
        return False
    try:
        import azure.cognitiveservices.speech as speechsdk
        cfg = speechsdk.SpeechConfig(
            subscription=config.AZURE_SPEECH_KEY,
            region=config.AZURE_SPEECH_REGION,
        )
        cfg.speech_synthesis_voice_name = config.AZURE_SPEECH_VOICE
        synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        result = synth.speak_text_async("Health coach ready.").get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            line(OK, "Azure AI Speech",
                 f"{config.AZURE_SPEECH_VOICE} in {config.AZURE_SPEECH_REGION}, "
                 f"{len(result.audio_data)} bytes synthesised")
            return True
        line(FAIL, "Azure AI Speech", str(result.reason))
        return False
    except Exception as exc:
        line(FAIL, "Azure AI Speech", str(exc)[:110])
        return False


def check_content_safety() -> bool:
    from app.services import safety
    if not safety.content_safety_available():
        line(SKIP, "Content Safety", "no key - local red-flag rules still active")
        return False
    try:
        flagged = safety.content_safety_flags("I feel tired today")
        line(OK, "Content Safety",
             f"benign text flagged={flagged} (expected False)")
        return flagged is False
    except Exception as exc:
        line(FAIL, "Content Safety", str(exc)[:110])
        return False


def check_search() -> bool:
    if not (config.AZURE_SEARCH_API_KEY and config.AZURE_SEARCH_ENDPOINT):
        line(SKIP, "Azure AI Search", "no key - local knowledge base used")
        return False
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        client = SearchClient(
            endpoint=config.AZURE_SEARCH_ENDPOINT,
            index_name=config.AZURE_SEARCH_INDEX,
            credential=AzureKeyCredential(config.AZURE_SEARCH_API_KEY),
        )
        hits = list(client.search(search_text="headache", top=1))
        line(OK, "Azure AI Search",
             f"index {config.AZURE_SEARCH_INDEX!r}, {len(hits)} hit(s)")
        return True
    except Exception as exc:
        line(FAIL, "Azure AI Search", str(exc)[:110])
        return False


def main() -> int:
    print(f"\nMOCK_MODE = {config.MOCK_MODE}")
    if config.MOCK_MODE:
        print("(MOCK_MODE is on - the app ignores these services at runtime)\n")
    else:
        print()

    results = [check_openai(), check_speech(),
               check_content_safety(), check_search()]

    live = sum(results)
    print(f"\n{live} of 4 Azure services live. "
          f"The app runs either way - every service has a local fallback.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
