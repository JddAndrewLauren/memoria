"""The default embedder's assumed dimension (#155, ADR-0007).

`memoria.embeddings.EMBEDDING_DIMENSIONS` is a hand-copied number the
`paragraph_vectors` table is declared with; nothing verifies it still
matches `EMBEDDING_MODEL_NAME` itself. `fastembed`'s model registry reports
a model's vector width from its own offline metadata - no weights
downloaded, no network - so that claim is checkable without running
`default_embed_fn`, which this suite must never call (see
`memoria.embeddings`'s own docstring).
"""

import socket

import pytest

from memoria.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME


def test_the_assumed_dimension_matches_what_fastembed_reports_offline(monkeypatch):
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        pytest.skip(f"fastembed is not installed: {exc}")

    def _blocked(*args, **kwargs):
        raise AssertionError("reading the model registry touched the network")

    monkeypatch.setattr(socket, "socket", _blocked)

    try:
        reported = TextEmbedding.get_embedding_size(EMBEDDING_MODEL_NAME)
    except Exception as exc:
        pytest.skip(
            f"fastembed cannot report {EMBEDDING_MODEL_NAME}'s dimension offline: {exc}"
        )

    assert reported == EMBEDDING_DIMENSIONS
