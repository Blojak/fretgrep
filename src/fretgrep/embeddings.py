"""Semantic search over embedding vectors from an Ollama server.

Embeddings are ``auto_*`` data: they can be recomputed at any time. An
embedder is a plain function from texts to vectors, so tests and other
back ends can supply their own.
"""

import hashlib
import json
import math
import unicodedata
import urllib.error
import urllib.request
from array import array
from collections.abc import Callable, Iterable
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from fretgrep import search
from fretgrep.filename_parser import load_vocabulary
from fretgrep.models import AutoEmbedding, AutoFile, Recording

Embedder = Callable[[list[str]], list[list[float]]]

BATCH_SIZE = 16
TIMEOUT_S = 120
# Short, so that an address that does not answer barely delays a search.
PROBE_TIMEOUT_S = 1
RRF_K = 60
# How many hits of each ranking take part in the fusion.
CANDIDATES = 50


class EmbeddingError(RuntimeError):
    """The embedding server could not be reached or refused the request."""


def first_reachable(urls: list[str]) -> str | None:
    """Return the first address at which an Ollama server answers."""
    for url in urls:
        probe = url.rstrip("/") + "/api/version"
        try:
            with urllib.request.urlopen(probe, timeout=PROBE_TIMEOUT_S):
                return url
        except (OSError, ValueError):
            continue
    return None


def ollama_embedder(base_url: str, model: str) -> Embedder:
    """Return an embedder that calls ``/api/embed`` of an Ollama server."""
    url = base_url.rstrip("/") + "/api/embed"

    def embed(texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": model, "input": texts}).encode()
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                vectors = json.load(response)["embeddings"]
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace").strip()
            raise EmbeddingError(f"HTTP {error.code}: {detail}") from error
        except (OSError, ValueError, KeyError) as error:
            raise EmbeddingError(str(error)) from error
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"{len(texts)} Texte gesendet, {len(vectors)} Vektoren erhalten"
            )
        return vectors

    return embed


def document_text(recording: Recording) -> str:
    """Build the text that stands for one recording.

    Tag values carry their explanation from the vocabulary, so the model
    learns what a private abbreviation or name means.
    """
    path = PurePosixPath(unicodedata.normalize("NFC", recording.file.rel_path))
    descriptions = load_vocabulary().descriptions
    tags = [
        f"{value} ({descriptions[value]})" if value in descriptions else value
        for value in sorted({tag.value for tag in recording.tags})
    ]
    tags += sorted(tag.tag for tag in recording.user_tags)
    lines = [" ".join(path.with_suffix("").parts)]
    if tags:
        lines.append("Tags: " + ", ".join(tags))
    if recording.note:
        lines.append("Notiz: " + recording.note.text)
    if recording.transcript and recording.transcript.text:
        lines.append("Gesprochen: " + recording.transcript.text)
    return "\n".join(lines)


def text_hash(text: str) -> str:
    """Return the hash that identifies an embedded text."""
    return hashlib.sha256(text.encode()).hexdigest()


def pack(vector: Iterable[float]) -> bytes:
    """Store a vector as float32 bytes."""
    return array("f", vector).tobytes()


def unpack(data: bytes) -> array:
    """Read a vector stored by ``pack``."""
    vector = array("f")
    vector.frombytes(data)
    return vector


def pending(session: Session, model_name: str, redo: bool = False) -> list[Recording]:
    """Return the recordings whose vector is missing or outdated."""
    query = (
        select(Recording)
        .join(AutoFile)
        .options(*search.LOAD_ALL)
        .order_by(AutoFile.rel_path)
    )
    return [
        recording
        for recording in session.scalars(query)
        if redo
        or recording.embedding is None
        or recording.embedding.model != model_name
        or recording.embedding.text_hash != text_hash(document_text(recording))
    ]


def embed_recordings(
    session: Session,
    embed: Embedder,
    model_name: str,
    recordings: list[Recording],
    report: Callable[[int], None] = lambda _done: None,
) -> None:
    """Embed recordings in batches; ``report`` gets the running count.

    Each batch is committed on its own, so a run that fails halfway with
    an ``EmbeddingError`` can simply be started again.
    """
    for start in range(0, len(recordings), BATCH_SIZE):
        batch = recordings[start : start + BATCH_SIZE]
        texts = [document_text(recording) for recording in batch]
        for recording, text, vector in zip(batch, texts, embed(texts)):
            if recording.embedding is None:
                recording.embedding = AutoEmbedding()
            recording.embedding.model = model_name
            recording.embedding.text_hash = text_hash(text)
            recording.embedding.vector = pack(vector)
        session.commit()
        report(start + len(batch))


def _cosine(left, right) -> float:
    norm = math.sqrt(sum(x * x for x in left) * sum(y * y for y in right))
    return sum(x * y for x, y in zip(left, right)) / norm if norm else 0.0


def semantic_ids(
    session: Session, embed: Embedder, model_name: str, words: str, limit: int
) -> list[int]:
    """Return the ids of the recordings closest in meaning, closest first."""
    rows = session.execute(
        select(AutoEmbedding.recording_id, AutoEmbedding.vector).where(
            AutoEmbedding.model == model_name
        )
    ).all()
    if not rows:
        return []
    query = embed([words])[0]
    scored = sorted(
        (-_cosine(query, unpack(vector)), recording_id)
        for recording_id, vector in rows
    )
    return [recording_id for _score, recording_id in scored[:limit]]


def fuse(*rankings: list[int]) -> list[int]:
    """Merge rankings by reciprocal rank fusion, best first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, recording_id in enumerate(ranking, start=1):
            scores[recording_id] = scores.get(recording_id, 0.0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda item: (-scores[item], item))


def hybrid_search(
    session: Session, embed: Embedder, model_name: str, words: str, limit: int = 20
) -> list[Recording]:
    """Return the best recordings by keyword and meaning combined.

    A recording counts as a keyword hit if any of the words matches, so
    that whole sentences still reward literal hits such as a name.
    """
    pool = max(limit, CANDIDATES)
    by_keyword = search.search_ids(session, words, pool, match_all=False)
    by_meaning = semantic_ids(session, embed, model_name, words, pool)
    return search.load(session, fuse(by_keyword, by_meaning)[:limit])
