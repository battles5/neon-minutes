"""Merge words with speaker turns and write Markdown, SRT, WebVTT and JSON."""

import json
from pathlib import Path

import numpy as np

MAX_PARAGRAPH_S = 90.0
FRAGMENT_WORDS = 3
FRAGMENT_GAP_S = 2.0
CUE_MAX_S = 6.0
CUE_MAX_CHARS = 84
SENTENCE_END = (".", "?", "!", "…")


def attribute_words(segments: list[dict], turns: list[dict], max_gap_s: float = 1.0) -> list[dict]:
    """Tag each word with the cluster speaking at its midpoint (or the nearest turn)."""
    words = [dict(w) for seg in segments for w in seg["words"]]
    if not turns:
        return [dict(w, speaker=None) for w in words]
    turns = sorted(turns, key=lambda t: t["start"])
    starts = np.array([t["start"] for t in turns])
    ends = np.array([t["end"] for t in turns])
    previous = None
    for w in words:
        if previous is not None and not w["text"][:1].isspace():
            # Continuation of the previous word (e.g. "'unica" after " l"): never split a word.
            w["speaker"] = previous
            continue
        mid = (w["start"] + w["end"]) / 2
        i = int(np.searchsorted(starts, mid, side="right")) - 1
        speaker = None
        w["in_turn"] = bool(i >= 0 and mid < ends[i])
        if w["in_turn"]:
            speaker = turns[i]["speaker"]
        else:
            # Nearest turn edge: the previous turn's end or the next turn's start.
            candidates = []
            if i >= 0:
                candidates.append((mid - ends[i], i))
            if i + 1 < len(turns):
                candidates.append((starts[i + 1] - mid, i + 1))
            gap, j = min(candidates)
            if gap <= max_gap_s:
                speaker = turns[j]["speaker"]
        w["speaker"] = speaker or previous
        previous = w["speaker"]
    return words


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith(SENTENCE_END)


def _ends_clause(text: str) -> bool:
    return text.rstrip().endswith(SENTENCE_END + (",", ";", ":"))


def _continues(text: str) -> bool:
    """A word starting in lowercase carries on the sentence before it."""
    first = text.strip()[:1]
    return first.isalpha() and first.islower()


def _fix_boundaries(paras: list[dict]):
    """Move fragments of a sentence cut by a speaker change to the side it belongs to.

    Whisper's word times and pyannote's turn edges disagree by a few hundred ms, which
    leaves "...per altro. Al | momento no." or "...ce la | facciamo.". When the sentence
    visibly continues across the boundary and one side holds at most a few words, those
    words join the other side. Words that fell outside every voice turn were attributed
    by proximity only, so they may follow their sentence across a longer pause.
    """
    for a, b in zip(paras, paras[1:]):
        if not a["words"] or not b["words"] or _ends_sentence(a["words"][-1]["text"]):
            continue
        if not _continues(b["words"][0]["text"]):
            continue
        cut = len(a["words"])
        while cut > 0 and not _ends_sentence(a["words"][cut - 1]["text"]):
            cut -= 1
        tail = a["words"][cut:]
        close = b["words"][0]["start"] - tail[-1]["end"] <= FRAGMENT_GAP_S if tail else False
        if tail and len(tail) <= FRAGMENT_WORDS and (close or not any(w.get("in_turn") for w in tail)):
            b["words"][:0] = tail
            del a["words"][cut:]
            continue
        end = next((i for i, w in enumerate(b["words"]) if _ends_clause(w["text"])), None)
        if end is not None and end < FRAGMENT_WORDS and b["words"][0]["start"] - a["words"][-1]["end"] <= FRAGMENT_GAP_S:
            a["words"].extend(b["words"][: end + 1])
            del b["words"][: end + 1]


def paragraphs(words: list[dict], names: dict[str, str]) -> list[dict]:
    """Group consecutive words by speaker name; split long monologues at sentence ends.

    Grouping by name rather than by cluster also merges a person pyannote split in two.
    """
    result = []
    for w in words:
        name = names.get(w["speaker"], "Sconosciuto")
        cur = result[-1] if result else None
        too_long = (cur and w["start"] - cur["words"][0]["start"] > MAX_PARAGRAPH_S
                    and _ends_sentence(cur["words"][-1]["text"]))
        if cur is None or cur["speaker"] != name or too_long:
            result.append({"speaker": name, "words": []})
        result[-1]["words"].append(w)

    _fix_boundaries(result)
    merged = []
    for p in result:
        if not p["words"]:
            continue
        prev = merged[-1] if merged else None
        if prev and prev["speaker"] == p["speaker"] and p["words"][-1]["end"] - prev["words"][0]["start"] <= MAX_PARAGRAPH_S:
            prev["words"].extend(p["words"])
        else:
            merged.append(p)
    for p in merged:
        p["start"], p["end"] = p["words"][0]["start"], p["words"][-1]["end"]
        p["text"] = "".join(w["text"] for w in p["words"]).strip()
        p["clusters"] = sorted({w["speaker"] for w in p["words"] if w["speaker"]})
    return merged


def _clock(seconds: float, sep: str = ".") -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _hms(seconds: float) -> str:
    return _clock(seconds)[:8]


def _cues(paras: list[dict]):
    for p in paras:
        cue = []
        for w in p["words"]:
            text = "".join(x["text"] for x in cue + [w]).strip()
            if cue and (w["end"] - cue[0]["start"] > CUE_MAX_S or len(text) > CUE_MAX_CHARS):
                yield p["speaker"], cue[0]["start"], cue[-1]["end"], "".join(x["text"] for x in cue).strip()
                cue = []
            cue.append(w)
        if cue:
            yield p["speaker"], cue[0]["start"], cue[-1]["end"], "".join(x["text"] for x in cue).strip()


def write_outputs(out_dir: Path, meta: dict, speakers: dict, paras: list[dict]) -> list[Path]:
    md = [f"# {meta['title']}", ""]
    info = [meta["date"]] if meta.get("date") else []
    info.append(f"durata {_hms(meta['duration_s'])}")
    info.append(f"trascrizione {meta['asr_model']}, speaker {meta['diarization_model']}")
    md += [" · ".join(info), "", "## Partecipanti", "", "| Nome | Tempo di parola | Riconosciuto da |", "|---|---|---|"]
    by_name = {}
    for s in speakers.values():
        row = by_name.setdefault(s["name"], {"speech_s": 0.0, "sources": {}})
        row["speech_s"] += s.get("speech_s", 0.0)
        if s.get("source"):
            best = row["sources"].get(s["source"])
            conf = s.get("confidence")
            row["sources"][s["source"]] = conf if best is None or (conf or 0) > best else best
    for n, row in sorted(by_name.items(), key=lambda kv: -kv[1]["speech_s"]):
        sources = ", ".join(f"{src} ({c})" if c is not None else src for src, c in sorted(row["sources"].items()))
        md.append(f"| {n} | {_hms(row['speech_s'])} | {sources or '—'} |")
    md += ["", "## Trascrizione", ""]
    for p in paras:
        md += [f"**[{_hms(p['start'])}] {p['speaker']}:** {p['text']}", ""]

    srt, vtt = [], ["WEBVTT", ""]
    for i, (name, start, end, text) in enumerate(_cues(paras), 1):
        srt += [str(i), f"{_clock(start, ',')} --> {_clock(end, ',')}", f"{name}: {text}", ""]
        vtt += [f"{_clock(start)} --> {_clock(end)}", f"<v {name}>{text}", ""]

    doc = {
        "meta": meta,
        "speakers": speakers,
        "paragraphs": [
            {"start": p["start"], "end": p["end"], "speaker": p["speaker"], "clusters": p["clusters"],
             "text": p["text"], "words": [{k: w[k] for k in ("start", "end", "text", "p")} for w in p["words"]]}
            for p in paras
        ],
    }

    files = {
        "trascrizione.md": "\n".join(md),
        "trascrizione.srt": "\n".join(srt),
        "trascrizione.vtt": "\n".join(vtt),
        "trascrizione.json": json.dumps(doc, ensure_ascii=False, indent=1),
    }
    paths = []
    for filename, content in files.items():
        path = out_dir / filename
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths
