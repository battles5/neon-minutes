"""Give diarization clusters real names.

Video evidence comes from the Teams highlight timeline (video_labels). For a voice
cluster c and a name n we compare how often n is lit while c speaks (p_in) with how
often n is lit while *other* clusters speak (p_out). An open mic or the presenter
label is lit no matter who talks, so plain co-occurrence would favour it; the
contrast p_in - p_out does not.

Voice evidence comes from the local voice library (voices.py) and is used for the
clusters the video could not name.
"""

from collections import Counter
from difflib import SequenceMatcher

import numpy as np

# A cluster gets a name from video only with enough evidence behind it.
MIN_EVIDENCE_S = 3.0
MIN_P_IN = 0.4
MIN_CONTRAST = 0.25
# Below those, a weaker best guess is still shown as a hint ("forse: ...").
HINT_P_IN = 0.2
HINT_CONTRAST = 0.1
LAGS = np.arange(-1.0, 3.01, 0.25)


def _truncated(name: str) -> bool:
    return name.endswith("...") or name.endswith("…")


def build_roster(samples: list[dict], min_samples: int = 2) -> dict[str, str]:
    """Map every OCR'd label text to a canonical participant name.

    OCR variants fold into the most frequent close spelling; names Teams truncated
    ("Mario Ros...") fold into the unique full name they are a prefix of.
    """
    counts = Counter(n for s in samples for n in s["names"])
    canonical: list[str] = []
    mapping: dict[str, str] = {}
    for name, _ in counts.most_common():
        if _truncated(name):
            continue
        match = next(
            (c for c in canonical if SequenceMatcher(None, c.lower(), name.lower()).ratio() >= 0.85), None
        )
        if match is None:
            canonical.append(name)
        mapping[name] = match or name
    for name in counts:
        if _truncated(name):
            prefix = name.rstrip(".… ").lower()
            hits = [c for c in canonical if c.lower().startswith(prefix)]
            if len(hits) == 1:
                mapping[name] = hits[0]
    totals = Counter()
    for s in samples:
        totals.update({mapping[n] for n in s["names"] if n in mapping})
    return {raw: canon for raw, canon in mapping.items() if totals[canon] >= min_samples}


def participants(roster: dict[str, str]) -> list[str]:
    return sorted(set(roster.values()))


def _activity(samples: list[dict], roster: dict[str, str], names: list[str]):
    times = np.array([s["t"] for s in samples], dtype=float)
    lit = np.zeros((len(names), len(samples)), dtype=bool)
    index = {n: i for i, n in enumerate(names)}
    for j, s in enumerate(samples):
        for raw in s["names"]:
            if raw in roster:
                lit[index[roster[raw]], j] = True
    return times, lit


def _active_cluster(turns: list[dict], clusters: list[str], times: np.ndarray) -> np.ndarray:
    """Index of the cluster speaking at each time (-1 for silence)."""
    starts = np.array([t["start"] for t in turns])
    ends = np.array([t["end"] for t in turns])
    labels = np.array([clusters.index(t["speaker"]) for t in turns])
    pos = np.searchsorted(starts, times, side="right") - 1
    active = np.full(len(times), -1)
    ok = (pos >= 0) & (times < ends[np.clip(pos, 0, None)])
    active[ok] = labels[pos[ok]]
    return active


def _scores(active: np.ndarray, lit: np.ndarray, n_clusters: int):
    p_in = np.zeros((n_clusters, lit.shape[0]))
    p_out = np.zeros_like(p_in)
    n_in = np.zeros(n_clusters, dtype=int)
    for c in range(n_clusters):
        inside = active == c
        outside = (active >= 0) & ~inside
        n_in[c] = inside.sum()
        if n_in[c]:
            p_in[c] = lit[:, inside].mean(axis=1)
        if outside.any():
            p_out[c] = lit[:, outside].mean(axis=1)
    return p_in, p_out, n_in


def name_from_video(samples: list[dict], roster: dict[str, str], turns: list[dict], fps: float) -> dict:
    """Per cluster: best video name, evidence, and the highlight lag that fits best."""
    clusters = sorted({t["speaker"] for t in turns})
    names = participants(roster)
    if not clusters or not names or not samples:
        return {"lag_s": None, "clusters": {}}
    times, lit = _activity(samples, roster, names)

    # Teams lights a label a little after the voice starts: the audio heard at video time t
    # was spoken at t - lag. Pick the lag under which clusters and names agree best.
    best = None
    for lag in LAGS:
        active = _active_cluster(turns, clusters, times - lag)
        p_in, p_out, n_in = _scores(active, lit, len(clusters))
        fit = float((n_in * (p_in - p_out).max(axis=1)).sum())
        if best is None or fit > best[0]:
            best = (fit, lag, p_in, p_out, n_in)
    _, lag, p_in, p_out, n_in = best
    active = _active_cluster(turns, clusters, times - lag)

    def judge(c: int, contrast: np.ndarray) -> dict:
        order = np.argsort(-contrast)
        top = order[0]
        evidence_s = n_in[c] / fps
        entry = {
            "evidence_s": round(evidence_s, 1),
            "candidates": [
                {"name": names[i], "p_in": round(float(p_in[c, i]), 2), "contrast": round(float(contrast[i]), 2)}
                for i in order[:3]
            ],
        }
        if evidence_s >= MIN_EVIDENCE_S and p_in[c, top] >= MIN_P_IN and contrast[top] >= MIN_CONTRAST:
            entry["name"] = names[top]
            entry["confidence"] = round(float(contrast[top]), 2)
        elif p_in[c, top] >= HINT_P_IN and contrast[top] >= HINT_CONTRAST:
            entry["hint"] = names[top]
        return entry

    result = {cluster: judge(c, p_in[c] - p_out[c]) for c, cluster in enumerate(clusters)}

    # pyannote sometimes splits one person in two (e.g. muttering while sharing the screen).
    # The smaller part then looks weak, because that person's label is also lit while the
    # bigger part speaks. Second pass: leave out the clusters already named n when measuring
    # how often n is lit "while others speak".
    named = {}
    for c, cluster in enumerate(clusters):
        if "name" in result[cluster]:
            named.setdefault(names.index(result[cluster]["name"]), []).append(c)
    for c, cluster in enumerate(clusters):
        if "name" in result[cluster] or not named:
            continue
        contrast = p_in[c] - p_out[c]
        for n, same in named.items():
            others = (active >= 0) & (active != c) & ~np.isin(active, same)
            if others.any():
                contrast[n] = p_in[c, n] - lit[n, others].mean()
        retry = judge(c, contrast)
        if "name" in retry:
            retry["split_of"] = retry["name"]
            result[cluster] = retry
    return {"lag_s": float(lag), "clusters": result}


def speech_seconds(turns: list[dict]) -> Counter:
    total = Counter()
    for t in turns:
        total[t["speaker"]] += t["end"] - t["start"]
    return total


def resolve(turns: list[dict], video: dict | None, voice_matches: dict[str, dict]) -> dict:
    """Build the speakers.json content: one entry per cluster with a display name."""
    speech = speech_seconds(turns)
    first_seen = {}
    for t in turns:
        first_seen.setdefault(t["speaker"], t["start"])
    clusters = sorted(speech, key=lambda c: first_seen[c])

    speakers = {}
    unnamed = 0
    for cluster in clusters:
        v = (video or {}).get("clusters", {}).get(cluster, {})
        voice = voice_matches.get(cluster)
        entry = {"speech_s": round(speech[cluster], 1)}
        if "name" in v:
            entry.update(name=v["name"], source="video", confidence=v["confidence"])
        elif voice and voice.get("name"):
            entry.update(name=voice["name"], source="voice", confidence=voice["similarity"])
        else:
            unnamed += 1
            hint = v.get("hint") or (voice or {}).get("hint")
            label = f"Speaker {unnamed}"
            entry.update(name=f"{label} (forse: {hint})" if hint else label, source=None)
        if v:
            entry["video"] = {k: v[k] for k in ("evidence_s", "candidates")}
        if voice:
            entry["voice"] = voice
        speakers[cluster] = entry
    return speakers
