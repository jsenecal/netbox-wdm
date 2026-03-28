"""Shared pytest fixtures using the testing package."""

import django
import pytest
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.DJANGO_SETTINGS_MODULE = "netbox.settings"
        django.setup()


from netbox_wdm.testing import (  # noqa: E402
    create_cwdm_mux_dx_type,
    create_cwdm_mux_sf_type,
    create_device_roles,
    create_dwdm_mux_dx_type,
    create_fiber_pp_type,
    create_manufacturer,
    create_roadm_2d_type,
    create_site,
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
