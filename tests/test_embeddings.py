"""Tests for the semantic search, with a stand-in for the embedding model."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import json
import urllib.error

import pytest
from sqlalchemy import select

from fretgrep import config, embeddings, search, user_meta
from fretgrep.filename_parser import load_vocabulary
from fretgrep.models import AutoEmbedding, Recording
from fretgrep.scanner import scan_library

NAMES = ["251 moll chet baker.mp3", "blues in F wes.mp3", "bossa akkorde.mp3"]

# One axis per topic; a text points along every topic it mentions.
TOPICS = [("baker", "trompete"), ("blues", "traurig"), ("bossa", "brasilien")]


class FakeEmbedder:
    """Maps texts to topic vectors and records the batches it was given."""

    def __init__(self):
        self.calls = []

    def __call__(self, texts):
        self.calls.append(texts)
        return [
            [float(any(word in text.lower() for word in topic)) for topic in TOPICS]
            for text in texts
        ]


@pytest.fixture
def scanned(session, library):
    """Return a session with a scanned and indexed small library."""
    for number, name in enumerate(NAMES):
        (library / name).write_bytes(bytes([number]))
    scan_library(session, library)
    search.rebuild(session)
    session.commit()
    return session


def embed_all(session, embed, model_name="fake", **options):
    todo = embeddings.pending(session, model_name, **options)
    embeddings.embed_recordings(session, embed, model_name, todo)
    return len(todo)


def names(recordings):
    return [recording.file.filename_norm for recording in recordings]


def test_vectors_are_stored_once(scanned):
    embed = FakeEmbedder()

    assert embed_all(scanned, embed) == 3
    assert embed_all(scanned, embed) == 0

    rows = scanned.scalars(select(AutoEmbedding)).all()
    assert {row.model for row in rows} == {"fake"}
    assert sorted(list(embeddings.unpack(row.vector)) for row in rows) == [
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0],
    ]
    assert len(embed.calls) == 1


def test_changed_text_or_model_makes_vector_outdated(scanned):
    embed = FakeEmbedder()
    embed_all(scanned, embed)
    recording = scanned.scalars(select(Recording)).first()

    user_meta.set_note(recording, "klingt nach Brasilien")
    scanned.commit()

    assert embeddings.pending(scanned, "fake") == [recording]
    assert embed_all(scanned, embed) == 1
    assert "Notiz: klingt nach Brasilien" in embed.calls[-1][0]
    assert len(embeddings.pending(scanned, "other-model")) == 3
    assert embed_all(scanned, embed, redo=True) == 3
    assert scanned.scalars(select(AutoEmbedding)).all()[0].model == "fake"


def test_document_text_explains_tags_from_the_vocabulary(session, library):
    (library / "251 looper hm5 wes.mp3").write_bytes(b"x")
    scan_library(session, library)
    recording = session.scalars(select(Recording)).one()
    user_meta.add_tags(recording, ["lieblingslick"])

    lines = embeddings.document_text(recording).splitlines()

    assert lines[0] == "251 looper hm5 wes"
    assert lines[1].startswith("Tags: hm5 (Harmonisch-Moll-5")
    assert lines[1].endswith(
        "), ii-V-I, looper (mehrere Spuren übereinander), wes montgomery, "
        "lieblingslick"
    )


def test_every_description_belongs_to_a_vocabulary_value():
    vocabulary = load_vocabulary()

    assert vocabulary.descriptions
    assert set(vocabulary.descriptions) <= {alias.value for alias in vocabulary.aliases}


def test_batches(scanned, monkeypatch):
    monkeypatch.setattr(embeddings, "BATCH_SIZE", 2)
    embed = FakeEmbedder()
    counts = []
    todo = embeddings.pending(scanned, "fake")

    embeddings.embed_recordings(scanned, embed, "fake", todo, report=counts.append)

    assert [len(call) for call in embed.calls] == [2, 1]
    assert counts == [2, 3]


def test_failed_batch_keeps_earlier_batches(scanned, monkeypatch):
    monkeypatch.setattr(embeddings, "BATCH_SIZE", 2)
    calls = []

    def embed(texts):
        calls.append(texts)
        if len(calls) == 2:
            raise embeddings.EmbeddingError("weg")
        return FakeEmbedder()(texts)

    with pytest.raises(embeddings.EmbeddingError):
        embed_all(scanned, embed)

    assert len(embeddings.pending(scanned, "fake")) == 1


def test_semantic_ids_rank_by_meaning(scanned):
    embed = FakeEmbedder()
    embed_all(scanned, embed)

    ids = embeddings.semantic_ids(scanned, embed, "fake", "traurig", 3)

    assert names(search.load(scanned, ids))[0] == "blues in F wes"
    assert len(embeddings.semantic_ids(scanned, embed, "fake", "traurig", 1)) == 1
    assert not embeddings.semantic_ids(scanned, embed, "other-model", "traurig", 3)


def test_fuse_prefers_hits_of_both_rankings():
    assert embeddings.fuse([1, 2, 3], [3, 4]) == [3, 1, 2, 4]
    assert embeddings.fuse([], [5, 6]) == [5, 6]


def test_hybrid_search_finds_what_keywords_miss(scanned):
    embed = FakeEmbedder()
    embed_all(scanned, embed)

    assert not search.search(scanned, "trompete")
    found = embeddings.hybrid_search(scanned, embed, "fake", "trompete", limit=1)
    assert names(found) == ["251 moll chet baker"]

    # "wes" means nothing to the fake model; the keyword hit decides.
    found = embeddings.hybrid_search(scanned, embed, "fake", "wes")
    assert names(found)[0] == "blues in F wes"
    assert len(found) == 3


def test_hybrid_search_rewards_literal_hits_in_sentences(scanned):
    embed = FakeEmbedder()
    embed_all(scanned, embed)

    # The meaning points at the bossa, the literal "wes" at the blues.
    found = embeddings.hybrid_search(scanned, embed, "fake", "brasilien wes", 2)

    assert set(names(found)) == {"blues in F wes", "bossa akkorde"}


def test_hybrid_search_without_vectors_is_keyword_search(scanned):
    found = embeddings.hybrid_search(scanned, FakeEmbedder(), "fake", "baker")

    assert names(found) == ["251 moll chet baker"]


class FakeResponse:
    """Stand-in for the object returned by urlopen."""

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, *_args):
        return self.payload


def test_ollama_embedder_request_and_response(monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)
        seen["timeout"] = timeout
        return FakeResponse({"embeddings": [[1.0, 2.0], [3.0, 4.0]]})

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", urlopen)
    embed = embeddings.ollama_embedder("http://host:1/", "some-model")

    assert embed(["a", "b"]) == [[1.0, 2.0], [3.0, 4.0]]
    assert seen["url"] == "http://host:1/api/embed"
    assert seen["body"] == {"model": "some-model", "input": ["a", "b"]}
    assert seen["timeout"] == embeddings.TIMEOUT_S


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("unreachable"),
        FakeResponse({"error": "no embeddings"}),
        FakeResponse({"embeddings": [[1.0]]}),
    ],
)
def test_ollama_embedder_errors(monkeypatch, failure):
    def urlopen(_request, timeout):  # pylint: disable=unused-argument
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", urlopen)

    with pytest.raises(embeddings.EmbeddingError):
        embeddings.ollama_embedder("http://host:1", "m")(["a", "b"])


def test_first_reachable_skips_addresses_that_do_not_answer(monkeypatch):
    asked = []

    def urlopen(url, timeout):
        asked.append((url, timeout))
        if "down" in url:
            raise urllib.error.URLError("Connection refused")
        return FakeResponse({"version": "1"})

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", urlopen)

    assert embeddings.first_reachable(["http://down:1", "http://up:2/"]) == (
        "http://up:2/"
    )
    assert asked[1] == ("http://up:2/api/version", embeddings.PROBE_TIMEOUT_S)
    assert embeddings.first_reachable(["http://down:1"]) is None


def test_ollama_urls_put_configured_addresses_first(monkeypatch):
    monkeypatch.delenv(config.ENV_OLLAMA_URL, raising=False)
    assert config.ollama_urls() == list(config.DEFAULT_OLLAMA_URLS)

    monkeypatch.setenv(
        config.ENV_OLLAMA_URL, "http://host:1/, http://localhost:11434"
    )
    assert config.ollama_urls() == [
        "http://host:1",
        "http://localhost:11434",
        "http://192.168.122.1:11434",
    ]
