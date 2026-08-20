"""Query-budget regression test for wavelength path rebuilds (issue #48).

A rebuild pass used to run one full cable-chain walk per distinct
(module, grid_position) combination, re-issuing the same WdmLinePort,
WdmChannel, PortMapping, and cable lookups on every walk (~740 queries
for one node of a duplex CWDM mux pair). The per-pass read cache in
trace.TraceCache serves walks 2..N from memory, so the rebuild must stay
within a fixed query budget.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from netbox_wdm.testing import duplex_mux_pair
from netbox_wdm.trace import rebuild_wavelength_paths_for_node

# One node rebuild of a duplex_mux_pair measured ~740 queries before the
# per-pass read cache and ~150 after; the budget leaves headroom for noise
# while still failing clearly on any return to per-channel re-walking.
QUERY_BUDGET = 250


@pytest.mark.django_db(transaction=True)
def test_rebuild_query_count_stays_within_budget(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
    """rebuild_wavelength_paths_for_node must not re-walk the trunk per channel (issue #48)."""
    topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
    node = topo.bundles["mux_a"].node

    with CaptureQueriesContext(connection) as ctx:
        rebuild_wavelength_paths_for_node(node)

    count = len(ctx.captured_queries)
    assert count < QUERY_BUDGET, f"rebuild issued {count} queries (budget {QUERY_BUDGET})"
