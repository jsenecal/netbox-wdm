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
# per-pass read cache and ~150 after. Delegating traversal to core's
# CablePath walker (issue #49) re-based it to ~330: core walks further than
# the hand-rolled version it replaced -- on through the far mux's channel
# front ports -- and resolves cable profiles and positions on the way.
# Measured on that change: 273 queries for the walks themselves and 56 for
# the loop/hop pre-scan that keeps core off a cabling loop.
#
# The budget still does its job. It guards against re-walking the trunk
# once per channel, which costs an order of magnitude more (~10 grid
# positions x 4 walks), not the tens of queries between these figures.
QUERY_BUDGET = 400


@pytest.mark.django_db(transaction=True)
def test_rebuild_query_count_stays_within_budget(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles):
    """rebuild_wavelength_paths_for_node must not re-walk the trunk per channel (issue #48)."""
    topo = duplex_mux_pair(wdm_site, dt_cwdm_dx, dt_pp, wdm_roles)
    node = topo.bundles["mux_a"].node

    with CaptureQueriesContext(connection) as ctx:
        rebuild_wavelength_paths_for_node(node)

    count = len(ctx.captured_queries)
    assert count < QUERY_BUDGET, f"rebuild issued {count} queries (budget {QUERY_BUDGET})"
