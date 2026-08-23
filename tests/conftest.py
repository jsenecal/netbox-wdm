"""Shared pytest fixtures using the testing package."""

import django
import pytest
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.DJANGO_SETTINGS_MODULE = "netbox.settings"
        django.setup()


from dataclasses import dataclass, field  # noqa: E402
from itertools import count  # noqa: E402
from typing import Any  # noqa: E402

from netbox_wdm.testing import (  # noqa: E402
    create_cwdm_mux_dx_type,
    create_cwdm_mux_sf_type,
    create_device_roles,
    create_dwdm_mux_dx_type,
    create_fiber_pp_type,
    create_manufacturer,
    create_roadm_2d_type,
    create_site,
    duplex_mux_pair,
    mux_roadm_mux,
    sf_mux_pair,
)


@pytest.fixture
def wdm_site():
    return create_site("Test Site")


@pytest.fixture
def wdm_manufacturer():
    return create_manufacturer("Test Vendor")


@pytest.fixture
def wdm_roles():
    return create_device_roles()


@pytest.fixture
def dt_cwdm_dx(wdm_manufacturer):
    return create_cwdm_mux_dx_type(wdm_manufacturer)


@pytest.fixture
def dt_cwdm_sf(wdm_manufacturer):
    return create_cwdm_mux_sf_type(wdm_manufacturer)


@pytest.fixture
def dt_dwdm(wdm_manufacturer):
    return create_dwdm_mux_dx_type(wdm_manufacturer)


@pytest.fixture
def dt_roadm(wdm_manufacturer):
    return create_roadm_2d_type(wdm_manufacturer)


@pytest.fixture
def dt_pp(wdm_manufacturer):
    return create_fiber_pp_type(wdm_manufacturer)


# ---------------------------------------------------------------------------
# Class-scoped committed topologies for read-only trace tests.
#
# Building a full WDM topology (devices, ports, cables, auto-rebuilt
# wavelength paths) is by far the most expensive part of the trace tests, and
# the tests that consume one only trace and inspect it. These fixtures build
# a topology once per test class, actually committed to the test database (so
# every transaction.on_commit rebuild has flushed before any test runs), and
# delete everything they created at class teardown so the database is left
# clean for the rest of the session.
#
# Tests using these fixtures must be READ-ONLY against the topology and use a
# plain (non-transactional) django_db mark, so each test's own transaction is
# rolled back while the committed topology persists across the class.
# ---------------------------------------------------------------------------

_env_tags = count(1)


@dataclass
class _TopologyEnv:
    """A committed topology plus the foundation objects created for it."""

    site: Any
    manufacturer: Any
    roles: dict
    device_types: list = field(default_factory=list)
    topo: Any = None


def _rebuild_all(topo):
    from netbox_wdm.trace import rebuild_wavelength_paths_for_node

    for bundle in topo.bundles.values():
        rebuild_wavelength_paths_for_node(bundle.node)


def _new_env(kind: str) -> _TopologyEnv:
    tag = next(_env_tags)
    return _TopologyEnv(
        site=create_site(f"WDM Class Site {kind} {tag}"),
        manufacturer=create_manufacturer(f"WDM Class Vendor {kind} {tag}"),
        roles=create_device_roles(),
    )


def _build_duplex_env() -> _TopologyEnv:
    env = _new_env("dx")
    dt_mux = create_cwdm_mux_dx_type(env.manufacturer)
    dt_pp = create_fiber_pp_type(env.manufacturer)
    env.device_types = [dt_mux, dt_pp]
    env.topo = duplex_mux_pair(env.site, dt_mux, dt_pp, env.roles)
    _rebuild_all(env.topo)
    return env


def _build_unprofiled_duplex_env() -> _TopologyEnv:
    env = _build_duplex_env()
    for cable in env.topo.cables:
        if cable.profile:
            cable.profile = ""
            cable.save()
    return env


def _build_roadm_env() -> _TopologyEnv:
    env = _new_env("roadm")
    dt_dwdm = create_dwdm_mux_dx_type(env.manufacturer)
    dt_roadm = create_roadm_2d_type(env.manufacturer)
    dt_pp = create_fiber_pp_type(env.manufacturer)
    env.device_types = [dt_dwdm, dt_roadm, dt_pp]
    env.topo = mux_roadm_mux(env.site, dt_dwdm, dt_roadm, dt_pp, env.roles)
    _rebuild_all(env.topo)
    return env


def _build_sf_env() -> _TopologyEnv:
    env = _new_env("sf")
    dt_sf = create_cwdm_mux_sf_type(env.manufacturer)
    dt_pp = create_fiber_pp_type(env.manufacturer)
    env.device_types = [dt_sf, dt_pp]
    env.topo = sf_mux_pair(env.site, dt_sf, dt_pp, env.roles)
    _rebuild_all(env.topo)
    return env


def _teardown_env(env: _TopologyEnv) -> None:
    """Delete everything the env committed, leaving the reused database clean.

    Wavelength paths go first so the cable-delete signal handlers find nothing
    to rebuild; the rebuilds they queue via on_commit run after this atomic
    block commits, by which time the nodes are gone and the flush is a no-op.
    Device roles are shared get_or_create objects, so they are only removed
    once no other committed env still references them.
    """
    from django.db import transaction

    from netbox_wdm.models import WdmWavelengthPath

    with transaction.atomic():
        WdmWavelengthPath.objects.all().delete()
        for cable in env.topo.cables:
            cable.delete()
        devices = [bundle.device for bundle in env.topo.bundles.values()] + list(env.topo.patch_panels)
        for device in devices:
            device.delete()
        for device_type in env.device_types:
            device_type.delete()
        for role in env.roles.values():
            if not role.devices.exists():
                role.delete()
        env.manufacturer.delete()
        env.site.delete()


def _committed_topology(django_db_blocker, build_env):
    with django_db_blocker.unblock():
        env = build_env()
    yield env.topo
    with django_db_blocker.unblock():
        _teardown_env(env)


@pytest.fixture(scope="class")
def duplex_topology(django_db_setup, django_db_blocker):
    """A committed CWDM duplex MUX pair topology with rebuilt wavelength paths."""
    yield from _committed_topology(django_db_blocker, _build_duplex_env)


@pytest.fixture(scope="class")
def unprofiled_duplex_topology(django_db_setup, django_db_blocker):
    """A committed duplex MUX pair topology whose cables carry no profile."""
    yield from _committed_topology(django_db_blocker, _build_unprofiled_duplex_env)


@pytest.fixture(scope="class")
def roadm_topology(django_db_setup, django_db_blocker):
    """A committed MUX-A / ROADM / MUX-B pass-through topology with rebuilt paths."""
    yield from _committed_topology(django_db_blocker, _build_roadm_env)


@pytest.fixture(scope="class")
def sf_topology(django_db_setup, django_db_blocker):
    """A committed single-fiber MUX pair topology with rebuilt wavelength paths."""
    yield from _committed_topology(django_db_blocker, _build_sf_env)
