"""Hierarchical clustering over the extraction's co-occurrence graph.

ADR-0005 build shape 1: clusters are **hierarchical**, computed by Leiden
over the graph of things the extraction placed together, so that Themes are
proposed at several grains rather than one. `graspologic-native` is the
preferred backend; when its wheel is not installed, a recursive networkx
Louvain produces the same nesting a level at a time.

This module is deliberately **pure**. It takes node refs and weights and
returns assignments; it opens no database, holds no ``Repository``, and knows
nothing about entries, candidates or paragraphs. Two reasons, and both are
load-bearing:

- it is the only part of the extraction with an optional third-party
  dependency, so isolating it means ``import memoria.extraction`` never pulls
  networkx in and the core stays installable with PyYAML alone;
- a partition algorithm is where the subtle bugs live, and pure functions
  over small dataclasses are the cheapest possible thing to test.

**Vocabulary.** ``networkx``'s own API says ``add_edge``, which is
unavoidable third-party wording; every name chosen here stays off
CONTEXT.md's avoid list, so a link between two nodes is a
``CoOccurrence`` with a ``weight``, never an edge, and a cluster's contents
are its ``members``, never a community.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Sequence

# The backend names recorded in `extraction_meta.clustering_backend`, so a
# surface reporting clusters can say what computed them - two machines with
# different backends installed will not agree on a partition, and that is
# worth being able to see rather than worth pretending away.
BACKEND_LEIDEN = "leiden"
BACKEND_LOUVAIN = "louvain"
BACKEND_UNAVAILABLE = "unavailable"

# How large a cluster may get before it is split again into a finer level.
# GraphRAG's own default, and the knob that decides how deep the nesting
# goes rather than how many clusters there are.
MAX_CLUSTER_SIZE = 10


class ClusteringUnavailable(Exception):
    """No clustering backend is installed.

    Not an error the caller should die on: the core is installable without
    the ``graph`` extra, and an extraction that produces placements and
    candidates but no clusters is a diminished result rather than a broken
    one. ``extraction.derive`` catches this and records
    ``clustering_backend = 'unavailable'``.
    """


@dataclass(frozen=True)
class CoOccurrence:
    """Two nodes placed in the same paragraph, and how often.

    ``weight`` is a count of paragraphs, not of relations. Relations are
    carried separately and used only for labelling: they are a strict subset
    of co-occurrences, so weighting by them as well would just amplify
    whatever the model happened to phrase as a relation rather than as a
    plain co-mention.
    """

    from_ref: str
    to_ref: str
    weight: int


@dataclass(frozen=True)
class ClusterAssignment:
    """One cluster the backend proposed.

    ``level`` counts down from the broadest partition at 0. ``parent_members``
    is the member set of the cluster this one refines, or ``None`` at level 0;
    the caller resolves that to a parent id, because ids are derived from
    membership (see ``cluster_id``) and this module does not need to know it.
    """

    level: int
    members: tuple[str, ...]
    parent_members: tuple[str, ...] | None


def cluster_id(level: int, members: Sequence[str]) -> str:
    """The stable id for a cluster at ``level`` holding ``members``.

    Derived from the membership, never from position in a list. Two
    consequences the rest of the extraction depends on: a re-run that lands
    on the same partition produces the same ids, and a cluster whose members
    have not changed keeps its summary - because the summary is memoized on
    the membership rather than on the id.
    """
    digest = hashlib.sha1(
        ("\n".join([str(level), *sorted(members)])).encode("utf-8")
    ).hexdigest()
    return f"CL-{digest[:12]}"


def cluster(
    nodes: Sequence[str],
    co_occurrences: Sequence[CoOccurrence],
    *,
    seed: int = 0,
    max_cluster_size: int = MAX_CLUSTER_SIZE,
) -> tuple[list[ClusterAssignment], str]:
    """Partition ``nodes`` hierarchically. Returns the assignments and the
    backend name that produced them.

    Deterministic under a fixed seed *and* a fixed backend. It is not
    deterministic across backends, and cannot be: a machine with the Leiden
    wheel and one without will read the same memo cache and propose different
    clusters. That is why the backend name comes back out of here and is
    recorded - "regenerates identically" is a claim about one process, not
    about two machines.

    A node with no co-occurrence at all is still a cluster of one at level 0,
    rather than being dropped. A thing the archive mentions repeatedly but
    never beside anything else is a real finding, and silently discarding it
    would be the index deciding what is interesting.
    """
    backend = _backend_name()
    if not nodes:
        return [], backend or BACKEND_UNAVAILABLE
    if backend is None:
        raise ClusteringUnavailable(
            "no clustering backend is installed - install the `graph` extra "
            "(`pip install -e '.[graph]'`) for networkx Louvain, or "
            "`graspologic-native` for Leiden"
        )

    ordered_nodes = sorted(set(nodes))
    weights = _weight_map(ordered_nodes, co_occurrences)

    if backend == BACKEND_LEIDEN:
        assignments = _leiden(ordered_nodes, weights, seed, max_cluster_size)
    else:
        assignments = _louvain(ordered_nodes, weights, seed, max_cluster_size)
    return assignments, backend


def _weight_map(
    nodes: Sequence[str], co_occurrences: Sequence[CoOccurrence]
) -> dict[tuple[str, str], int]:
    """Co-occurrences as an undirected, deduplicated weight map.

    A pair is keyed by its sorted ends, so a graph carrying both
    ``(bob, carol)`` and ``(carol, bob)`` weights the pair once - the
    extraction emits ordered pairs and this is the one place that has to stop
    caring about the order.
    """
    known = set(nodes)
    weights: dict[tuple[str, str], int] = {}
    for link in co_occurrences:
        if link.from_ref == link.to_ref:
            continue
        if link.from_ref not in known or link.to_ref not in known:
            continue
        key = (
            (link.from_ref, link.to_ref)
            if link.from_ref < link.to_ref
            else (link.to_ref, link.from_ref)
        )
        weights[key] = weights.get(key, 0) + link.weight
    return weights


# --- backend selection -------------------------------------------------------


def _leiden_backend() -> Callable | None:
    """``graspologic_native.hierarchical_leiden``, or ``None``.

    A function rather than a module-level ``try: import`` so a test can
    monkeypatch it and exercise the Leiden branch without the wheel installed.
    That matters here more than usual: `pyproject.toml` keeps
    `graspologic-native` out of the `dev` extra on purpose, so that the suite
    exercises the fallback most installs actually run - and this is what stops
    that choice from leaving the Leiden branch untested rather than merely
    unrun.
    """
    try:
        from graspologic_native import hierarchical_leiden
    except ImportError:
        return None
    return hierarchical_leiden


def _louvain_backend() -> Callable | None:
    """``networkx.algorithms.community.louvain_communities``, or ``None``."""
    try:
        from networkx.algorithms.community import louvain_communities
    except ImportError:
        return None
    return louvain_communities


def _backend_name() -> str | None:
    if _leiden_backend() is not None:
        return BACKEND_LEIDEN
    if _louvain_backend() is not None:
        return BACKEND_LOUVAIN
    return None


# --- the two backends --------------------------------------------------------


def _leiden(
    nodes: Sequence[str],
    weights: dict[tuple[str, str], int],
    seed: int,
    max_cluster_size: int,
) -> list[ClusterAssignment]:
    """Hierarchical Leiden, which already returns levels of its own."""
    hierarchical_leiden = _leiden_backend()
    links = [
        (left, right, float(weight)) for (left, right), weight in sorted(weights.items())
    ]
    if not links:
        return _singletons(nodes)
    _, partitions = hierarchical_leiden(
        links,
        starting_communities=None,
        resolution=1.0,
        randomness=0.001,
        iterations=1,
        use_modularity=True,
        seed=seed,
        max_cluster_size=max_cluster_size,
    )
    # graspologic reports one row per node per level; regroup into member sets
    # and hand the parent relation back as a member set too, so this backend
    # and the fallback return the same shape.
    by_level: dict[int, dict[str, list[str]]] = {}
    for entry in partitions:
        by_level.setdefault(entry.level, {}).setdefault(entry.cluster, []).append(
            entry.node
        )
    return _as_assignments(
        [
            [tuple(sorted(members)) for _, members in sorted(clusters.items())]
            for _, clusters in sorted(by_level.items())
        ],
        nodes,
    )


def _louvain(
    nodes: Sequence[str],
    weights: dict[tuple[str, str], int],
    seed: int,
    max_cluster_size: int,
) -> list[ClusterAssignment]:
    """Louvain's own dendrogram, broadest level first, then split what is
    still too large.

    ``louvain_partitions`` yields the partition after each pass of the
    algorithm, finest first: pass 0 finds the tightest groups, and each later
    pass merges them. Reversed, that *is* the nesting - level 0 the broadest,
    each finer level strictly refining the one above, with containment
    guaranteed by construction rather than inferred.

    This is not what a first attempt does. Calling ``louvain_communities`` and
    re-partitioning oversized clusters looks equivalent and is not: that
    function returns only the finest partition, so on a graph whose natural
    communities are already small it returns one flat level and the hierarchy
    never appears - clusters would carry a level of 0 and no parent, on every
    archive. The dendrogram was there the whole time.

    ``max_cluster_size`` still does a job at the bottom: a cluster the
    dendrogram leaves larger than the limit is partitioned again over the
    links wholly inside it, adding one more level. A cluster Louvain cannot
    break up (a clique has no finer structure) ends that branch rather than
    recursing forever.
    """
    import networkx as nx
    from networkx.algorithms.community import louvain_partitions

    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    for (left, right), weight in weights.items():
        graph.add_edge(left, right, weight=weight)

    passes = list(louvain_partitions(graph, weight="weight", seed=seed))
    levels: list[list[tuple[str, ...]]] = [
        _ordered(groups) for groups in reversed(passes)
    ]

    # Refine whatever the dendrogram left oversized.
    while levels:
        oversized = [
            members for members in levels[-1] if len(members) > max_cluster_size
        ]
        if not oversized:
            break
        finer: list[tuple[str, ...]] = []
        for members in oversized:
            inside = set(members)
            subgraph = nx.Graph()
            subgraph.add_nodes_from(members)
            for (left, right), weight in weights.items():
                if left in inside and right in inside:
                    subgraph.add_edge(left, right, weight=weight)
            split = _ordered(
                nx.community.louvain_communities(subgraph, weight="weight", seed=seed)
            )
            if len(split) > 1:
                finer.extend(split)
        if not finer:
            break
        # Clusters already small enough carry down unchanged, so every level
        # is a partition of the whole node set and containment still holds.
        kept = [
            members for members in levels[-1] if len(members) <= max_cluster_size
        ]
        levels.append(_ordered(kept + finer))
    return _as_assignments(levels, nodes)


def _ordered(groups) -> list[tuple[str, ...]]:
    """Member sets in a stable order - largest first, then lexical."""
    return sorted(
        (tuple(sorted(group)) for group in groups if group),
        key=lambda group: (-len(group), group),
    )


def _as_assignments(
    levels: Sequence[Sequence[tuple[str, ...]]], nodes: Sequence[str]
) -> list[ClusterAssignment]:
    """Turn per-level member sets into assignments, resolving each cluster's
    parent by containment.

    A cluster's parent is the smallest cluster one level up that contains all
    of its members. Containment rather than a reported parent id, because the
    two backends disagree about what they report and containment is what the
    nesting actually means.
    """
    if not levels:
        return _singletons(nodes)
    assignments: list[ClusterAssignment] = []
    for level, clusters in enumerate(levels):
        parents = levels[level - 1] if level else None
        for members in clusters:
            parent_members = None
            if parents is not None:
                containing = [
                    candidate
                    for candidate in parents
                    if set(members) <= set(candidate)
                ]
                if containing:
                    parent_members = min(containing, key=lambda group: (len(group), group))
            assignments.append(
                ClusterAssignment(
                    level=level, members=members, parent_members=parent_members
                )
            )
    return assignments


def _singletons(nodes: Sequence[str]) -> list[ClusterAssignment]:
    """One cluster per node, at level 0 - what an unconnected graph means."""
    return [
        ClusterAssignment(level=0, members=(node,), parent_members=None)
        for node in sorted(nodes)
    ]
