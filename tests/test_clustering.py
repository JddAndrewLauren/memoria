"""Hierarchical clustering over the extraction's co-occurrence graph (#17)."""

import pytest

from memoria import clustering
from memoria.clustering import (
    BACKEND_LEIDEN,
    BACKEND_LOUVAIN,
    ClusteringUnavailable,
    CoOccurrence,
    cluster,
    cluster_id,
)


def _paired_graph(groups=8, members=3):
    """Groups whose members co-occur constantly, paired by a weaker link.

    Two real scales, which is what a hierarchy needs in order to have anything
    to nest.
    """
    nodes = [f"g{group}p{index}" for group in range(groups) for index in range(members)]
    links = []
    for group in range(groups):
        inside = [f"g{group}p{index}" for index in range(members)]
        for i, left in enumerate(inside):
            for right in inside[i + 1 :]:
                links.append(CoOccurrence(left, right, 3))
    for group in range(0, groups, 2):
        for index in range(members):
            links.append(
                CoOccurrence(f"g{group}p{index}", f"g{group + 1}p{index}", 1)
            )
    return nodes, links


def test_the_louvain_fallback_produces_a_nesting(tmp_path):
    """The backend most installs will actually run.

    `graspologic-native` is kept out of the `dev` extra so this path is the
    one the suite exercises - the hierarchy here is hand-built from Louvain's
    dendrogram, which is where the subtle part is.
    """
    nodes, links = _paired_graph()

    assignments, backend = cluster(nodes, links)

    assert backend == BACKEND_LOUVAIN
    levels = {assignment.level for assignment in assignments}
    assert len(levels) > 1
    assert any(assignment.parent_members for assignment in assignments)


def test_every_finer_cluster_is_contained_by_its_parent():
    """What nesting means. A parent that does not contain its child would make
    "a broad cluster contains narrower ones" false while still typechecking."""
    nodes, links = _paired_graph()

    assignments, _ = cluster(nodes, links)

    for assignment in assignments:
        if assignment.parent_members:
            assert set(assignment.members) <= set(assignment.parent_members)


def test_leiden_is_used_when_it_is_importable(monkeypatch):
    """The preferred backend, exercised without the wheel installed.

    `_leiden_backend` is a function rather than a module-level import for
    exactly this: keeping `graspologic-native` out of `dev` should leave the
    Leiden branch unrun, not untested.
    """
    calls = []

    class _Entry:
        def __init__(self, level, community, node):
            self.level, self.cluster, self.node = level, community, node

    def fake_hierarchical_leiden(links, **kwargs):
        calls.append(kwargs)
        return None, [
            _Entry(0, "a", "x"),
            _Entry(0, "a", "y"),
            _Entry(0, "b", "z"),
        ]

    monkeypatch.setattr(clustering, "_leiden_backend", lambda: fake_hierarchical_leiden)

    assignments, backend = cluster(
        ["x", "y", "z"], [CoOccurrence("x", "y", 2), CoOccurrence("y", "z", 1)]
    )

    assert backend == BACKEND_LEIDEN
    assert calls, "the backend was actually called"
    assert {assignment.members for assignment in assignments} == {("x", "y"), ("z",)}


def test_clustering_without_a_backend_says_so_rather_than_crashing(monkeypatch):
    """The core is installable with PyYAML alone, and an extraction with
    candidates but no clusters is diminished rather than broken."""
    monkeypatch.setattr(clustering, "_leiden_backend", lambda: None)
    monkeypatch.setattr(clustering, "_louvain_backend", lambda: None)

    with pytest.raises(ClusteringUnavailable, match="graph"):
        cluster(["x", "y"], [CoOccurrence("x", "y", 1)])


def test_cluster_ids_are_derived_from_membership_not_position():
    """A stable partition has to yield stable ids, because a cluster whose
    members have not changed keeps the summary somebody paid a model for."""
    assert cluster_id(0, ["b", "a"]) == cluster_id(0, ["a", "b"])
    assert cluster_id(0, ["a", "b"]) != cluster_id(1, ["a", "b"])
    assert cluster_id(0, ["a", "b"]) != cluster_id(0, ["a", "c"])


def test_clustering_is_deterministic_under_a_fixed_seed():
    nodes, links = _paired_graph()

    first, _ = cluster(nodes, links, seed=7)
    second, _ = cluster(nodes, links, seed=7)

    assert first == second


def test_a_node_with_no_co_occurrence_is_still_a_cluster_of_one():
    """Something the archive mentions repeatedly but never beside anything
    else is a real finding. Dropping it would be the index deciding what is
    interesting."""
    assignments, _ = cluster(["lonely"], [])

    assert [assignment.members for assignment in assignments] == [("lonely",)]


def test_a_co_occurrence_is_undirected_and_counted_once():
    """The extraction emits ordered pairs; this is the one place that has to
    stop caring about the order."""
    weights = clustering._weight_map(
        ["a", "b"], [CoOccurrence("a", "b", 2), CoOccurrence("b", "a", 3)]
    )

    assert weights == {("a", "b"): 5}


def test_a_link_to_an_unknown_node_is_ignored():
    weights = clustering._weight_map(["a"], [CoOccurrence("a", "ghost", 4)])

    assert weights == {}
