"""Names from what people say: "Giulia, what do you think?" means the next speaker is Giulia.

Without a Teams video (audio recordings, screen captures) the only clues to who is who are in
the words themselves: self-introductions, people called by name, thanks to the previous speaker.

1. Candidates: capitalised words that never appear in lower case elsewhere in the transcript
   (so not "Allora" or "Quindi"); the language model (lm.py) keeps those that are people's
   names. Names from the participant list (and their first names and surnames) need no check,
   and a voice called "Giulia" then gets "Giulia Rossi".
2. Every mention is shown to the model with the turn before and the turn after, and it says
   whose name it is: the previous speaker, the one talking, the next one, or someone else.
   Clear phrases ("sono X", "grazie X", "X, a te la parola") settle most cases on their own.
3. The answers are summed per voice and each name goes to at most one voice, only with enough
   evidence. Voices left over may get a hint by elimination ("forse: ...").

On a 100-minute meeting: about 15 s on the GPU, 6 minutes on the CPU.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from .lm import LanguageModel

SYSTEM = ("You analyse meeting transcripts. Speakers are labelled with letters. "
          "Answer with a single letter.")
OPTIONS = ("A", "B", "C", "N")
CONTEXT_CHARS = 320  # of each turn shown around a mention
MAX_MENTIONS_PER_NAME = 12
NAME_WORD = r"[A-ZÀ-Ý][a-zà-ÿ]+(?:['’][A-Za-zà-ÿ]+)?"
NAME_RE = re.compile(rf"\b{NAME_WORD}(?:\s+{NAME_WORD})?\b")


@dataclass
class Turn:
    cluster: str
    start: float
    end: float
    text: str


@dataclass
class Mention:
    name: str
    turn: int  # index in the turns list
    offset: int  # character offset of the name in that turn
    prev: int | None = None
    next: int | None = None
    probs: dict[str, float] = field(default_factory=dict)
    cue: str | None = None  # answer settled by a phrase ("sono X", "grazie X", ...)
    person: str = ""  # full name from the participant list, when the mention is a part of it


def turns_from_paragraphs(paras: list[dict]) -> list[Turn]:
    """One turn per paragraph of render.paragraphs, labelled with its main cluster."""
    turns = []
    for p in paras:
        counts = Counter(w["speaker"] for w in p["words"] if w["speaker"])
        if counts and p["text"]:
            turns.append(Turn(counts.most_common(1)[0][0], p["start"], p["end"], p["text"]))
    return turns


def _sentence_start(text: str, pos: int) -> bool:
    before = text[:pos].rstrip()
    return not before or before[-1] in ".?!:…"


def aliases(participants: list[str]) -> dict[str, str]:
    """How each participant may be called: full name, first name, surname (when unambiguous)."""
    counts = Counter()
    for full in participants:
        parts = full.split()
        counts.update({p for p in (parts[0], parts[-1]) if len(parts) > 1})
    result = {}
    for full in participants:
        result[full] = full
        parts = full.split()
        for p in {parts[0], parts[-1]}:
            if len(parts) > 1 and counts[p] == 1 and len(p) > 2:
                result[p] = full
    return result


def candidate_names(turns: list[Turn], known: list[str] = ()) -> list[str]:
    """Capitalised words (or pairs) that look like proper nouns.

    At the start of a sentence any word is capitalised, so there a word also found in lower case
    elsewhere ("Allora", "Pensavo") is dropped; in mid-sentence a capitalised pair is kept whole
    ("sono Rosa Bianchi" even if "rosa" also occurs as a common word). After a common word at the
    start of a sentence ("Sono Rosa Bianchi.") the search starts again from the next word.
    """
    lower = set(re.findall(r"\b[a-zà-ÿ]+\b", " ".join(t.text for t in turns)))
    found = Counter()
    for turn in turns:
        pos = 0
        while m := NAME_RE.search(turn.text, pos):
            pos = m.end()
            words = m.group(0).split()
            start = _sentence_start(turn.text, m.start())
            if start and len(words) == 2 and words[0].lower() in lower:
                # "Sono Rosa Bianchi": the pair was "Sono Rosa"; look again from the second word.
                pos = m.start() + len(words[0]) + 1
                continue
            if start or len(words) == 1:
                words = [w for w in words if w.lower() not in lower]
            if words:
                found[" ".join(words)] += 1
            if start and len(words) == 2:
                found[words[1]] += 1  # "Grazie Luca": also "Luca" alone, for the model to judge
    names = set(found) | set(known)
    return sorted(names, key=lambda n: -found.get(n, 0))


def _person_question(excerpt: str, name: str) -> str:
    return (f'Sentence from a meeting: "...{excerpt}..."\n\n'
            f'Is "{name}" the name of a person (first name, surname or both)? '
            "A = yes, a person. N = no: a company, product, place, project, title, or a common word.")


PERSON_EXAMPLES = (
    (_person_question("ok, grazie Elena, adesso passiamo al secondo punto", "Elena"), "A"),
    (_person_question("Immaginavo, eh. Comunque andiamo avanti", "Immaginavo"), "N"),
    (_person_question("la sede è a Brescia e lavoriamo con Google", "Google"), "N"),
    (_person_question("come diceva il professor Bianchi nella sua relazione", "Bianchi"), "A"),
    (_person_question("referente per l'area di Data Strategy in azienda", "Data Strategy"), "N"),
)


def filter_people(model: LanguageModel, turns: list[Turn], names: list[str]) -> list[str]:
    """Ask the model which candidates are people's names, with one sentence of context each."""
    if not names:
        return []
    prompts = []
    for name in names:
        context = next((t.text for t in turns if name in t.text), "")
        i = context.find(name)
        prompts.append(_person_question(context[max(0, i - 150):i + 150], name))
    probs = model.choose(prompts, ("A", "N"), system=SYSTEM, examples=PERSON_EXAMPLES)
    return [n for n, p in zip(names, probs) if p["A"] >= 0.8]


# Phrases that settle whose name it is, in the six languages of the window. Each pattern gets the
# name as {n}; the answer letter follows the mention question (A previous, B speaker, C next, N other).
_W = r"[\s,]*"
CUES = {
    "B": [  # self-introduction
        r"\b(?:sono|mi chiamo|io sono|i'?m|i am|my name is|this is|me llamo|soy|je suis|je m'appelle|"
        r"moi c'est|sou|eu sou|me chamo)\s+(?:il |la |lo |el |le )?{n}\b",
    ],
    "A": [  # thanks / reply to the previous speaker
        r"\b(?:grazie(?: mille)?|ti ringrazio|thanks?|thank you|gracias|merci|obrigad[oa])" + _W + r"{n}\b",
        r"^\W*(?:sì|si|ok|okay|yes|sí|oui|sim|esatto|certo)?" + _W + r"{n}" + _W + r"(?:grazie|thanks|gracias|merci|obrigad)",
    ],
    "C": [  # giving the floor / asking the next speaker
        r"\b{n}" + _W + r"(?:lascio a te|a te la parola|tocca a te|vai pure|vai tu|prego|cosa ne pensi|che ne pensi|"
        r"puoi|vuoi|over to you|your turn|what do you think|can you|te toca|qué opinas|à toi|qu'en penses|"
        r"sua vez|o que achas|o que você acha)",
        r"\b(?:lascio (?:la parola )?a|passo la parola a|do la parola a|a te|over to|hand over to|"
        r"le paso la palabra a|je passe la parole à|passo a palavra (?:a|para))" + _W + r"{n}\b",
        r"\b{n}" + _W + r"[^.?!]{0,80}\?\s*$",
    ],
    "N": [  # talking about someone
        r"\b(?:diceva|ha detto|dice|diceva prima|la risposta di|secondo|come dice|parlava|"
        r"said|says|according to|decía|ha dicho|según|disait|a dit|selon|dizia|disse|segundo)" + _W + r"(?:il |la )?{n}\b",
        r"\b{n}\s+(?:diceva|ha detto|parlava|said|was saying|decía|disait|dizia)\b",
        r"\b(?:il|la|lo|del|della|dal|dalla|al|alla|per|con|di|il professor|la professoressa|il dottor|"
        r"the|professor|dr\.?)\s+{n}\b",
    ],
}


def cue(turn_text: str, offset: int, name: str) -> str | None:
    """The answer a phrase around the mention settles, if any."""
    window = turn_text[max(0, offset - 60):offset + len(name) + 90]
    tail = turn_text[offset:]
    n = re.escape(name)
    for answer in ("B", "A", "C", "N"):
        for pattern in CUES[answer]:
            text = tail if pattern.endswith(r"\?\s*$") else window
            if re.search(pattern.replace("{n}", n), text, re.IGNORECASE):
                return answer
    return None


def find_mentions(turns: list[Turn], names: list[str], full: dict[str, str] | None = None) -> list[Mention]:
    """Every occurrence of the names; full maps a first name or surname to the participant's full name."""
    full = full or {}
    mentions = []
    if not names:
        return mentions
    per_name = Counter()
    # Longest names first, so "Mario Rossi" is not also counted as "Mario".
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b")
    for i, turn in enumerate(turns):
        for m in pattern.finditer(turn.text):
            name = m.group(1)
            if per_name[name] >= MAX_MENTIONS_PER_NAME:
                continue
            prev = next((j for j in range(i - 1, -1, -1) if turns[j].cluster != turn.cluster), None)
            nxt = next((j for j in range(i + 1, len(turns)) if turns[j].cluster != turn.cluster), None)
            mentions.append(Mention(name, i, m.start(), prev, nxt, person=full.get(name, name)))
            per_name[name] += 1
    return mentions


def _clip(text: str, around: int | None = None, from_end: bool = False) -> str:
    if len(text) <= CONTEXT_CHARS:
        return text
    if around is not None:
        lo = max(0, around - CONTEXT_CHARS // 2)
        return ("..." if lo else "") + text[lo:lo + CONTEXT_CHARS] + "..."
    return "..." + text[-CONTEXT_CHARS:] if from_end else text[:CONTEXT_CHARS] + "..."


def exchange_question(prev: str | None, cur: str, nxt: str | None, name: str) -> str:
    lines = ([f"A: {prev}"] if prev else []) + [f"B: {cur}"] + ([f"C: {nxt}"] if nxt else [])
    exchange = "\n".join(lines)
    return (f"Meeting excerpt (A speaks, then B, then C):\n{exchange}\n\n"
            f'B says "{name}". Who is {name}?\n'
            "A = the previous speaker: B thanks A, replies to A, or repeats what A has just said\n"
            "B = B themself: B introduces themself\n"
            "C = the next speaker: B gives the floor to or asks a question of that person, and C answers\n"
            "N = none of them: someone absent, or someone B only quotes or talks about")


# Worked examples (the small model needs them to tell the four cases apart).
MENTION_EXAMPLES = (
    (exchange_question("Abbiamo chiuso il rilascio ieri sera.", "Grazie Luca, ottimo lavoro. Passiamo ai costi.",
                       "Sui costi siamo in linea.", "Luca"), "A"),
    (exchange_question("Facciamo un giro di presentazioni.", "Buongiorno, sono Sara Neri e seguo il marketing.",
                       "Piacere, io sono del legale.", "Sara Neri"), "B"),
    (exchange_question("Il budget per ora regge.", "Come diceva Anna la settimana scorsa, il budget è fisso.",
                       "Sì, confermo.", "Anna"), "N"),
    (exchange_question("Questo è il piano.", "Paolo, tu cosa ne pensi? A te la parola.",
                       "Secondo me va bene, però servono due settimane.", "Paolo"), "C"),
    (exchange_question("We shipped it on Friday.", "Thanks, Tom. Next item: hiring. Maria, any news?",
                       "Yes, we have two candidates.", "Maria"), "C"),
)


def mention_prompt(turns: list[Turn], m: Mention) -> str:
    return exchange_question(
        _clip(turns[m.prev].text, from_end=True) if m.prev is not None else None,
        _clip(turns[m.turn].text, around=m.offset),
        _clip(turns[m.next].text) if m.next is not None else None,
        m.name)


def classify(model: LanguageModel, turns: list[Turn], mentions: list[Mention]):
    probs = model.choose([mention_prompt(turns, m) for m in mentions], OPTIONS, system=SYSTEM,
                         examples=MENTION_EXAMPLES)
    for m, p in zip(mentions, probs):
        settled = cue(turns[m.turn].text, m.offset, m.name)
        if settled:
            # A clear phrase outweighs the model; the model still shades the confidence.
            p = {o: round(0.8 * (o == settled) + 0.2 * p[o], 3) for o in OPTIONS}
        m.cue = settled
        m.probs = p


# "Carlo said / was saying / Franco's answer": the person spoke earlier, so was in the meeting.
SPOKE = (r"\b(?:diceva|parlava|ha detto|aveva detto|la risposta di|said|was saying|mentioned|decía|dijo|"
         r"disait|a dit|dizia|disse)\b[\s,]*(?:\w+\s+){0,3}{n}\b",  # "diceva il mio amico X"
         r"\b{n}\s+(?:diceva|parlava|ha detto|said|was saying|decía|disait|dizia)\b")
MIN_HINT_SPEECH_S = 60.0


def spoke_earlier(turn_text: str, offset: int, name: str) -> bool:
    window = turn_text[max(0, offset - 50):offset + len(name) + 30]
    return any(re.search(p.replace("{n}", re.escape(name)), window, re.IGNORECASE) for p in SPOKE)


def assign(turns: list[Turn], mentions: list[Mention], speech: dict[str, float],
           min_score: float = 0.75, min_share: float = 0.6) -> dict:
    """Sum the evidence per (voice, name) and give each name to at most one voice.

    A name is sure only with a strong clue (a self-introduction, or the floor given by name) or
    with at least two clues: a single "thanks, Marco" may be a word Whisper misheard, or come
    from someone thanking a person who has not spoken. Voices left without a name may get a hint
    by elimination: people said to have spoken ("as Carlo was saying") were in the meeting, and
    nobody quotes themself in the third person.
    """
    from itertools import permutations

    from scipy.optimize import linear_sum_assignment

    votes = defaultdict(float)
    support = defaultdict(list)
    strong = set()  # (cluster, name) settled by "sono X" or "X, a te la parola"
    not_them = set()  # (cluster, name): that voice talked about the person, so it is not them
    present = set()
    for m in mentions:
        person = m.person or m.name
        for option, index in (("A", m.prev), ("B", m.turn), ("C", m.next)):
            if index is not None and m.probs.get(option, 0) > 0.05:
                key = (turns[index].cluster, person)
                votes[key] += m.probs[option]
                if m.probs[option] >= 0.5:
                    support[key].append(round(turns[m.turn].start))
                    if m.cue == option and option in ("B", "C"):
                        strong.add(key)
        if m.probs.get("B", 0) < 0.2:
            not_them.add((turns[m.turn].cluster, person))
        if spoke_earlier(turns[m.turn].text, m.offset, m.name):
            present.add(person)

    result = {}
    clusters = sorted({c for c, _ in votes})
    names = sorted({n for _, n in votes})
    if clusters:
        matrix = np.array([[votes.get((c, n), 0.0) for n in names] for c in clusters])
        rows, cols = linear_sum_assignment(-matrix)
        for r, c in zip(rows, cols):
            cluster, name, score = clusters[r], names[c], matrix[r, c]
            share = score / matrix[r].sum() if matrix[r].sum() else 0
            name_share = score / matrix[:, c].sum() if matrix[:, c].sum() else 0
            if score < 0.3:
                continue
            sure = (score >= min_score and share >= min_share and name_share >= min_share
                    and ((cluster, name) in strong or len(support.get((cluster, name), [])) >= 2))
            result[cluster] = {"name": name, "score": round(float(score), 2), "sure": bool(sure),
                               "evidence_s": support.get((cluster, name), [])[:6]}

    # Hints by elimination, only when exactly one way of pairing the rest is consistent.
    taken = {a["name"] for a in result.values() if a["sure"]}
    open_voices = [c for c, s in speech.items() if s >= MIN_HINT_SPEECH_S
                   and not result.get(c, {}).get("sure")]
    open_names = sorted(present - taken)
    if open_voices and len(open_names) == len(open_voices) <= 6:
        fits = [p for p in permutations(open_names)
                if all((c, n) not in not_them for c, n in zip(open_voices, p))]
        if len(fits) == 1:
            for c, n in zip(open_voices, fits[0]):
                result[c] = {"name": n, "score": 0.0, "sure": False, "by_elimination": True, "evidence_s": []}
    return result


def speech_seconds(paras: list[dict]) -> dict[str, float]:
    """Seconds of words actually spoken by each voice."""
    seconds = defaultdict(float)
    for p in paras:
        for w in p["words"]:
            if w["speaker"]:
                seconds[w["speaker"]] += w["end"] - w["start"]
    return dict(seconds)


def find_people(model: LanguageModel, turns: list[Turn], participants: list[str] = ()):
    """Candidates, the names that are people, and the map from a short form to a participant's full name."""
    full = aliases(list(participants))
    candidates = candidate_names(turns)
    spoken = " ".join(t.text for t in turns)
    known = [a for a in full if re.search(rf"\b{re.escape(a)}\b", spoken)]
    people = known + [n for n in filter_people(model, turns, [c for c in candidates if c not in full])
                      if n not in known]
    return candidates, people, full


def run(paras: list[dict], model: LanguageModel, participants: list[str] = ()) -> dict:
    """participants: optional full names (from the invitation); their first names and surnames
    count as people without asking the model, and a voice called "Giulia" gets the full name."""
    turns = turns_from_paragraphs(paras)
    candidates, people, full = find_people(model, turns, participants)
    mentions = find_mentions(turns, people, full)
    classify(model, turns, mentions)
    return {"candidates": candidates, "people": people, "mentions": len(mentions),
            "assignment": assign(turns, mentions, speech_seconds(paras)),
            "_mentions": [{"name": m.name, "t": round(turns[m.turn].start), "probs": m.probs} for m in mentions]}
