"""Emoji inference from role keywords — single source of truth."""

_EMOJI_MAP: list[tuple[list[str], str]] = [
    (["professor", "prof.", "dozent", "wissenschaft"], "👨‍🏫"),
    (["gründer", "founder", "ceo", "startup", "unternehmer"], "👨‍💻"),
    (["arbeiter", "arbeiterin", "fließband", "fabrik"], "👷"),
    (["rentner", "rentnerin", "pension", "landwirt", "bauer"], "👴"),
    (["inhaber", "inhaberin", "agentur", "marketing"], "👩‍💼"),
    (["gewerkschaft", "sekretär", "sekretärin"], "✊"),
    (["student", "studentin"], "👩‍🎓"),
    (["ärzt", "doktor", "dr.", "medizin", "pflege"], "👩‍⚕️"),
    (["lehrer", "lehrerin", "schule"], "👨‍🏫"),
    (["sozial", "flüchtling", "helfer"], "🤝"),
    (["driver", "fahrer", "fahrerin", "lkw", "taxi"], "🚗"),
    (["copy", "shop", "laden", "geschäft"], "🏪"),
    (["journalist", "reporter", "presse"], "📰"),
    (["künstler", "künstlerin", "designer"], "🎨"),
    (["anwalt", "anwältin", "richter", "jurist"], "⚖️"),
    (["politiker", "politikerin", "abgeordnet", "minister"], "🏛️"),
    (["mutter", "vater", "alleinerziehend"], "👩‍👧"),
    (["frau", "dame"], "👩"),
    (["herr", "mann"], "👨"),
]


def infer_emoji(role: str) -> str:
    role_lower = role.lower()
    for keywords, emoji in _EMOJI_MAP:
        if any(kw in role_lower for kw in keywords):
            return emoji
    return "👤"
