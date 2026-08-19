"""Tests for per-transaction deduplication of scheduled rebuild work."""

from collections import Counter

import pytest

from netbox_wdm.testing import create_duplex_mux


@pytest.fixture
def rebuild_counter(monkeypatch):
    """Count rebuild_wavelength_paths_for_node calls by node, without doing the work."""
    import netbox_wdm.trace as trace_mod

    calls: Counter = Counter()
    monkeypatch.setattr(
        trace_mod,
        "rebuild_wavelength_paths_for_node",
        lambda node, *args, **kwargs: calls.update([node.pk]),
    )
    return calls


@pytest.mark.django_db
def test_rebuild_runs_once_per_node_per_transaction(
    wdm_site, dt_cwdm_dx, wdm_roles, rebuild_counter, django_capture_on_commit_callbacks
):
    """Regression test for issue #48: building a node schedules many rebuilds but must run one.

    Channel, line port and port mapping signals each scheduled their own
    on_commit rebuild, so populating a single MUX rebuilt the same node once per
    created object.
    """
    with django_capture_on_commit_callbacks(execute=True):
        create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "DEDUP-MUX-A")

    assert rebuild_counter, "expected at least one rebuild to be scheduled"
    assert max(rebuild_counter.values()) == 1, f"node rebuilt more than once: {dict(rebuild_counter)}"


@pytest.mark.django_db
def test_rebuild_covers_every_affected_node(
    wdm_site, dt_cwdm_dx, wdm_roles, rebuild_counter, django_capture_on_commit_callbacks
):
    """Deduplication must not drop nodes: two nodes touched in one transaction both rebuild."""
    with django_capture_on_commit_callbacks(execute=True):
        mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "DEDUP-MUX-B")
        mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "DEDUP-MUX-C")

    assert set(rebuild_counter) == {mux_a.node.pk, mux_b.node.pk}
    assert max(rebuild_counter.values()) == 1


@pytest.mark.django_db
def test_pending_rebuilds_do_not_leak_between_transactions(
    wdm_site, dt_cwdm_dx, wdm_roles, rebuild_counter, django_capture_on_commit_callbacks
):
    """A flushed transaction must not re-rebuild its nodes when a later one commits."""
    with django_capture_on_commit_callbacks(execute=True):
        mux_a = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "DEDUP-MUX-D")
    rebuild_counter.clear()

    with django_capture_on_commit_callbacks(execute=True):
        mux_b = create_duplex_mux(wdm_site, dt_cwdm_dx, wdm_roles["wdm-mux"], "DEDUP-MUX-E")

    assert mux_a.node.pk not in rebuild_counter, "nodes from an earlier transaction were rebuilt again"
    assert set(rebuild_counter) == {mux_b.node.pk}
