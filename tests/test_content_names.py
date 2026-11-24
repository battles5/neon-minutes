"""Names from content without the language model: a stand-in model, the phrases decide.

    python tests/test_content_names.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meeting_transcriber import content_names as cn  # noqa: E402
from meeting_transcriber import naming, titles  # noqa: E402
from meeting_transcriber.pipeline import _participants_list  # noqa: E402

PEOPLE = {"Anna", "Luca", "Paolo", "Giulia", "Anna Neri", "Neri"}


class StandIn:
    """'Is X a person?' from a fixed list; no opinion on whose name a mention is."""

    def choose(self, prompts, options, system="", examples=()):
        out = []
        for prompt in prompts:
            if "Is \"" in prompt:
                name = prompt.split('Is "')[1].split('"')[0]
                out.append({"A": 0.95, "N": 0.05} if name in PEOPLE else {"A": 0.05, "N": 0.95})
            else:
                out.append({o: 1 / len(options) for o in options})
        return out


def paragraph(speaker, start, text, seconds=30.0):
    words = text.split()
    step = seconds / len(words)
    return {"speaker": speaker, "start": start, "end": start + seconds, "text": text,
            "words": [{"speaker": speaker, "start": start + i * step, "end": start + (i + 1) * step}
                      for i in range(len(words))]}


MEETING = [
    paragraph("S1", 0, "Buongiorno a tutti, sono Anna Neri e coordino il progetto. Iniziamo dal budget."),
    paragraph("S2", 40, "Il budget regge, abbiamo speso meno del previsto sul primo lotto di lavori."),
    paragraph("S1", 80, "Bene. Giulia, a te la parola per la parte tecnica."),
    paragraph("S3", 120, "Grazie. Sulla parte tecnica siamo in linea, come diceva Paolo la settimana scorsa."),
    paragraph("S1", 160, "Ottimo. Allora chiudiamo qui, grazie a tutti."),
    paragraph("S2", 200, "Come diceva Luca prima, il lotto due parte a marzo."),
    paragraph("S3", 240, "Perfetto, aggiorniamo il piano."),
]


def test_aliases():
    a = cn.aliases(["Anna Neri", "Luca Bianchi", "Luca Verdi"])
    assert a["Anna"] == "Anna Neri" and a["Neri"] == "Anna Neri"
    assert "Luca" not in a  # two participants are called Luca
    assert a["Bianchi"] == "Luca Bianchi"


def test_candidates():
    turns = cn.turns_from_paragraphs(MEETING)
    names = cn.candidate_names(turns)
    assert "Anna Neri" in names and "Giulia" in names
    # A sentence-start word is kept for the model only if it never occurs in lower case.
    assert "Allora" in names
    turns.append(cn.Turn("S2", 300, 330, "e allora bene, ottimo lavoro"))
    names = cn.candidate_names(turns)
    assert "Allora" not in names and "Ottimo" not in names
    # A common word starting the sentence does not swallow the first name.
    turns.append(cn.Turn("S2", 330, 360, "Io. Sono Rosa Bianchi. Sono qui per il progetto."))
    assert "Rosa Bianchi" in cn.candidate_names(turns)


def test_cues():
    assert cn.cue("Buongiorno, sono Anna Neri e coordino", 16, "Anna Neri") == "B"
    assert cn.cue("Grazie Luca, ottimo lavoro", 7, "Luca") == "A"
    assert cn.cue("Bene. Giulia, a te la parola", 6, "Giulia") == "C"
    assert cn.cue("come diceva Paolo la settimana scorsa", 12, "Paolo") == "N"
    assert cn.cue("Thanks, Tom. Next item.", 8, "Tom") == "A"
    assert cn.cue("Maria, what do you think?", 0, "Maria") == "C"


def test_assign():
    result = cn.run(MEETING, StandIn(), participants=["Anna Neri", "Giulia Rossi"])
    a = result["assignment"]
    assert a["S1"]["name"] == "Anna Neri" and a["S1"]["sure"], a
    assert a["S3"]["name"] == "Giulia Rossi" and a["S3"]["sure"], a  # "Giulia" + participant list
    # Luca and Paolo are quoted as having spoken, but only one voice (S2) is left: no hint by elimination.
    assert "S2" not in a or not a["S2"]["sure"], a


def test_single_thanks_is_a_hint():
    """One "grazie Luca" (perhaps misheard) names the previous voice only as a hint."""
    meeting = [
        paragraph("S1", 0, "Il primo lotto è finito e i costi sono in linea con quanto previsto a marzo."),
        paragraph("S2", 40, "Grazie Luca, passiamo al secondo punto: il calendario dei lavori di aprile."),
        paragraph("S1", 80, "Sul calendario non ci sono novità rispetto alla riunione della settimana scorsa."),
    ]
    a = cn.run(meeting, StandIn())["assignment"]
    assert a["S1"]["name"] == "Luca" and not a["S1"]["sure"], a
    assert cn.find_mentions(cn.turns_from_paragraphs(meeting), []) == []  # no names, no mentions


def test_add_content():
    speakers = {
        "S1": {"name": "Speaker 1", "speech_s": 90, "source": None, "auto": "Speaker 1"},
        "S2": {"name": "Mario Bianchi", "speech_s": 60, "source": "video", "auto": "Mario Bianchi"},
        "S3": {"name": "Speaker 2 (forse: Carlo)", "speech_s": 70, "source": None, "auto": "Speaker 2 (forse: Carlo)"},
        "S4": {"name": "Speaker 3", "speech_s": 40, "source": None, "auto": "Speaker 3"},
    }
    content = {
        "S1": {"name": "Anna Neri", "score": 1.0, "sure": True},
        "S4": {"name": "Mario Bianchi", "score": 0.0, "sure": False},  # already the video's name for S2
    }
    out = naming.add_content(speakers, content)
    assert out["S1"]["name"] == "Anna Neri" and out["S1"]["source"] == "content"
    assert out["S1"]["auto"] == "Anna Neri"  # still automatic: not mistaken for a manual edit
    assert out["S3"]["name"] == "Speaker 1 (forse: Carlo)"
    assert out["S4"]["name"] == "Speaker 2"


def test_participants_list():
    text = "Anna Neri <anna@example.org>; Luca Bianchi (Acme)\nGiulia Rossi, , Anna Neri"
    assert _participants_list(text) == ["Anna Neri", "Luca Bianchi", "Giulia Rossi"]
    assert _participants_list(["Anna Neri, Luca Bianchi"]) == ["Anna Neri", "Luca Bianchi"]


def test_title_clean():
    assert titles.clean('Titolo: "Revisione del budget 2027".') == "Revisione del budget 2027"
    assert titles.clean("Kick-off: new CRM / vendors?\nmore") == "Kick-off new CRM vendors"
    assert len(titles.clean("word " * 40)) <= titles.MAX_TITLE_CHARS


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print(f"{len(tests)} tests passed")
