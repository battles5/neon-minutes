"""Local voice library: speaker embeddings of people identified in past meetings.

Each person keeps one embedding per (meeting, cluster) that was named by video or
by hand, so re-running a meeting replaces its own entries instead of piling up.
"""

import json
from pathlib import Path

import numpy as np

# Cosine similarity of pyannote community-1 embeddings. Across the two test stand-ups the
# same person scored 0.84-0.94 and every other voice below 0.1.
MATCH_SIMILARITY = 0.6
HINT_SIMILARITY = 0.45
MIN_SPEECH_S = 10.0


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) + 1e-9)


class VoiceLibrary:
    def __init__(self, path: Path):
        self.path = path
        self.people: dict[str, dict[str, list[float]]] = {}
        if path.exists():
            self.people = json.loads(path.read_text(encoding="utf-8")).get("people", {})

    def _centroids(self, exclude_meeting: str | None = None) -> dict[str, np.ndarray]:
        centroids = {}
        for name, entries in self.people.items():
            vecs = [_unit(e) for key, e in entries.items() if key.split("|")[0] != exclude_meeting]
            if vecs:
                centroids[name] = _unit(np.mean(vecs, axis=0))
        return centroids

    def match(self, embeddings: dict[str, list[float]], meeting_id: str) -> dict[str, dict]:
        """Best library match for every cluster embedding, ignoring this meeting's own entries."""
        centroids = self._centroids(exclude_meeting=meeting_id)
        if not centroids:
            return {}
        names = list(centroids)
        matrix = np.stack([centroids[n] for n in names])
        matches = {}
        for cluster, emb in embeddings.items():
            sims = matrix @ _unit(emb)
            i = int(np.argmax(sims))
            sim = round(float(sims[i]), 3)
            entry = {"best": names[i], "similarity": sim}
            if sim >= MATCH_SIMILARITY:
                entry["name"] = names[i]
            elif sim >= HINT_SIMILARITY:
                entry["hint"] = names[i]
            matches[cluster] = entry
        return matches

    def update(self, meeting_id: str, speakers: dict, embeddings: dict[str, list[float]]) -> list[str]:
        """Store embeddings of clusters named by video or by hand; return the names learned."""
        for entries in self.people.values():
            for key in [k for k in entries if k.split("|")[0] == meeting_id]:
                del entries[key]
        learned = []
        for cluster, info in speakers.items():
            if info.get("source") not in ("video", "manual") or cluster not in embeddings:
                continue
            if info.get("speech_s", 0) < MIN_SPEECH_S:
                continue
            self.people.setdefault(info["name"], {})[f"{meeting_id}|{cluster}"] = embeddings[cluster]
            learned.append(info["name"])
        self.people = {n: e for n, e in self.people.items() if e}
        return learned

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"people": self.people}, ensure_ascii=False), encoding="utf-8")
