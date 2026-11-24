"""A short title for a meeting, from the beginning of its transcript ("Kick-off with Acme").

Used for the name of the results folder when the user prefers it to the recording's name:
"<date> <title>", e.g. "2026-03-12 Budget review for the new office".
"""

import re

from .lm import LanguageModel

SYSTEM = "You write short, plain titles for meetings."
LANGUAGE_NAMES = {"it": "Italian", "en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese",
                  "zh": "Chinese", "de": "German", "nl": "Dutch"}
EXCERPT_CHARS = 6000  # the opening minutes usually say what the meeting is about
MAX_TITLE_CHARS = 70


def _question(excerpt: str, language: str) -> str:
    lang = LANGUAGE_NAMES.get(language, "the language of the transcript")
    return (f"Beginning of a meeting transcript:\n\n{excerpt}\n\n"
            f"Write the title of this meeting as it could appear in the calendar invitation: 3 to 8 words, "
            f"in {lang}, about its purpose (who meets whom, or the subject). No date, no quotes, "
            f"no final full stop. Answer with the title only.")


EXAMPLES = (
    (_question("Anna: Good morning, thanks for joining. As you know we need to decide on the new CRM by June.\n"
               "Tom: Yes, I have prepared a comparison of the three vendors...", "en"),
     "Choosing the new CRM vendor"),
    (_question("Luca: Allora, benvenuti. Oggi vi presentiamo la nostra azienda e capiamo se ci sono spazi "
               "di collaborazione sul progetto di manutenzione predittiva.\nGiulia: Grazie dell'invito...", "it"),
     "Incontro conoscitivo sulla manutenzione predittiva"),
)


def excerpt(paras: list[dict]) -> str:
    lines, size = [], 0
    for p in paras:
        line = f"{p['speaker']}: {p['text']}"
        lines.append(line)
        size += len(line)
        if size >= EXCERPT_CHARS:
            break
    return "\n".join(lines)[:EXCERPT_CHARS]


def clean(title: str) -> str:
    """One line without quotes, characters a folder name cannot hold, or a final full stop."""
    title = title.strip().splitlines()[0] if title.strip() else ""
    title = re.sub(r'^(?:title|titolo|título|titre|标题)\s*:\s*', "", title, flags=re.IGNORECASE)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f“”«»]', " ", title).strip(" '’.`*-")
    title = re.sub(r"\s+", " ", title)
    if len(title) > MAX_TITLE_CHARS:
        title = title[:MAX_TITLE_CHARS].rsplit(" ", 1)[0]
    return title


def meeting_title(model: LanguageModel, paras: list[dict], language: str) -> str:
    text = excerpt(paras)
    if not text.strip():
        return ""
    return clean(model.answer(_question(text, language), system=SYSTEM, examples=EXAMPLES, max_tokens=32))
