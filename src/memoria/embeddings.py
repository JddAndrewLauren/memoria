"""The one embedder `memoria.index`'s semantic table is built and searched
with (#81, ADR-0007).

**A seam with exactly one implementation.** Nothing here is user-configurable
and there is no second backend to pick between - `bge-small-en-v1.5` through
`fastembed` is the whole of it, pinned by name here and by version in
`pyproject.toml`, exactly as ADR-0007 settles. What this module offers a
caller is not a choice of model but a *substitution point*: every function
that needs an embedder takes one as a plain callable (`EmbedFn`) rather than
importing this module and calling it directly, so a test can hand it a
deterministic fake instead - see `memoria.index.build_index`,
`memoria.index.rebuild` and `memoria.index.search_semantic`. **Tests must
never call `default_embed_fn` itself**: the first call to `fastembed`'s
`TextEmbedding` downloads the model's ONNX weights from the Hugging Face
Hub, which needs network and is not deterministic in a sandboxed test run.

**CPU ONNX, not torch.** `fastembed` runs the model through `onnxruntime`;
nothing here imports `torch` or asks for a GPU, which is what lets this run
unattended on the production machine (ADR-0007: "production has no GPU").

Imported lazily inside `default_embed_fn`, not at module scope, for the same
reason `memoria.clustering` lazy-imports `networkx`: importing this module -
which `memoria.index` does unconditionally, so every CLI invocation and
every test collecting `memoria.index` pulls it in - must not cost the
`onnxruntime`/`numpy`/`tokenizers` import chain when nothing here is
actually called.
"""

from __future__ import annotations

from typing import Callable, Sequence

# Pinned by name (the version lives in `pyproject.toml`, beside `sqlite-vec`'s
# own pin - both are named in ADR-0007). `fastembed`'s own model registry
# reports this name's vector width as 384; `EMBEDDING_DIMENSIONS` is that
# number, not a guess, and `memoria.index`'s `paragraph_vectors` table is
# declared with it.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

# A batch of paragraph texts in, one vector per text out, same order - the
# shape both `default_embed_fn` and every test fake honour.
EmbedFn = Callable[[Sequence[str]], list[list[float]]]


def default_embed_fn(texts: Sequence[str]) -> list[list[float]]:
    """The one production embedder: `EMBEDDING_MODEL_NAME` through
    `fastembed`, run once over the whole batch handed to it.

    Never called with cluster summaries - `memoria.index.build_index` only
    ever collects real paragraph text, never a `memo` row's `[inferred]`
    text, so nothing here has to refuse one (the refusal that matters is
    upstream, at the collection point).
    """
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME)
    return [vector.tolist() for vector in model.embed(list(texts))]
