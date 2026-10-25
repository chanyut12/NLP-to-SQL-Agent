"""ExampleStore sync: the examples file is the only source of truth."""
import json

import numpy as np
import pytest

from core.data import rag_store


class _FakeEmbedder:
    """Deterministic stand-in so the test never loads the real model."""
    def encode(self, text):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.random(8)


@pytest.fixture
def make_store(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_store, "load_sentence_transformer", lambda name: _FakeEmbedder())
    path = tmp_path / "examples.json"

    def _make(examples):
        path.write_text(json.dumps({"examples": examples}), encoding="utf-8")
        return rag_store.ExampleStore(
            str(path), persist_directory=str(tmp_path / "db"), profile="t")

    return _make


def _ex(tags=None):
    ex = {"question": "q", "sql": "SELECT 1", "dialect": "postgresql"}
    if tags is not None:
        ex["retrieval_tags"] = tags
    return ex


def _ids(store):
    return set(store.collection.get(include=[])["ids"])


def test_changing_only_tags_replaces_the_stored_example(make_store):
    first = _ids(make_store([_ex(["เก่า"])]))
    second = _ids(make_store([_ex(["ใหม่"])]))
    assert len(first) == len(second) == 1
    assert first != second


def test_unchanged_examples_are_not_re_embedded(make_store):
    assert _ids(make_store([_ex(["a"])])) == _ids(make_store([_ex(["a"])]))


def test_example_without_tags_keeps_its_question_sql_id(make_store):
    from core.utils.common import generate_stable_id
    assert _ids(make_store([_ex()])) == {generate_stable_id("q", "SELECT 1")}
