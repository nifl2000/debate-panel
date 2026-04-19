"""Language detection utility — single source of truth."""

from langdetect import detect, LangDetectException

LANGUAGE_MAP: dict[str, str] = {
    "de": "German",
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "tr": "Turkish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}


def detect_language(text: str) -> str:
    """Detect language of *text* and return its English name.

    Falls back to ``"English"`` when detection fails.
    """
    try:
        code = detect(text)
    except LangDetectException:
        code = "en"
    return LANGUAGE_MAP.get(code, "English")
