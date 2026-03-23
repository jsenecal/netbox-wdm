# netbox-wdm Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone NetBox 4.5+ plugin for WDM device management — ITU channel plans, ROADM editing, position stack enforcement, and wavelength service tracking.

**Architecture:** Overlay pattern — `WdmDeviceTypeProfile` (1:1 on DeviceType) serves as blueprint, `WdmNode` (1:1 on Device) as instance. Channels auto-populate from templates on device creation. `WavelengthService` protects channel components via PROTECT FK guards. ROADM editor uses TypeScript frontend + atomic API endpoint.

**Tech Stack:** Python 3.12+, Django/NetBox 4.5+, strawberry-django (GraphQL), TypeScript + esbuild (frontend), pytest-django (tests).

**Spec:** `../netbox-fms/docs/superpowers/specs/2026-03-23-netbox-wdm-standalone-plugin.md` + WavelengthService extraction (without FiberCircuit FK).

---

## Chunk 1: Project Bootstrap

### Task 1: Initialize project files

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `Makefile`
- Create: `CLAUDE.md`
- Create: `LICENSE`
- Create: `netbox_wdm/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["netbox_wdm", "netbox_wdm.*"]

[tool.setuptools.package-data]
netbox_wdm = ["templates/**/*"]

[project]
name = "netbox-wdm"
version = "0.1.0"
description = "WDM wavelength management for NetBox — ITU channel plans, ROADM editing, and position stack enforcement"
readme = "README.md"
authors = [
    { name = "Jonathan Senecal", email = "contact@jonathansenecal.com" },
]
license = "AGPL-3.0-or-later"
license-files = ["LICENSE"]
requires-python = ">=3.12"
classifiers = [
    "Development Status :: 3 - Alpha",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = []

[project.optional-dependencies]
dev = [
    "bumpver",
    "pre-commit>=4.0.0",
    "pytest",
    "pytest-django>=4.5.0",
    "pytest-cov>=3.0.0",
    "ruff",
]

[project.urls]
Homepage = "https://github.com/jsenecal/netbox-wdm"
Source = "https://github.com/jsenecal/netbox-wdm"

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "DJ", "PIE"]
ignore = ["E501", "S101", "DJ01"]

[tool.ruff.lint.per-file-ignores]
"migrations/*" = ["N806", "N999"]
"tests/*" = ["S101", "S105", "S106"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --cov=netbox_wdm --cov-report=term-missing --reuse-db"

[tool.bumpver]
current_version = "0.1.0"
version_pattern = "MAJOR.MINOR.PATCH"
commit_message = "chore: bump version {old_version} -> {new_version}"
tag_pattern = "vMAJOR.MINOR.PATCH"
commit = true
tag = true
push = true

[tool.bumpver.file_patterns]
"pyproject.toml" = [
    'current_version = "{version}"',
    'version = "{version}"',
]
"netbox_wdm/__init__.py" = [
    '__version__ = "{version}"',
]
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
*.egg
dist/
!netbox_wdm/static/netbox_wdm/dist/
build/
.eggs/
*.so
.env
.venv/
venv/
node_modules/
netbox_wdm/static/netbox_wdm/node_modules/
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/
site/
.devcontainer/home/
.devcontainer/env/
.superpowers/
.worktrees/
docs/superpowers/
```

- [ ] **Step 3: Create Makefile**

```makefile
NETBOX_DIR  := /opt/netbox/netbox
MANAGE      := cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py
PYTEST      := cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest
PLUGIN_PKG  := netbox_wdm

.DEFAULT_GOAL := help

.PHONY: lint format check test test-fast migrations migrate runserver superuser collectstatic verify validate build clean ts-install ts-build ts-typecheck help

lint:
	uvx ruff check --fix $(PLUGIN_PKG)/

format:
	uvx ruff format $(PLUGIN_PKG)/

check:
	uvx ruff check $(PLUGIN_PKG)/
	uvx ruff format --check --exclude migrations $(PLUGIN_PKG)/

test:
	$(PYTEST) $(CURDIR)/tests/ -v

test-fast:
	$(PYTEST) $(CURDIR)/tests/ -v --no-cov

migrations:
	$(MANAGE) makemigrations $(PLUGIN_PKG)

migrate:
	$(MANAGE) migrate

runserver:
	$(MANAGE) runserver 0.0.0.0:8080

superuser:
	@cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from django.contrib.auth import get_user_model; User = get_user_model(); print('exists') if User.objects.filter(username='admin').exists() else (User.objects.create_superuser('admin', 'admin@example.com', 'admin'), print('created admin:admin'))"

collectstatic:
	$(MANAGE) collectstatic --no-input

verify:
	@cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from $(PLUGIN_PKG).models import *; from $(PLUGIN_PKG).forms import *; from $(PLUGIN_PKG).filters import *; print('OK')"

validate: check verify

ts-install:
	cd $(PLUGIN_PKG)/static/$(PLUGIN_PKG) && npm install

ts-build: ts-install
	cd $(PLUGIN_PKG)/static/$(PLUGIN_PKG) && npm run build

ts-typecheck:
	cd $(PLUGIN_PKG)/static/$(PLUGIN_PKG) && npm run typecheck

help:
	@grep -E '^[a-zA-Z_-]+:.*' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*"}; {printf "\033[36m%-18s\033[0m\n", $$1}'
```

- [ ] **Step 4: Create CLAUDE.md**

```markdown
# CLAUDE.md

## Project Overview

netbox-wdm is a NetBox 4.5+ plugin for WDM (Wavelength Division Multiplexing) device management. It follows NetBox's Device/DeviceType pattern: **WdmDeviceTypeProfile** (blueprint) overlays dcim.DeviceType, **WdmNode** (instance) overlays dcim.Device. The plugin manages ITU channel plans, channel-to-port assignments, trunk port identification, ROADM live editing, and wavelength service tracking.

## Development Environment

The plugin runs inside a Docker devcontainer with NetBox. NetBox source is at `/opt/netbox`.

### Key Commands

```bash
uvx ruff check --fix netbox_wdm/
uvx ruff format netbox_wdm/
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_wdm
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate
```

## Architecture

### Overlay Pattern

- `WdmDeviceTypeProfile` → 1:1 on `dcim.DeviceType` (blueprint)
- `WdmChannelTemplate` → channel-to-port blueprint on profile
- `WdmNode` → 1:1 on `dcim.Device` (instance)
- `WdmTrunkPort` → identifies trunk RearPorts
- `WavelengthChannel` → one per enabled ITU channel
- `WavelengthService` → end-to-end wavelength service spanning channels
- `WavelengthServiceChannelAssignment` → M2M through for sequenced channel assignments
- `WavelengthServiceNode` → PROTECT guard preventing deletion of in-use channels

### Position Stack Alignment

Channel `grid_position` determines the `rear_port_position` in PortMappings. CablePath carries this position through profiled trunk cables.

### ITU Grid Constants

In `wdm_constants.py`: DWDM 100GHz (44ch), DWDM 50GHz (88ch), CWDM (18ch).

### NetBox Plugin API Imports

| Component | Import Path |
|-----------|------------|
| NetBoxModel | `netbox.models.NetBoxModel` |
| ChoiceSet | `utilities.choices.ChoiceSet` |
| NetBoxModelForm | `netbox.forms.NetBoxModelForm` |
| NetBoxModelFilterSet | `netbox.filtersets.NetBoxModelFilterSet` |
| NetBoxTable | `netbox.tables.NetBoxTable` |
| Generic views | `netbox.views.generic` |
| NetBoxModelSerializer | `netbox.api.serializers.NetBoxModelSerializer` |
| NetBoxModelViewSet | `netbox.api.viewsets.NetBoxModelViewSet` |
| NetBoxRouter | `netbox.api.routers.NetBoxRouter` |
| ViewTab, register_model_view | `utilities.views` |
| PluginTemplateExtension | `netbox.plugins.PluginTemplateExtension` |

### URL Naming Convention

All URL names follow: `plugins:netbox_wdm:<modelname_lowercase>` (detail), `_list`, `_add`, `_edit`, `_delete`.

### Ruff Configuration

Line length: 120, target: Python 3.12.
```

- [ ] **Step 5: Create netbox_wdm/__init__.py**

```python
from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class NetBoxWDMConfig(PluginConfig):
    name = "netbox_wdm"
    verbose_name = "WDM Wavelength Management"
    description = "WDM wavelength management for NetBox — ITU channel plans, ROADM editing, and position stack enforcement"
    version = __version__
    author = "Jonathan Senecal"
    author_email = "contact@jonathansenecal.com"
    base_url = "wdm"
    min_version = "4.5.0"
    default_settings = {}

    def ready(self):
        super().ready()
        from .signals import connect_signals

        connect_signals()
        self._register_map_layers()

    @staticmethod
    def _register_map_layers():
        """Register WDM map layers with netbox-pathways if installed."""
        try:
            from netbox_pathways.registry import LayerStyle, register_map_layer
        except ImportError:
            return

        from dcim.models import Device

        register_map_layer(
            name="wdm_nodes",
            label="WDM Nodes",
            geometry_type="Point",
            source="reference",
            queryset=lambda r: Device.objects.filter(wdm_node__isnull=False).restrict(r.user, "view"),
            geometry_field="site",
            feature_fields=["name", "site", "role", "status"],
            popover_fields=["name", "role"],
            style=LayerStyle(color="#2196f3", icon="mdi-sine-wave"),
            group="WDM",
            sort_order=10,
        )


config = NetBoxWDMConfig
```

- [ ] **Step 6: Create LICENSE file (AGPL-3.0)**

Download or create AGPL-3.0 license text.

- [ ] **Step 7: Create placeholder signals.py**

Create `netbox_wdm/signals.py` with just the `connect_signals()` function (empty body for now — Task 9 implements it):

```python
def connect_signals():
    """Connect device signals. Called from AppConfig.ready(). Implemented in Task 9."""
```

- [ ] **Step 8: Create empty tests directory**

```bash
mkdir -p tests
touch tests/__init__.py
```

Create `tests/conftest.py`:

```python
import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.DJANGO_SETTINGS_MODULE = "netbox.settings"
        django.setup()
```

- [ ] **Step 9: Commit bootstrap**

```bash
git add pyproject.toml .gitignore Makefile CLAUDE.md LICENSE netbox_wdm/__init__.py netbox_wdm/signals.py tests/
git commit -m "feat: bootstrap netbox-wdm plugin project"
```

---

## Chunk 2: Constants, Choices & Tests

### Task 2: ITU grid constants

**Files:**
- Create: `netbox_wdm/wdm_constants.py`
- Create: `tests/test_constants.py`

- [ ] **Step 1: Create wdm_constants.py**

```python
"""ITU grid constants for WDM channel plans.

Each channel is a tuple of (grid_position, label, wavelength_nm).
Wavelengths for DWDM are computed from the ITU-T frequency grid
using c = 299792.458 km/s (speed of light).
"""

# Speed of light in km/s (for THz -> nm conversion: lambda = c / f)
_SPEED_OF_LIGHT_KMS = 299792.458

# ---------------------------------------------------------------------------
# CWDM: 18 channels, 1270-1610 nm, 20 nm spacing (ITU-T G.694.2)
# ---------------------------------------------------------------------------
CWDM_CHANNELS: tuple[tuple[int, str, float], ...] = tuple(
    (i + 1, f"CWDM-{1270 + i * 20}", float(1270 + i * 20)) for i in range(18)
)

# ---------------------------------------------------------------------------
# DWDM 100 GHz: 44 channels, C21-C64 (ITU-T G.694.1)
# Start frequency: 192.10 THz (C21), spacing: 0.10 THz
# ---------------------------------------------------------------------------

_DWDM_100GHZ_START_FREQ = 192.10  # THz (C21 = 192.10 THz)
_DWDM_100GHZ_SPACING = 0.10  # THz
_DWDM_100GHZ_COUNT = 44
_DWDM_100GHZ_FIRST_CHANNEL = 21


def _dwdm_100ghz_channels() -> tuple[tuple[int, str, float], ...]:
    channels = []
    for i in range(_DWDM_100GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_100GHZ_SPACING
        wavelength_nm = _SPEED_OF_LIGHT_KMS / freq_thz
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i
        label = f"C{channel_num}"
        channels.append((i + 1, label, round(wavelength_nm, 2)))
    return tuple(channels)


DWDM_100GHZ_CHANNELS: tuple[tuple[int, str, float], ...] = _dwdm_100ghz_channels()

# ---------------------------------------------------------------------------
# DWDM 50 GHz: 88 channels, C21-C64.5 with half-channels
# Start freq 192.10 THz, 0.05 THz spacing
# ---------------------------------------------------------------------------

_DWDM_50GHZ_SPACING = 0.05  # THz
_DWDM_50GHZ_COUNT = 88


def _dwdm_50ghz_channels() -> tuple[tuple[int, str, float], ...]:
    channels = []
    for i in range(_DWDM_50GHZ_COUNT):
        freq_thz = _DWDM_100GHZ_START_FREQ + i * _DWDM_50GHZ_SPACING
        wavelength_nm = _SPEED_OF_LIGHT_KMS / freq_thz
        # Even indices are whole channels (C21, C22, ...), odd are half (C21.5, C22.5, ...)
        channel_num = _DWDM_100GHZ_FIRST_CHANNEL + i // 2
        if i % 2 == 0:
            label = f"C{channel_num}"
        else:
            label = f"C{channel_num}.5"
        channels.append((i + 1, label, round(wavelength_nm, 2)))
    return tuple(channels)


DWDM_50GHZ_CHANNELS: tuple[tuple[int, str, float], ...] = _dwdm_50ghz_channels()

# ---------------------------------------------------------------------------
# Lookup dict: grid key -> channel list
# ---------------------------------------------------------------------------
WDM_GRIDS: dict[str, tuple[tuple[int, str, float], ...]] = {
    "cwdm": CWDM_CHANNELS,
    "dwdm_100ghz": DWDM_100GHZ_CHANNELS,
    "dwdm_50ghz": DWDM_50GHZ_CHANNELS,
}
```

- [ ] **Step 2: Write constants tests**

```python
"""Tests for ITU grid constants."""

import pytest

from netbox_wdm.wdm_constants import (
    CWDM_CHANNELS,
    DWDM_100GHZ_CHANNELS,
    DWDM_50GHZ_CHANNELS,
    WDM_GRIDS,
)


class TestCwdmChannels:
    def test_channel_count(self):
        assert len(CWDM_CHANNELS) == 18

    def test_first_channel(self):
        pos, label, wl = CWDM_CHANNELS[0]
        assert pos == 1
        assert label == "CWDM-1270"
        assert wl == 1270.0

    def test_last_channel(self):
        pos, label, wl = CWDM_CHANNELS[-1]
        assert pos == 18
        assert label == "CWDM-1610"
        assert wl == 1610.0

    def test_spacing(self):
        for i in range(1, len(CWDM_CHANNELS)):
            assert CWDM_CHANNELS[i][2] - CWDM_CHANNELS[i - 1][2] == 20.0

    def test_positions_sequential(self):
        positions = [ch[0] for ch in CWDM_CHANNELS]
        assert positions == list(range(1, 19))


class TestDwdm100GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_100GHZ_CHANNELS) == 44

    def test_first_channel(self):
        pos, label, wl = DWDM_100GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"
        assert isinstance(wl, float)

    def test_last_channel(self):
        pos, label, wl = DWDM_100GHZ_CHANNELS[-1]
        assert pos == 44
        assert label == "C64"

    def test_labels_sequential(self):
        for i, (_, label, _) in enumerate(DWDM_100GHZ_CHANNELS):
            assert label == f"C{21 + i}"

    def test_positions_sequential(self):
        positions = [ch[0] for ch in DWDM_100GHZ_CHANNELS]
        assert positions == list(range(1, 45))

    def test_wavelengths_decreasing(self):
        """Higher frequency = shorter wavelength, so wavelengths should decrease."""
        for i in range(1, len(DWDM_100GHZ_CHANNELS)):
            assert DWDM_100GHZ_CHANNELS[i][2] < DWDM_100GHZ_CHANNELS[i - 1][2]


class TestDwdm50GhzChannels:
    def test_channel_count(self):
        assert len(DWDM_50GHZ_CHANNELS) == 88

    def test_first_channel(self):
        pos, label, wl = DWDM_50GHZ_CHANNELS[0]
        assert pos == 1
        assert label == "C21"

    def test_half_channel_labels(self):
        _, label, _ = DWDM_50GHZ_CHANNELS[1]
        assert label == "C21.5"

    def test_positions_sequential(self):
        positions = [ch[0] for ch in DWDM_50GHZ_CHANNELS]
        assert positions == list(range(1, 89))

    def test_wavelengths_decreasing(self):
        for i in range(1, len(DWDM_50GHZ_CHANNELS)):
            assert DWDM_50GHZ_CHANNELS[i][2] < DWDM_50GHZ_CHANNELS[i - 1][2]

    def test_100ghz_channels_are_subset(self):
        """Every 100GHz channel wavelength should appear in 50GHz grid."""
        wl_50 = {ch[2] for ch in DWDM_50GHZ_CHANNELS}
        for ch in DWDM_100GHZ_CHANNELS:
            assert ch[2] in wl_50


class TestWdmGrids:
    def test_all_grids_present(self):
        assert set(WDM_GRIDS.keys()) == {"cwdm", "dwdm_100ghz", "dwdm_50ghz"}

    def test_grid_references(self):
        assert WDM_GRIDS["cwdm"] is CWDM_CHANNELS
        assert WDM_GRIDS["dwdm_100ghz"] is DWDM_100GHZ_CHANNELS
        assert WDM_GRIDS["dwdm_50ghz"] is DWDM_50GHZ_CHANNELS

    @pytest.mark.parametrize("grid_key", WDM_GRIDS.keys())
    def test_channel_tuple_structure(self, grid_key):
        for pos, label, wl in WDM_GRIDS[grid_key]:
            assert isinstance(pos, int)
            assert isinstance(label, str)
            assert isinstance(wl, float)
            assert pos > 0
            assert len(label) > 0
            assert wl > 0
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/test_constants.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add netbox_wdm/wdm_constants.py tests/test_constants.py
git commit -m "feat: add ITU grid constants and tests"
```

### Task 3: Choice sets

**Files:**
- Create: `netbox_wdm/choices.py`

- [ ] **Step 1: Create choices.py**

```python
from utilities.choices import ChoiceSet


class WdmNodeTypeChoices(ChoiceSet):
    TERMINAL_MUX = "terminal_mux"
    OADM = "oadm"
    ROADM = "roadm"
    AMPLIFIER = "amplifier"
    CHOICES = (
        (TERMINAL_MUX, "Terminal MUX"),
        (OADM, "OADM"),
        (ROADM, "ROADM"),
        (AMPLIFIER, "Amplifier"),
    )


class WdmGridChoices(ChoiceSet):
    DWDM_100GHZ = "dwdm_100ghz"
    DWDM_50GHZ = "dwdm_50ghz"
    CWDM = "cwdm"
    CHOICES = (
        (DWDM_100GHZ, "DWDM C-band 100GHz (44ch)"),
        (DWDM_50GHZ, "DWDM C-band 50GHz (88ch)"),
        (CWDM, "CWDM (18ch)"),
    )


class WdmTrunkDirectionChoices(ChoiceSet):
    COMMON = "common"
    EAST = "east"
    WEST = "west"
    CHOICES = (
        (COMMON, "Common"),
        (EAST, "East"),
        (WEST, "West"),
    )


class WavelengthChannelStatusChoices(ChoiceSet):
    AVAILABLE = "available"
    RESERVED = "reserved"
    LIT = "lit"
    CHOICES = (
        (AVAILABLE, "Available"),
        (RESERVED, "Reserved"),
        (LIT, "Lit"),
    )


class WavelengthServiceStatusChoices(ChoiceSet):
    PLANNED = "planned"
    STAGED = "staged"
    ACTIVE = "active"
    DECOMMISSIONED = "decommissioned"
    CHOICES = (
        (PLANNED, "Planned"),
        (STAGED, "Staged"),
        (ACTIVE, "Active"),
        (DECOMMISSIONED, "Decommissioned"),
    )
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/choices.py
git commit -m "feat: add WDM choice sets"
```

---

## Chunk 3: Models & Migration

### Task 4: Models

**Files:**
- Create: `netbox_wdm/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Create models.py**

```python
from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from .choices import (
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
    WdmTrunkDirectionChoices,
)


class WdmDeviceTypeProfile(NetBoxModel):
    """WDM capability profile attached to a DeviceType."""

    device_type = models.OneToOneField(
        to="dcim.DeviceType",
        on_delete=models.CASCADE,
        related_name="wdm_profile",
        verbose_name=_("device type"),
    )
    node_type = models.CharField(
        max_length=50,
        choices=WdmNodeTypeChoices,
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    clone_fields = ("node_type", "grid")

    class Meta:
        ordering = ("device_type",)
        verbose_name = _("WDM device type profile")
        verbose_name_plural = _("WDM device type profiles")

    def __str__(self):
        return f"WDM Profile: {self.device_type}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmdevicetypeprofile", args=[self.pk])


class WdmChannelTemplate(NetBoxModel):
    """Channel slot template on a WdmDeviceTypeProfile."""

    profile = models.ForeignKey(
        to="netbox_wdm.WdmDeviceTypeProfile",
        on_delete=models.CASCADE,
        related_name="channel_templates",
        verbose_name=_("profile"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    front_port_template = models.ForeignKey(
        to="dcim.FrontPortTemplate",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("front port template"),
    )

    class Meta:
        ordering = ("profile", "grid_position")
        unique_together = (
            ("profile", "wavelength_nm"),
            ("profile", "grid_position"),
        )
        verbose_name = _("WDM channel template")
        verbose_name_plural = _("WDM channel templates")
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "front_port_template"],
                condition=models.Q(front_port_template__isnull=False),
                name="unique_profile_fpt",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmchanneltemplate", args=[self.pk])


class WdmNode(NetBoxModel):
    """WDM node instance attached to a Device."""

    device = models.OneToOneField(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="wdm_node",
        verbose_name=_("device"),
    )
    node_type = models.CharField(
        max_length=50,
        choices=WdmNodeTypeChoices,
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    clone_fields = ("node_type", "grid")

    class Meta:
        ordering = ("device",)
        verbose_name = _("WDM node")
        verbose_name_plural = _("WDM nodes")

    def __str__(self):
        return f"WDM: {self.device.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmnode", args=[self.pk])

    @staticmethod
    def validate_channel_mapping(wdm_node, desired_mapping: dict[int, int | None]) -> list[str]:
        """Validate proposed channel-to-port mapping changes.

        Returns list of error strings. Empty list means validation passed.
        """
        errors = []
        channels = {ch.pk: ch for ch in wdm_node.channels.all()}

        protected_statuses = {WavelengthChannelStatusChoices.LIT, WavelengthChannelStatusChoices.RESERVED}
        for ch_pk, desired_fp_pk in desired_mapping.items():
            ch = channels.get(ch_pk)
            if ch is None:
                continue
            if ch.status in protected_statuses and ch.front_port_id != desired_fp_pk:
                errors.append(f"Channel {ch.label} (pk={ch.pk}) is {ch.get_status_display()} and cannot be remapped.")

        port_usage = {}
        for ch_pk, desired_fp_pk in desired_mapping.items():
            if desired_fp_pk is None:
                continue
            ch = channels.get(ch_pk)
            label = ch.label if ch else f"pk={ch_pk}"
            if desired_fp_pk in port_usage:
                errors.append(
                    f"Port conflict: channels {port_usage[desired_fp_pk]} and {label} "
                    f"both map to FrontPort pk={desired_fp_pk}."
                )
            else:
                port_usage[desired_fp_pk] = label

        return errors

    def save(self, *args, **kwargs):
        """Save and auto-populate channels from device type profile on creation."""
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.node_type != WdmNodeTypeChoices.AMPLIFIER:
            self._auto_populate_channels()

    def _auto_populate_channels(self):
        """Create WavelengthChannel rows from the device type's WDM profile templates."""
        from dcim.models import FrontPort

        try:
            profile = self.device.device_type.wdm_profile
        except WdmDeviceTypeProfile.DoesNotExist:
            return

        templates = list(profile.channel_templates.select_related("front_port_template").all())
        if not templates:
            return

        fp_by_name = {fp.name: fp for fp in FrontPort.objects.filter(device=self.device)}

        channels = []
        for ct in templates:
            front_port = None
            if ct.front_port_template:
                front_port = fp_by_name.get(ct.front_port_template.name)
            channels.append(
                WavelengthChannel(
                    wdm_node=self,
                    grid_position=ct.grid_position,
                    wavelength_nm=ct.wavelength_nm,
                    label=ct.label,
                    front_port=front_port,
                )
            )
        WavelengthChannel.objects.bulk_create(channels)


class WdmTrunkPort(NetBoxModel):
    """Maps a RearPort on a WDM node to a directional trunk."""

    wdm_node = models.ForeignKey(
        to="netbox_wdm.WdmNode",
        on_delete=models.CASCADE,
        related_name="trunk_ports",
        verbose_name=_("WDM node"),
    )
    rear_port = models.ForeignKey(
        to="dcim.RearPort",
        on_delete=models.PROTECT,
        verbose_name=_("rear port"),
    )
    direction = models.CharField(
        max_length=50,
        choices=WdmTrunkDirectionChoices,
        verbose_name=_("direction"),
    )
    position = models.PositiveIntegerField(verbose_name=_("position"))

    class Meta:
        ordering = ("wdm_node", "position")
        unique_together = (
            ("wdm_node", "rear_port"),
            ("wdm_node", "direction"),
        )
        verbose_name = _("WDM trunk port")
        verbose_name_plural = _("WDM trunk ports")

    def __str__(self):
        return f"{self.direction}: {self.rear_port}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmtrunkport", args=[self.pk])


class WavelengthChannel(NetBoxModel):
    """A wavelength channel instance on a WDM node."""

    wdm_node = models.ForeignKey(
        to="netbox_wdm.WdmNode",
        on_delete=models.CASCADE,
        related_name="channels",
        verbose_name=_("WDM node"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("front port"),
    )
    status = models.CharField(
        max_length=50,
        choices=WavelengthChannelStatusChoices,
        default=WavelengthChannelStatusChoices.AVAILABLE,
        verbose_name=_("status"),
    )

    class Meta:
        ordering = ("wdm_node", "grid_position")
        unique_together = (
            ("wdm_node", "wavelength_nm"),
            ("wdm_node", "grid_position"),
        )
        verbose_name = _("wavelength channel")
        verbose_name_plural = _("wavelength channels")
        constraints = [
            models.UniqueConstraint(
                fields=["wdm_node", "front_port"],
                condition=models.Q(front_port__isnull=False),
                name="unique_node_fp",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wavelengthchannel", args=[self.pk])


class WavelengthService(NetBoxModel):
    """An end-to-end wavelength service spanning WDM channels."""

    name = models.CharField(max_length=200, verbose_name=_("name"))
    status = models.CharField(
        max_length=50,
        choices=WavelengthServiceStatusChoices,
        default=WavelengthServiceStatusChoices.PLANNED,
        verbose_name=_("status"),
    )
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="wavelength_services",
        verbose_name=_("tenant"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    comments = models.TextField(blank=True, verbose_name=_("comments"))

    clone_fields = ("status", "wavelength_nm", "tenant")

    class Meta:
        ordering = ("name",)
        verbose_name = _("wavelength service")
        verbose_name_plural = _("wavelength services")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wavelengthservice", args=[self.pk])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status if self.pk else None

    def clean(self):
        """Validate channel consistency: same grid, matching wavelength."""
        super().clean()

        channel_assignments = self.channel_assignments.select_related("channel__wdm_node").all()
        if not channel_assignments.exists():
            return

        grids = set()
        svc_wl = Decimal(str(self.wavelength_nm))
        for ca in channel_assignments:
            if ca.channel:
                grids.add(ca.channel.wdm_node.grid)

        if len(grids) > 1:
            from django.core.exceptions import ValidationError

            raise ValidationError(
                _("All WDM nodes in a wavelength service must use the same grid. Found: %(grids)s")
                % {"grids": ", ".join(sorted(grids))}
            )

        for ca in channel_assignments:
            if ca.channel:
                ch_wl = Decimal(str(ca.channel.wavelength_nm))
                if abs(ch_wl - svc_wl) > Decimal("0.01"):
                    from django.core.exceptions import ValidationError

                    raise ValidationError(
                        _("Channel %(label)s has wavelength %(ch_wl)s nm but service wavelength is %(svc_wl)s nm.")
                        % {
                            "label": ca.channel.label,
                            "ch_wl": ca.channel.wavelength_nm,
                            "svc_wl": self.wavelength_nm,
                        }
                    )

    def save(self, *args, **kwargs):
        """Save and handle lifecycle transitions."""
        is_new = self._state.adding
        old_status = self._original_status

        super().save(*args, **kwargs)
        self._original_status = self.status

        if not is_new and old_status != self.status:
            if self.status == WavelengthServiceStatusChoices.DECOMMISSIONED:
                self.nodes.all().delete()
                channel_ids = self.channel_assignments.values_list("channel_id", flat=True)
                WavelengthChannel.objects.filter(pk__in=channel_ids).update(
                    status=WavelengthChannelStatusChoices.AVAILABLE
                )
            elif old_status == WavelengthServiceStatusChoices.DECOMMISSIONED:
                self.rebuild_nodes()

    def get_stitched_path(self):
        """Return the stitched end-to-end path as an ordered list of hop dicts."""
        hops = []
        for ca in self.channel_assignments.select_related("channel__wdm_node__device").order_by("sequence"):
            if ca.channel:
                hops.append(
                    {
                        "type": "wdm_node",
                        "node_id": ca.channel.wdm_node_id,
                        "node_name": ca.channel.wdm_node.device.name,
                        "channel_id": ca.channel_id,
                        "channel_label": ca.channel.label,
                        "wavelength_nm": float(ca.channel.wavelength_nm),
                    }
                )
        return hops

    def rebuild_nodes(self):
        """Delete existing service nodes and recreate from channel assignments."""
        self.nodes.all().delete()
        nodes = []
        for ca in self.channel_assignments.all():
            if ca.channel_id:
                nodes.append(WavelengthServiceNode(service=self, channel=ca.channel))
        if nodes:
            WavelengthServiceNode.objects.bulk_create(nodes)


class WavelengthServiceChannelAssignment(models.Model):
    """Through-model linking a WavelengthService to WavelengthChannels in sequence."""

    service = models.ForeignKey(
        to="netbox_wdm.WavelengthService",
        on_delete=models.CASCADE,
        related_name="channel_assignments",
        verbose_name=_("service"),
    )
    channel = models.ForeignKey(
        to="netbox_wdm.WavelengthChannel",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("channel"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("sequence"))

    class Meta:
        ordering = ("service", "sequence")
        unique_together = (
            ("service", "channel"),
            ("service", "sequence"),
        )
        verbose_name = _("wavelength service channel assignment")
        verbose_name_plural = _("wavelength service channel assignments")

    def __str__(self):
        return f"{self.service} #{self.sequence}: {self.channel}"


class WavelengthServiceNode(models.Model):
    """PROTECT guard preventing deletion of WavelengthChannels in active services."""

    service = models.ForeignKey(
        to="netbox_wdm.WavelengthService",
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name=_("service"),
    )
    channel = models.ForeignKey(
        to="netbox_wdm.WavelengthChannel",
        on_delete=models.PROTECT,
        verbose_name=_("channel"),
    )

    class Meta:
        verbose_name = _("wavelength service node")
        verbose_name_plural = _("wavelength service nodes")
        constraints = [
            models.UniqueConstraint(
                fields=["service", "channel"],
                name="unique_wsn_channel",
            ),
        ]

    def __str__(self):
        return f"channel: {self.channel}"
```

- [ ] **Step 2: Generate migration**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py makemigrations netbox_wdm`

- [ ] **Step 3: Run migration**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py migrate`

- [ ] **Step 4: Write model tests**

Create `tests/test_models.py`:

```python
"""Tests for WDM models."""

import pytest
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.db import IntegrityError

from netbox_wdm.choices import WavelengthChannelStatusChoices, WdmGridChoices, WdmNodeTypeChoices
from netbox_wdm.models import (
    WavelengthChannel,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


@pytest.fixture
def site():
    return Site.objects.create(name="Test Site", slug="test-site")


@pytest.fixture
def manufacturer():
    return Manufacturer.objects.create(name="Test Manufacturer", slug="test-manufacturer")


@pytest.fixture
def device_role():
    return DeviceRole.objects.create(name="WDM Mux", slug="wdm-mux")


@pytest.fixture
def device_type(manufacturer):
    return DeviceType.objects.create(
        manufacturer=manufacturer,
        model="Test MUX 44ch",
        slug="test-mux-44ch",
    )


@pytest.fixture
def device(site, device_type, device_role):
    return Device.objects.create(
        name="MUX-A",
        site=site,
        device_type=device_type,
        role=device_role,
    )


@pytest.fixture
def profile(device_type):
    return WdmDeviceTypeProfile.objects.create(
        device_type=device_type,
        node_type=WdmNodeTypeChoices.TERMINAL_MUX,
        grid=WdmGridChoices.DWDM_100GHZ,
    )


@pytest.mark.django_db
class TestWdmDeviceTypeProfile:
    def test_create(self, profile, device_type):
        assert profile.pk is not None
        assert profile.device_type == device_type
        assert profile.node_type == WdmNodeTypeChoices.TERMINAL_MUX

    def test_str(self, profile):
        assert "WDM Profile:" in str(profile)

    def test_get_absolute_url(self, profile):
        url = profile.get_absolute_url()
        assert f"/plugins/wdm/" in url

    def test_unique_device_type(self, profile, device_type):
        with pytest.raises(IntegrityError):
            WdmDeviceTypeProfile.objects.create(
                device_type=device_type,
                node_type=WdmNodeTypeChoices.ROADM,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWdmChannelTemplate:
    def test_create(self, profile):
        ct = WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert ct.pk is not None

    def test_str(self, profile):
        ct = WdmChannelTemplate.objects.create(
            profile=profile,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert "C21" in str(ct)
        assert "1560.61" in str(ct)

    def test_unique_position(self, profile):
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        with pytest.raises(IntegrityError):
            WdmChannelTemplate.objects.create(
                profile=profile, grid_position=1, wavelength_nm=1559.79, label="C22"
            )


@pytest.mark.django_db
class TestWdmNode:
    def test_create(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.pk is not None

    def test_str(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert "WDM:" in str(node)

    def test_auto_populate_channels_from_profile(self, device, profile):
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=2, wavelength_nm=1559.79, label="C22"
        )
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.channels.count() == 2

    def test_amplifier_no_auto_populate(self, device, profile):
        WdmChannelTemplate.objects.create(
            profile=profile, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.AMPLIFIER,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        assert node.channels.count() == 0

    def test_unique_device(self, device):
        WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        with pytest.raises(IntegrityError):
            WdmNode.objects.create(
                device=device,
                node_type=WdmNodeTypeChoices.ROADM,
                grid=WdmGridChoices.CWDM,
            )


@pytest.mark.django_db
class TestWavelengthChannel:
    def test_create(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert ch.pk is not None
        assert ch.status == WavelengthChannelStatusChoices.AVAILABLE

    def test_str(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
        )
        assert "C21" in str(ch)


@pytest.mark.django_db
class TestValidateChannelMapping:
    def test_reject_lit_channel_remap(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node,
            grid_position=1,
            wavelength_nm=1560.61,
            label="C21",
            status=WavelengthChannelStatusChoices.LIT,
        )
        errors = WdmNode.validate_channel_mapping(node, {ch.pk: 999})
        assert len(errors) == 1
        assert "cannot be remapped" in errors[0]

    def test_reject_port_conflict(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch1 = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        ch2 = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=2, wavelength_nm=1559.79, label="C22"
        )
        errors = WdmNode.validate_channel_mapping(node, {ch1.pk: 100, ch2.pk: 100})
        assert len(errors) == 1
        assert "Port conflict" in errors[0]

    def test_valid_mapping(self, device):
        node = WdmNode.objects.create(
            device=device,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WavelengthChannel.objects.create(
            wdm_node=node, grid_position=1, wavelength_nm=1560.61, label="C21"
        )
        errors = WdmNode.validate_channel_mapping(node, {ch.pk: 100})
        assert errors == []
```

- [ ] **Step 5: Run model tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add netbox_wdm/models.py netbox_wdm/migrations/ tests/test_models.py
git commit -m "feat: add WDM models with auto-populate, validation, and WavelengthService"
```

---

## Chunk 4: Forms, Filters, Tables

### Task 5: Forms

**Files:**
- Create: `netbox_wdm/forms.py`

- [ ] **Step 1: Create forms.py**

```python
from django import forms
from django.utils.translation import gettext_lazy as _

from dcim.models import Device, DeviceType, FrontPort, FrontPortTemplate, RearPort
from netbox.forms import NetBoxModelBulkEditForm, NetBoxModelFilterSetForm, NetBoxModelForm, NetBoxModelImportForm
from tenancy.models import Tenant
from utilities.forms.fields import CommentField, DynamicModelChoiceField, DynamicModelMultipleChoiceField
from utilities.forms.rendering import FieldSet

from .choices import (
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


# --- WdmDeviceTypeProfile ---


class WdmDeviceTypeProfileForm(NetBoxModelForm):
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all(), label=_("Device Type"))

    fieldsets = (
        FieldSet("device_type", "node_type", "grid", name=_("WDM Profile")),
        FieldSet("description", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("device_type", "node_type", "grid", "description", "tags")


class WdmDeviceTypeProfileFilterForm(NetBoxModelFilterSetForm):
    model = WdmDeviceTypeProfile
    node_type = forms.MultipleChoiceField(choices=WdmNodeTypeChoices, required=False)
    grid = forms.MultipleChoiceField(choices=WdmGridChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("node_type", "grid", name=_("Attributes")),
    )


class WdmDeviceTypeProfileImportForm(NetBoxModelImportForm):
    device_type = DynamicModelChoiceField(queryset=DeviceType.objects.all())
    node_type = forms.ChoiceField(choices=WdmNodeTypeChoices)
    grid = forms.ChoiceField(choices=WdmGridChoices)

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("device_type", "node_type", "grid", "description")


# --- WdmChannelTemplate ---


class WdmChannelTemplateForm(NetBoxModelForm):
    profile = DynamicModelChoiceField(queryset=WdmDeviceTypeProfile.objects.all(), label=_("Profile"))
    front_port_template = DynamicModelChoiceField(
        queryset=FrontPortTemplate.objects.all(), required=False, label=_("Front Port Template")
    )

    fieldsets = (
        FieldSet("profile", "grid_position", "wavelength_nm", "label", "front_port_template", name=_("Channel Template")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmChannelTemplate
        fields = ("profile", "grid_position", "wavelength_nm", "label", "front_port_template", "tags")


# --- WdmNode ---


class WdmNodeForm(NetBoxModelForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all(), label=_("Device"))

    fieldsets = (
        FieldSet("device", "node_type", "grid", name=_("WDM Node")),
        FieldSet("description", "tags", name=_("Additional")),
    )

    class Meta:
        model = WdmNode
        fields = ("device", "node_type", "grid", "description", "tags")


class WdmNodeFilterForm(NetBoxModelFilterSetForm):
    model = WdmNode
    node_type = forms.MultipleChoiceField(choices=WdmNodeTypeChoices, required=False)
    grid = forms.MultipleChoiceField(choices=WdmGridChoices, required=False)

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("node_type", "grid", name=_("Attributes")),
    )


class WdmNodeImportForm(NetBoxModelImportForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all())
    node_type = forms.ChoiceField(choices=WdmNodeTypeChoices)
    grid = forms.ChoiceField(choices=WdmGridChoices)

    class Meta:
        model = WdmNode
        fields = ("device", "node_type", "grid", "description")


# --- WdmTrunkPort ---


class WdmTrunkPortForm(NetBoxModelForm):
    wdm_node = DynamicModelChoiceField(queryset=WdmNode.objects.all(), label=_("WDM Node"))
    rear_port = DynamicModelChoiceField(queryset=RearPort.objects.all(), label=_("Rear Port"))

    fieldsets = (
        FieldSet("wdm_node", "rear_port", "direction", "position", name=_("Trunk Port")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WdmTrunkPort
        fields = ("wdm_node", "rear_port", "direction", "position", "tags")


# --- WavelengthChannel ---


class WavelengthChannelForm(NetBoxModelForm):
    wdm_node = DynamicModelChoiceField(queryset=WdmNode.objects.all(), label=_("WDM Node"))
    front_port = DynamicModelChoiceField(queryset=FrontPort.objects.all(), required=False, label=_("Front Port"))

    fieldsets = (
        FieldSet("wdm_node", "grid_position", "wavelength_nm", "label", "front_port", "status", name=_("Channel")),
        FieldSet("tags", name=_("Additional")),
    )

    class Meta:
        model = WavelengthChannel
        fields = ("wdm_node", "grid_position", "wavelength_nm", "label", "front_port", "status", "tags")


class WavelengthChannelBulkEditForm(NetBoxModelBulkEditForm):
    model = WavelengthChannel
    status = forms.ChoiceField(choices=WavelengthChannelStatusChoices, required=False)
    fieldsets = (FieldSet("status"),)
    nullable_fields = ()


class WavelengthChannelFilterForm(NetBoxModelFilterSetForm):
    model = WavelengthChannel
    status = forms.MultipleChoiceField(choices=WavelengthChannelStatusChoices, required=False)
    wdm_node_id = DynamicModelMultipleChoiceField(queryset=WdmNode.objects.all(), required=False, label=_("WDM Node"))

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("wdm_node_id", "status", name=_("Attributes")),
    )


# --- WavelengthService ---


class WavelengthServiceForm(NetBoxModelForm):
    tenant = DynamicModelChoiceField(queryset=Tenant.objects.all(), required=False)
    comments = CommentField()

    fieldsets = (
        FieldSet("name", "status", "wavelength_nm", "tenant", name=_("Service")),
        FieldSet("description", "comments", "tags", name=_("Additional")),
    )

    class Meta:
        model = WavelengthService
        fields = ("name", "status", "wavelength_nm", "tenant", "description", "comments", "tags")


class WavelengthServiceFilterForm(NetBoxModelFilterSetForm):
    model = WavelengthService
    status = forms.MultipleChoiceField(choices=WavelengthServiceStatusChoices, required=False)
    tenant_id = DynamicModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False, label=_("Tenant"))

    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("status", "tenant_id", name=_("Attributes")),
    )


class WavelengthServiceImportForm(NetBoxModelImportForm):
    status = forms.ChoiceField(choices=WavelengthServiceStatusChoices)

    class Meta:
        model = WavelengthService
        fields = ("name", "status", "wavelength_nm", "description", "comments")
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/forms.py
git commit -m "feat: add forms for all WDM models"
```

### Task 6: Filters

**Files:**
- Create: `netbox_wdm/filters.py`

- [ ] **Step 1: Create filters.py**

```python
import django_filters
from django.db import models
from django.utils.translation import gettext_lazy as _

from dcim.models import Device
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant

from .choices import (
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


class SearchFieldsMixin:
    """Mixin providing declarative search_fields for FilterSets."""

    search_fields: tuple[str, ...] = ()

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        q = models.Q()
        for field in self.search_fields:
            q |= models.Q(**{field: value})
        return queryset.filter(q)


class WdmDeviceTypeProfileFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)
    search_fields = ("device_type__model__icontains",)

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("id", "node_type", "grid")


class WdmChannelTemplateFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    profile_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmDeviceTypeProfile.objects.all(), field_name="profile", label=_("Profile (ID)")
    )
    search_fields = ("label__icontains",)

    class Meta:
        model = WdmChannelTemplate
        fields = ("id", "profile", "grid_position", "wavelength_nm", "label")


class WdmNodeFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)
    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(), field_name="device", label=_("Device (ID)")
    )
    search_fields = ("device__name__icontains",)

    class Meta:
        model = WdmNode
        fields = ("id", "node_type", "grid")


class WdmTrunkPortFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    search_fields = ("direction__icontains",)

    class Meta:
        model = WdmTrunkPort
        fields = ("id", "wdm_node", "direction", "position")


class WavelengthChannelFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    status = django_filters.MultipleChoiceFilter(choices=WavelengthChannelStatusChoices)
    search_fields = ("label__icontains",)

    class Meta:
        model = WavelengthChannel
        fields = ("id", "wdm_node", "status", "grid_position", "wavelength_nm")


class WavelengthServiceFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    status = django_filters.MultipleChoiceFilter(choices=WavelengthServiceStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(), field_name="tenant", label=_("Tenant (ID)")
    )
    search_fields = ("name__icontains", "description__icontains")

    class Meta:
        model = WavelengthService
        fields = ("id", "name", "status", "wavelength_nm")
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/filters.py
git commit -m "feat: add filtersets for all WDM models"
```

### Task 7: Tables

**Files:**
- Create: `netbox_wdm/tables.py`

- [ ] **Step 1: Create tables.py**

```python
import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from netbox.tables import NetBoxTable, columns

from .models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


class WdmDeviceTypeProfileTable(NetBoxTable):
    pk = columns.ToggleColumn()
    device_type = tables.Column(linkify=True, verbose_name=_("Device Type"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmDeviceTypeProfile
        fields = ("pk", "id", "device_type", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "device_type", "node_type", "grid", "actions")


class WdmChannelTemplateTable(NetBoxTable):
    pk = columns.ToggleColumn()
    profile = tables.Column(linkify=True, verbose_name=_("Profile"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    front_port_template = tables.Column(linkify=True, verbose_name=_("Front Port Template"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmChannelTemplate
        fields = ("pk", "id", "profile", "grid_position", "label", "wavelength_nm", "front_port_template", "actions")
        default_columns = ("pk", "profile", "grid_position", "label", "wavelength_nm", "front_port_template", "actions")


class WdmNodeTable(NetBoxTable):
    pk = columns.ToggleColumn()
    device = tables.Column(linkify=True, verbose_name=_("Device"))
    node_type = tables.Column(verbose_name=_("Node Type"))
    grid = tables.Column(verbose_name=_("Grid"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmNode
        fields = ("pk", "id", "device", "node_type", "grid", "description", "actions")
        default_columns = ("pk", "device", "node_type", "grid", "actions")


class WdmTrunkPortTable(NetBoxTable):
    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    rear_port = tables.Column(linkify=True, verbose_name=_("Rear Port"))
    direction = tables.Column(verbose_name=_("Direction"))
    position = tables.Column(verbose_name=_("Position"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WdmTrunkPort
        fields = ("pk", "id", "wdm_node", "rear_port", "direction", "position", "actions")
        default_columns = ("pk", "wdm_node", "rear_port", "direction", "position", "actions")


class WavelengthChannelTable(NetBoxTable):
    pk = columns.ToggleColumn()
    wdm_node = tables.Column(linkify=True, verbose_name=_("WDM Node"))
    grid_position = tables.Column(verbose_name=_("Grid Position"))
    label = tables.Column(verbose_name=_("Label"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    front_port = tables.Column(linkify=True, verbose_name=_("Front Port"))
    status = tables.Column(verbose_name=_("Status"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WavelengthChannel
        fields = ("pk", "id", "wdm_node", "grid_position", "label", "wavelength_nm", "front_port", "status", "actions")
        default_columns = ("pk", "label", "grid_position", "wavelength_nm", "front_port", "status", "actions")


class WavelengthServiceTable(NetBoxTable):
    pk = columns.ToggleColumn()
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    status = tables.Column(verbose_name=_("Status"))
    wavelength_nm = tables.Column(verbose_name=_("Wavelength (nm)"))
    tenant = tables.Column(linkify=True, verbose_name=_("Tenant"))
    actions = columns.ActionsColumn()

    class Meta(NetBoxTable.Meta):
        model = WavelengthService
        fields = ("pk", "id", "name", "status", "wavelength_nm", "tenant", "description", "actions")
        default_columns = ("pk", "name", "status", "wavelength_nm", "tenant", "actions")
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/tables.py
git commit -m "feat: add tables for all WDM models"
```

---

## Chunk 5: Views, URLs, Navigation, Search, Template Content

### Task 8: Views

**Files:**
- Create: `netbox_wdm/views.py`

- [ ] **Step 1: Create views.py**

```python
from django.utils.translation import gettext_lazy as _

from dcim.models import FrontPort
from netbox.object_actions import BulkDelete, DeleteObject, EditObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from .filters import (
    WavelengthChannelFilterSet,
    WavelengthServiceFilterSet,
    WdmChannelTemplateFilterSet,
    WdmDeviceTypeProfileFilterSet,
    WdmNodeFilterSet,
    WdmTrunkPortFilterSet,
)
from .forms import (
    WavelengthChannelBulkEditForm,
    WavelengthChannelFilterForm,
    WavelengthChannelForm,
    WavelengthServiceFilterForm,
    WavelengthServiceForm,
    WavelengthServiceImportForm,
    WdmChannelTemplateForm,
    WdmDeviceTypeProfileFilterForm,
    WdmDeviceTypeProfileForm,
    WdmDeviceTypeProfileImportForm,
    WdmNodeFilterForm,
    WdmNodeForm,
    WdmNodeImportForm,
    WdmTrunkPortForm,
)
from .models import (
    WavelengthChannel,
    WavelengthService,
    WavelengthServiceChannelAssignment,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)
from .tables import (
    WavelengthChannelTable,
    WavelengthServiceTable,
    WdmChannelTemplateTable,
    WdmDeviceTypeProfileTable,
    WdmNodeTable,
    WdmTrunkPortTable,
)


# ---- WdmDeviceTypeProfile ----


class WdmDeviceTypeProfileListView(generic.ObjectListView):
    queryset = WdmDeviceTypeProfile.objects.select_related("device_type")
    table = WdmDeviceTypeProfileTable
    filterset = WdmDeviceTypeProfileFilterSet
    filterset_form = WdmDeviceTypeProfileFilterForm


@register_model_view(WdmDeviceTypeProfile)
class WdmDeviceTypeProfileView(generic.ObjectView):
    queryset = WdmDeviceTypeProfile.objects.all()


class WdmDeviceTypeProfileEditView(generic.ObjectEditView):
    queryset = WdmDeviceTypeProfile.objects.all()
    form = WdmDeviceTypeProfileForm


class WdmDeviceTypeProfileDeleteView(generic.ObjectDeleteView):
    queryset = WdmDeviceTypeProfile.objects.all()


class WdmDeviceTypeProfileBulkImportView(generic.BulkImportView):
    queryset = WdmDeviceTypeProfile.objects.all()
    model_form = WdmDeviceTypeProfileImportForm


class WdmDeviceTypeProfileBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmDeviceTypeProfile.objects.all()
    filterset = WdmDeviceTypeProfileFilterSet
    table = WdmDeviceTypeProfileTable


@register_model_view(WdmDeviceTypeProfile, "channel_templates", path="channel-templates")
class WdmDeviceTypeProfileChannelTemplatesView(generic.ObjectChildrenView):
    queryset = WdmDeviceTypeProfile.objects.all()
    child_model = WdmChannelTemplate
    table = WdmChannelTemplateTable
    filterset = WdmChannelTemplateFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channel Templates"),
        badge=lambda obj: obj.channel_templates.count(),
        permission="netbox_wdm.view_wdmchanneltemplate",
        weight=500,
    )

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(profile=parent)


# ---- WdmChannelTemplate ----


@register_model_view(WdmChannelTemplate)
class WdmChannelTemplateView(generic.ObjectView):
    queryset = WdmChannelTemplate.objects.all()


class WdmChannelTemplateEditView(generic.ObjectEditView):
    queryset = WdmChannelTemplate.objects.all()
    form = WdmChannelTemplateForm


class WdmChannelTemplateDeleteView(generic.ObjectDeleteView):
    queryset = WdmChannelTemplate.objects.all()


# ---- WdmNode ----


class WdmNodeListView(generic.ObjectListView):
    queryset = WdmNode.objects.select_related("device")
    table = WdmNodeTable
    filterset = WdmNodeFilterSet
    filterset_form = WdmNodeFilterForm


@register_model_view(WdmNode)
class WdmNodeView(generic.ObjectView):
    queryset = WdmNode.objects.all()

    def get_extra_context(self, request, instance):
        channels = instance.channels.all()
        total = channels.count()
        lit = channels.filter(status="lit").count()
        reserved = channels.filter(status="reserved").count()
        available = channels.filter(status="available").count()
        return {
            "channel_count": total,
            "trunk_port_count": instance.trunk_ports.count(),
            "channel_stats": {
                "total": total,
                "lit": lit,
                "reserved": reserved,
                "available": available,
                "lit_pct": round(lit / total * 100) if total else 0,
                "reserved_pct": round(reserved / total * 100) if total else 0,
                "available_pct": round(available / total * 100) if total else 0,
            },
        }


class WdmNodeEditView(generic.ObjectEditView):
    queryset = WdmNode.objects.all()
    form = WdmNodeForm


class WdmNodeDeleteView(generic.ObjectDeleteView):
    queryset = WdmNode.objects.all()


class WdmNodeBulkImportView(generic.BulkImportView):
    queryset = WdmNode.objects.all()
    model_form = WdmNodeImportForm


class WdmNodeBulkDeleteView(generic.BulkDeleteView):
    queryset = WdmNode.objects.all()
    filterset = WdmNodeFilterSet
    table = WdmNodeTable


@register_model_view(WdmNode, "channels", path="channels")
class WdmNodeChannelsView(generic.ObjectChildrenView):
    queryset = WdmNode.objects.all()
    child_model = WavelengthChannel
    table = WavelengthChannelTable
    filterset = WavelengthChannelFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Channels"),
        badge=lambda obj: obj.channels.count(),
        permission="netbox_wdm.view_wavelengthchannel",
        weight=500,
    )

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "trunk_ports", path="trunk-ports")
class WdmNodeTrunkPortsView(generic.ObjectChildrenView):
    queryset = WdmNode.objects.all()
    child_model = WdmTrunkPort
    table = WdmTrunkPortTable
    filterset = WdmTrunkPortFilterSet
    actions = (EditObject, DeleteObject, BulkDelete)
    tab = ViewTab(
        label=_("Trunk Ports"),
        badge=lambda obj: obj.trunk_ports.count(),
        permission="netbox_wdm.view_wdmtrunkport",
        weight=510,
    )

    def get_children(self, request, parent):
        return self.child_model.objects.restrict(request.user, "view").filter(wdm_node=parent)


@register_model_view(WdmNode, "wavelength_editor", path="wavelength-editor")
class WdmNodeWavelengthEditorView(generic.ObjectView):
    """Live wavelength channel editor for ROADM nodes."""

    queryset = WdmNode.objects.all()
    tab = ViewTab(
        label=_("Wavelength Editor"),
        permission="netbox_wdm.change_wavelengthchannel",
        weight=600,
    )

    def get_template_name(self):
        return "netbox_wdm/wdmnode_wavelength_editor.html"

    def get_extra_context(self, request, instance):
        import json

        from django.urls import reverse

        channels = instance.channels.select_related("front_port").order_by("grid_position")
        assigned_fp_ids = set(
            instance.channels.exclude(front_port__isnull=True).values_list("front_port_id", flat=True)
        )
        available_ports = FrontPort.objects.filter(device=instance.device).exclude(pk__in=assigned_fp_ids)

        channel_data = []
        for ch in channels:
            svc_name = None
            svc_assignment = (
                WavelengthServiceChannelAssignment.objects.filter(channel=ch).select_related("service").first()
            )
            if svc_assignment:
                svc_name = svc_assignment.service.name
            channel_data.append(
                {
                    "id": ch.pk,
                    "grid_position": ch.grid_position,
                    "wavelength_nm": float(ch.wavelength_nm),
                    "label": ch.label,
                    "front_port_id": ch.front_port_id,
                    "front_port_name": ch.front_port.name if ch.front_port else None,
                    "status": ch.status,
                    "service_name": svc_name,
                }
            )

        port_data = [{"id": p.pk, "name": p.name} for p in available_ports]

        config = {
            "nodeId": instance.pk,
            "nodeType": instance.node_type,
            "lastUpdated": str(instance.last_updated),
            "applyUrl": reverse("plugins-api:netbox_wdm-api:wdmnode-apply-mapping", args=[instance.pk]),
            "channels": channel_data,
            "availablePorts": port_data,
        }
        return {"editor_config_json": json.dumps(config)}


# ---- WdmTrunkPort ----


@register_model_view(WdmTrunkPort)
class WdmTrunkPortView(generic.ObjectView):
    queryset = WdmTrunkPort.objects.all()


class WdmTrunkPortEditView(generic.ObjectEditView):
    queryset = WdmTrunkPort.objects.all()
    form = WdmTrunkPortForm


class WdmTrunkPortDeleteView(generic.ObjectDeleteView):
    queryset = WdmTrunkPort.objects.all()


# ---- WavelengthChannel ----


class WavelengthChannelListView(generic.ObjectListView):
    queryset = WavelengthChannel.objects.select_related("wdm_node", "front_port")
    table = WavelengthChannelTable
    filterset = WavelengthChannelFilterSet
    filterset_form = WavelengthChannelFilterForm


@register_model_view(WavelengthChannel)
class WavelengthChannelView(generic.ObjectView):
    queryset = WavelengthChannel.objects.all()


class WavelengthChannelEditView(generic.ObjectEditView):
    queryset = WavelengthChannel.objects.all()
    form = WavelengthChannelForm


class WavelengthChannelDeleteView(generic.ObjectDeleteView):
    queryset = WavelengthChannel.objects.all()


class WavelengthChannelBulkEditView(generic.BulkEditView):
    queryset = WavelengthChannel.objects.all()
    filterset = WavelengthChannelFilterSet
    table = WavelengthChannelTable
    form = WavelengthChannelBulkEditForm


class WavelengthChannelBulkDeleteView(generic.BulkDeleteView):
    queryset = WavelengthChannel.objects.all()
    filterset = WavelengthChannelFilterSet
    table = WavelengthChannelTable


# ---- WavelengthService ----


class WavelengthServiceListView(generic.ObjectListView):
    queryset = WavelengthService.objects.select_related("tenant")
    table = WavelengthServiceTable
    filterset = WavelengthServiceFilterSet
    filterset_form = WavelengthServiceFilterForm


@register_model_view(WavelengthService)
class WavelengthServiceView(generic.ObjectView):
    queryset = WavelengthService.objects.all()


@register_model_view(WavelengthService, "trace", path="trace")
class WavelengthServiceTraceView(generic.ObjectView):
    queryset = WavelengthService.objects.all()
    tab = ViewTab(
        label=_("Trace"),
        permission="netbox_wdm.view_wavelengthservice",
        weight=500,
    )

    def get_template_name(self):
        return "netbox_wdm/wavelengthservice_trace_tab.html"

    def get_extra_context(self, request, instance):
        return {"stitched_path": instance.get_stitched_path()}


class WavelengthServiceEditView(generic.ObjectEditView):
    queryset = WavelengthService.objects.all()
    form = WavelengthServiceForm


class WavelengthServiceDeleteView(generic.ObjectDeleteView):
    queryset = WavelengthService.objects.all()


class WavelengthServiceBulkImportView(generic.BulkImportView):
    queryset = WavelengthService.objects.all()
    model_form = WavelengthServiceImportForm


class WavelengthServiceBulkDeleteView(generic.BulkDeleteView):
    queryset = WavelengthService.objects.all()
    filterset = WavelengthServiceFilterSet
    table = WavelengthServiceTable
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/views.py
git commit -m "feat: add views for all WDM models"
```

### Task 9: URLs

**Files:**
- Create: `netbox_wdm/urls.py`

- [ ] **Step 1: Create urls.py**

```python
from django.urls import include, path

from netbox.urls import get_model_urls

from . import views

urlpatterns = [
    # WDM Device Type Profile
    path("wdm-profiles/", views.WdmDeviceTypeProfileListView.as_view(), name="wdmdevicetypeprofile_list"),
    path("wdm-profiles/add/", views.WdmDeviceTypeProfileEditView.as_view(), name="wdmdevicetypeprofile_add"),
    path(
        "wdm-profiles/import/",
        views.WdmDeviceTypeProfileBulkImportView.as_view(),
        name="wdmdevicetypeprofile_import",
    ),
    path(
        "wdm-profiles/delete/",
        views.WdmDeviceTypeProfileBulkDeleteView.as_view(),
        name="wdmdevicetypeprofile_bulk_delete",
    ),
    path("wdm-profiles/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmdevicetypeprofile"))),
    path("wdm-profiles/<int:pk>/", views.WdmDeviceTypeProfileView.as_view(), name="wdmdevicetypeprofile"),
    path("wdm-profiles/<int:pk>/edit/", views.WdmDeviceTypeProfileEditView.as_view(), name="wdmdevicetypeprofile_edit"),
    path(
        "wdm-profiles/<int:pk>/delete/",
        views.WdmDeviceTypeProfileDeleteView.as_view(),
        name="wdmdevicetypeprofile_delete",
    ),
    # WDM Channel Template
    path("wdm-channel-templates/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmchanneltemplate"))),
    path("wdm-channel-templates/<int:pk>/", views.WdmChannelTemplateView.as_view(), name="wdmchanneltemplate"),
    path(
        "wdm-channel-templates/<int:pk>/edit/",
        views.WdmChannelTemplateEditView.as_view(),
        name="wdmchanneltemplate_edit",
    ),
    path(
        "wdm-channel-templates/<int:pk>/delete/",
        views.WdmChannelTemplateDeleteView.as_view(),
        name="wdmchanneltemplate_delete",
    ),
    # WDM Node
    path("wdm-nodes/", views.WdmNodeListView.as_view(), name="wdmnode_list"),
    path("wdm-nodes/add/", views.WdmNodeEditView.as_view(), name="wdmnode_add"),
    path("wdm-nodes/import/", views.WdmNodeBulkImportView.as_view(), name="wdmnode_import"),
    path("wdm-nodes/delete/", views.WdmNodeBulkDeleteView.as_view(), name="wdmnode_bulk_delete"),
    path("wdm-nodes/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmnode"))),
    path("wdm-nodes/<int:pk>/", views.WdmNodeView.as_view(), name="wdmnode"),
    path("wdm-nodes/<int:pk>/edit/", views.WdmNodeEditView.as_view(), name="wdmnode_edit"),
    path("wdm-nodes/<int:pk>/delete/", views.WdmNodeDeleteView.as_view(), name="wdmnode_delete"),
    # WDM Trunk Port
    path("wdm-trunk-ports/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmtrunkport"))),
    path("wdm-trunk-ports/<int:pk>/", views.WdmTrunkPortView.as_view(), name="wdmtrunkport"),
    path("wdm-trunk-ports/<int:pk>/edit/", views.WdmTrunkPortEditView.as_view(), name="wdmtrunkport_edit"),
    path("wdm-trunk-ports/<int:pk>/delete/", views.WdmTrunkPortDeleteView.as_view(), name="wdmtrunkport_delete"),
    # Wavelength Channel
    path("wavelength-channels/", views.WavelengthChannelListView.as_view(), name="wavelengthchannel_list"),
    path("wavelength-channels/add/", views.WavelengthChannelEditView.as_view(), name="wavelengthchannel_add"),
    path(
        "wavelength-channels/edit/",
        views.WavelengthChannelBulkEditView.as_view(),
        name="wavelengthchannel_bulk_edit",
    ),
    path(
        "wavelength-channels/delete/",
        views.WavelengthChannelBulkDeleteView.as_view(),
        name="wavelengthchannel_bulk_delete",
    ),
    path("wavelength-channels/<int:pk>/", include(get_model_urls("netbox_wdm", "wavelengthchannel"))),
    path("wavelength-channels/<int:pk>/", views.WavelengthChannelView.as_view(), name="wavelengthchannel"),
    path(
        "wavelength-channels/<int:pk>/edit/",
        views.WavelengthChannelEditView.as_view(),
        name="wavelengthchannel_edit",
    ),
    path(
        "wavelength-channels/<int:pk>/delete/",
        views.WavelengthChannelDeleteView.as_view(),
        name="wavelengthchannel_delete",
    ),
    # Wavelength Service
    path("wavelength-services/", views.WavelengthServiceListView.as_view(), name="wavelengthservice_list"),
    path("wavelength-services/add/", views.WavelengthServiceEditView.as_view(), name="wavelengthservice_add"),
    path(
        "wavelength-services/import/",
        views.WavelengthServiceBulkImportView.as_view(),
        name="wavelengthservice_import",
    ),
    path(
        "wavelength-services/delete/",
        views.WavelengthServiceBulkDeleteView.as_view(),
        name="wavelengthservice_bulk_delete",
    ),
    path("wavelength-services/<int:pk>/", include(get_model_urls("netbox_wdm", "wavelengthservice"))),
    path("wavelength-services/<int:pk>/", views.WavelengthServiceView.as_view(), name="wavelengthservice"),
    path(
        "wavelength-services/<int:pk>/edit/",
        views.WavelengthServiceEditView.as_view(),
        name="wavelengthservice_edit",
    ),
    path(
        "wavelength-services/<int:pk>/delete/",
        views.WavelengthServiceDeleteView.as_view(),
        name="wavelengthservice_delete",
    ),
]
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/urls.py
git commit -m "feat: add URL routing for all WDM views"
```

### Task 10: Navigation, Search, Template Content

**Files:**
- Create: `netbox_wdm/navigation.py`
- Create: `netbox_wdm/search.py`
- Create: `netbox_wdm/template_content.py`

- [ ] **Step 1: Create navigation.py**

```python
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label="WDM",
    groups=(
        (
            "WDM",
            (
                PluginMenuItem(
                    link="plugins:netbox_wdm:wdmdevicetypeprofile_list",
                    link_text="WDM Profiles",
                    permissions=["netbox_wdm.view_wdmdevicetypeprofile"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_wdm:wdmdevicetypeprofile_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_wdm.add_wdmdevicetypeprofile"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_wdm:wdmnode_list",
                    link_text="WDM Nodes",
                    permissions=["netbox_wdm.view_wdmnode"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_wdm:wdmnode_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_wdm.add_wdmnode"],
                        ),
                    ),
                ),
                PluginMenuItem(
                    link="plugins:netbox_wdm:wavelengthchannel_list",
                    link_text="Wavelength Channels",
                    permissions=["netbox_wdm.view_wavelengthchannel"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_wdm:wavelengthservice_list",
                    link_text="Wavelength Services",
                    permissions=["netbox_wdm.view_wavelengthservice"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_wdm:wavelengthservice_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_wdm.add_wavelengthservice"],
                        ),
                    ),
                ),
            ),
        ),
    ),
    icon_class="mdi mdi-sine-wave",
)
```

- [ ] **Step 2: Create search.py**

```python
from netbox.search import SearchIndex, register_search

from .models import WavelengthChannel, WavelengthService, WdmNode


@register_search
class WdmNodeIndex(SearchIndex):
    model = WdmNode
    fields = (("description", 500),)
    display_attrs = ("device", "node_type", "grid")


@register_search
class WavelengthChannelIndex(SearchIndex):
    model = WavelengthChannel
    fields = (("label", 100),)
    display_attrs = ("wdm_node", "wavelength_nm", "status")


@register_search
class WavelengthServiceIndex(SearchIndex):
    model = WavelengthService
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("status", "wavelength_nm", "tenant")
```

- [ ] **Step 3: Create template_content.py**

```python
from netbox.plugins import PluginTemplateExtension

from .models import WdmNode


class DeviceWdmNodePanel(PluginTemplateExtension):
    models = ["dcim.device"]

    def right_page(self):
        device = self.context["object"]
        wdm_node = WdmNode.objects.filter(device=device).first()
        if wdm_node:
            return self.render(
                "netbox_wdm/inc/device_wdm_panel.html",
                extra_context={"wdm_node": wdm_node},
            )
        return ""


template_extensions = [DeviceWdmNodePanel]
```

- [ ] **Step 4: Commit**

```bash
git add netbox_wdm/navigation.py netbox_wdm/search.py netbox_wdm/template_content.py
git commit -m "feat: add navigation menu, search indexes, and template extensions"
```

---

## Chunk 6: Templates

### Task 11: HTML templates

**Files:**
- Create: `netbox_wdm/templates/netbox_wdm/wdmdevicetypeprofile.html`
- Create: `netbox_wdm/templates/netbox_wdm/wdmnode.html`
- Create: `netbox_wdm/templates/netbox_wdm/wdmtrunkport.html`
- Create: `netbox_wdm/templates/netbox_wdm/wdmchanneltemplate.html`
- Create: `netbox_wdm/templates/netbox_wdm/wavelengthchannel.html`
- Create: `netbox_wdm/templates/netbox_wdm/wavelengthservice.html`
- Create: `netbox_wdm/templates/netbox_wdm/wavelengthservice_trace_tab.html`
- Create: `netbox_wdm/templates/netbox_wdm/wdmnode_wavelength_editor.html`
- Create: `netbox_wdm/templates/netbox_wdm/inc/device_wdm_panel.html`

- [ ] **Step 1: Create template directories**

```bash
mkdir -p netbox_wdm/templates/netbox_wdm/inc
```

- [ ] **Step 2: Create wdmdevicetypeprofile.html**

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "WDM Device Type Profile" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Device Type" %}</th>
                    <td>{{ object.device_type|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Node Type" %}</th>
                    <td>{{ object.get_node_type_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Grid" %}</th>
                    <td>{{ object.get_grid_display }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% if object.description %}
        <div class="card">
            <h5 class="card-header">{% trans "Description" %}</h5>
            <div class="card-body">{{ object.description|markdown }}</div>
        </div>
        {% endif %}
        {% include 'inc/panels/tags.html' %}
        {% include 'inc/panels/custom_fields.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 3: Create wdmnode.html** (includes channel utilization progress bar)

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "WDM Node" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Device" %}</th>
                    <td>{{ object.device|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Node Type" %}</th>
                    <td>{{ object.get_node_type_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Grid" %}</th>
                    <td>{{ object.get_grid_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Channels" %}</th>
                    <td>{{ channel_count }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Trunk Ports" %}</th>
                    <td>{{ trunk_port_count }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        <div class="card mb-3">
            <h5 class="card-header">{% trans "Channel Utilization" %}</h5>
            <div class="card-body">
                {% if channel_stats.total %}
                <div class="progress mb-2" style="height: 24px;">
                    {% if channel_stats.lit_pct %}
                    <div class="progress-bar bg-success" role="progressbar" style="width: {{ channel_stats.lit_pct }}%" title="{{ channel_stats.lit }} Lit">
                        {{ channel_stats.lit }}
                    </div>
                    {% endif %}
                    {% if channel_stats.reserved_pct %}
                    <div class="progress-bar bg-warning text-dark" role="progressbar" style="width: {{ channel_stats.reserved_pct }}%" title="{{ channel_stats.reserved }} Reserved">
                        {{ channel_stats.reserved }}
                    </div>
                    {% endif %}
                    {% if channel_stats.available_pct %}
                    <div class="progress-bar bg-secondary" role="progressbar" style="width: {{ channel_stats.available_pct }}%" title="{{ channel_stats.available }} Available">
                        {{ channel_stats.available }}
                    </div>
                    {% endif %}
                </div>
                <div class="d-flex justify-content-between">
                    <small><span class="badge bg-success">{{ channel_stats.lit }}</span> {% trans "Lit" %}</small>
                    <small><span class="badge bg-warning text-dark">{{ channel_stats.reserved }}</span> {% trans "Reserved" %}</small>
                    <small><span class="badge bg-secondary">{{ channel_stats.available }}</span> {% trans "Available" %}</small>
                    <small class="text-muted">{{ channel_stats.total }} {% trans "total" %}</small>
                </div>
                {% else %}
                <p class="text-muted mb-0">{% trans "No channels configured." %}</p>
                {% endif %}
            </div>
        </div>
        {% if object.description %}
        <div class="card">
            <h5 class="card-header">{% trans "Description" %}</h5>
            <div class="card-body">{{ object.description|markdown }}</div>
        </div>
        {% endif %}
        {% include 'inc/panels/tags.html' %}
        {% include 'inc/panels/custom_fields.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 4: Create wdmtrunkport.html**

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "WDM Trunk Port" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "WDM Node" %}</th>
                    <td>{{ object.wdm_node|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Rear Port" %}</th>
                    <td>{{ object.rear_port|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Direction" %}</th>
                    <td>{{ object.get_direction_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Position" %}</th>
                    <td>{{ object.position }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% include 'inc/panels/tags.html' %}
        {% include 'inc/panels/custom_fields.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 5: Create wdmchanneltemplate.html**

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "WDM Channel Template" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Profile" %}</th>
                    <td>{{ object.profile|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Grid Position" %}</th>
                    <td>{{ object.grid_position }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Label" %}</th>
                    <td>{{ object.label }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Wavelength (nm)" %}</th>
                    <td>{{ object.wavelength_nm }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Front Port Template" %}</th>
                    <td>{% if object.front_port_template %}{{ object.front_port_template }}{% else %}&mdash;{% endif %}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% include 'inc/panels/tags.html' %}
        {% include 'inc/panels/custom_fields.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 6: Create wavelengthchannel.html**

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Wavelength Channel" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "WDM Node" %}</th>
                    <td>{{ object.wdm_node|linkify }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Grid Position" %}</th>
                    <td>{{ object.grid_position }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Label" %}</th>
                    <td>{{ object.label }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Wavelength (nm)" %}</th>
                    <td>{{ object.wavelength_nm }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Front Port" %}</th>
                    <td>{% if object.front_port %}{{ object.front_port|linkify }}{% else %}&mdash;{% endif %}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Status" %}</th>
                    <td>{{ object.get_status_display }}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% include 'inc/panels/tags.html' %}
        {% include 'inc/panels/custom_fields.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 7: Create wavelengthservice.html**

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-6">
        <div class="card">
            <h5 class="card-header">{% trans "Wavelength Service" %}</h5>
            <table class="table table-hover attr-table">
                <tr>
                    <th scope="row">{% trans "Name" %}</th>
                    <td>{{ object.name }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Status" %}</th>
                    <td>{{ object.get_status_display }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Wavelength (nm)" %}</th>
                    <td>{{ object.wavelength_nm }}</td>
                </tr>
                <tr>
                    <th scope="row">{% trans "Tenant" %}</th>
                    <td>{% if object.tenant %}{{ object.tenant|linkify }}{% else %}&mdash;{% endif %}</td>
                </tr>
            </table>
        </div>
    </div>
    <div class="col col-md-6">
        {% if object.description %}
        <div class="card">
            <h5 class="card-header">{% trans "Description" %}</h5>
            <div class="card-body">{{ object.description|markdown }}</div>
        </div>
        {% endif %}
        {% include 'inc/panels/comments.html' %}
        {% include 'inc/panels/tags.html' %}
        {% include 'inc/panels/custom_fields.html' %}
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}
```

- [ ] **Step 8: Create wavelengthservice_trace_tab.html** (channel-only, no fiber circuits)

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}

{% block content %}
<div class="row mb-3">
    <div class="col col-md-8 mx-auto">
        <div class="card">
            <h5 class="card-header">{% trans "Stitched Wavelength Path" %}</h5>
            <div class="card-body">
                {% if stitched_path %}
                <div class="d-flex flex-column align-items-center">
                    {% for hop in stitched_path %}
                    {% if not forloop.first %}
                    <div style="width: 2px; height: 20px; background-color: #6c757d;"></div>
                    {% endif %}
                    <div class="border rounded p-3 mb-2 text-center" style="min-width: 300px; background-color: #d4edda; border-color: #28a745 !important;">
                        <strong>{{ hop.node_name }}</strong><br>
                        <small class="text-muted">
                            {{ hop.channel_label }} &mdash; {{ hop.wavelength_nm }} nm
                        </small>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <div class="text-muted text-center py-4">
                    {% trans "No path segments assigned" %}
                </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 9: Create wdmnode_wavelength_editor.html**

```html
{% extends 'generic/object.html' %}
{% load helpers %}
{% load plugins %}
{% load i18n %}
{% load static %}

{% block content %}
<div class="row mb-3">
    <div class="col">
        <div id="wavelength-editor-container"></div>
    </div>
</div>
{% plugin_full_width_page object %}
{% endblock %}

{% block javascript %}
{{ block.super }}
<script>
window.WAVELENGTH_EDITOR_CONFIG = {{ editor_config_json|safe }};
</script>
<script src="{% static 'netbox_wdm/dist/wavelength-editor.min.js' %}"></script>
{% endblock %}
```

- [ ] **Step 10: Create inc/device_wdm_panel.html**

```html
{% load helpers %}
{% load i18n %}
{% if wdm_node %}
<div class="card">
    <h2 class="card-header">{% trans "WDM Node" %}</h2>
    <table class="table table-hover attr-table">
        <tr>
            <th scope="row">{% trans "Node Type" %}</th>
            <td>{{ wdm_node.get_node_type_display }}</td>
        </tr>
        <tr>
            <th scope="row">{% trans "Grid" %}</th>
            <td>{{ wdm_node.get_grid_display }}</td>
        </tr>
        <tr>
            <th scope="row">{% trans "Channels" %}</th>
            <td>{{ wdm_node.channels.count }}</td>
        </tr>
        <tr>
            <th scope="row">{% trans "Trunk Ports" %}</th>
            <td>{{ wdm_node.trunk_ports.count }}</td>
        </tr>
        <tr>
            <td colspan="2">
                <a href="{{ wdm_node.get_absolute_url }}" class="btn btn-sm btn-outline-primary">
                    {% trans "View WDM Node" %}
                </a>
            </td>
        </tr>
    </table>
</div>
{% endif %}
```

- [ ] **Step 3: Commit**

```bash
git add netbox_wdm/templates/
git commit -m "feat: add HTML templates for all WDM views"
```

---

## Chunk 7: REST API

### Task 12: API serializers, views, URLs

**Files:**
- Create: `netbox_wdm/api/__init__.py`
- Create: `netbox_wdm/api/serializers.py`
- Create: `netbox_wdm/api/views.py`
- Create: `netbox_wdm/api/urls.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Create api/__init__.py**

Empty file.

- [ ] **Step 2: Create api/serializers.py**

```python
from netbox.api.serializers import NetBoxModelSerializer

from ..models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


class WdmDeviceTypeProfileSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmDeviceTypeProfile
        fields = (
            "id", "url", "display", "device_type", "node_type", "grid",
            "description", "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "node_type", "grid")


class WdmChannelTemplateSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmChannelTemplate
        fields = (
            "id", "url", "display", "profile", "grid_position", "wavelength_nm",
            "label", "front_port_template", "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "label", "wavelength_nm")


class WdmNodeSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmNode
        fields = (
            "id", "url", "display", "device", "node_type", "grid",
            "description", "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "node_type", "grid")


class WdmTrunkPortSerializer(NetBoxModelSerializer):
    class Meta:
        model = WdmTrunkPort
        fields = (
            "id", "url", "display", "wdm_node", "rear_port", "direction",
            "position", "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "direction", "position")


class WavelengthChannelSerializer(NetBoxModelSerializer):
    class Meta:
        model = WavelengthChannel
        fields = (
            "id", "url", "display", "wdm_node", "grid_position", "wavelength_nm",
            "label", "front_port", "status", "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "label", "wavelength_nm", "status")


class WavelengthServiceSerializer(NetBoxModelSerializer):
    class Meta:
        model = WavelengthService
        fields = (
            "id", "url", "display", "name", "status", "wavelength_nm", "tenant",
            "description", "comments", "tags", "custom_fields", "created", "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status", "wavelength_nm")
```

- [ ] **Step 3: Create api/views.py**

```python
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from dcim.models import PortMapping, RearPort
from netbox.api.viewsets import NetBoxModelViewSet

from ..filters import (
    WavelengthChannelFilterSet,
    WavelengthServiceFilterSet,
    WdmChannelTemplateFilterSet,
    WdmDeviceTypeProfileFilterSet,
    WdmNodeFilterSet,
    WdmTrunkPortFilterSet,
)
from ..models import WavelengthChannel, WavelengthService, WdmChannelTemplate, WdmDeviceTypeProfile, WdmNode, WdmTrunkPort
from .serializers import (
    WavelengthChannelSerializer,
    WavelengthServiceSerializer,
    WdmChannelTemplateSerializer,
    WdmDeviceTypeProfileSerializer,
    WdmNodeSerializer,
    WdmTrunkPortSerializer,
)


class WdmDeviceTypeProfileViewSet(NetBoxModelViewSet):
    queryset = WdmDeviceTypeProfile.objects.prefetch_related("device_type", "tags")
    serializer_class = WdmDeviceTypeProfileSerializer
    filterset_class = WdmDeviceTypeProfileFilterSet


class WdmChannelTemplateViewSet(NetBoxModelViewSet):
    queryset = WdmChannelTemplate.objects.prefetch_related("profile", "tags")
    serializer_class = WdmChannelTemplateSerializer
    filterset_class = WdmChannelTemplateFilterSet


def _apply_mapping(wdm_node, desired_mapping: dict[int, int | None]) -> dict:
    """Apply channel-to-port mapping changes. Uses bulk operations."""
    channels = {ch.pk: ch for ch in wdm_node.channels.all()}
    trunk_ports = list(wdm_node.trunk_ports.select_related("rear_port").all())

    added = removed = changed = 0
    channels_to_update = []
    old_fp_ids_to_delete = []
    new_mappings_to_create = []

    for ch_pk, desired_fp_pk in desired_mapping.items():
        ch = channels.get(ch_pk)
        if ch is None:
            continue

        current_fp_pk = ch.front_port_id
        if current_fp_pk == desired_fp_pk:
            continue

        if current_fp_pk is not None:
            old_fp_ids_to_delete.append((current_fp_pk, ch.grid_position))

        if desired_fp_pk is not None:
            for tp in trunk_ports:
                new_mappings_to_create.append(
                    PortMapping(
                        device=wdm_node.device,
                        front_port_id=desired_fp_pk,
                        rear_port=tp.rear_port,
                        front_port_position=1,
                        rear_port_position=ch.grid_position,
                    )
                )

        ch.front_port_id = desired_fp_pk
        channels_to_update.append(ch)

        if current_fp_pk is None and desired_fp_pk is not None:
            added += 1
        elif current_fp_pk is not None and desired_fp_pk is None:
            removed += 1
        else:
            changed += 1

    if channels_to_update:
        WavelengthChannel.objects.bulk_update(channels_to_update, ["front_port_id"])

    if old_fp_ids_to_delete:
        delete_q = Q()
        for fp_id, grid_pos in old_fp_ids_to_delete:
            for tp in trunk_ports:
                delete_q |= Q(front_port_id=fp_id, rear_port=tp.rear_port, rear_port_position=grid_pos)
        if delete_q:
            PortMapping.objects.filter(delete_q).delete()

    if new_mappings_to_create:
        PortMapping.objects.bulk_create(new_mappings_to_create)

    if channels_to_update:
        _retrace_affected_paths(wdm_node, trunk_ports)

    return {"added": added, "removed": removed, "changed": changed}


def _retrace_affected_paths(wdm_node, trunk_ports):
    """Retrace CablePaths that traverse cables connected to the node's trunk ports."""
    from dcim.models import CablePath, CableTermination
    from django.contrib.contenttypes.models import ContentType

    rp_ids = [tp.rear_port_id for tp in trunk_ports]
    if not rp_ids:
        return

    rp_ct = ContentType.objects.get_for_model(RearPort)
    cable_ids = (
        CableTermination.objects.filter(termination_type=rp_ct, termination_id__in=rp_ids)
        .values_list("cable_id", flat=True)
        .distinct()
    )

    if not cable_ids:
        return

    q = Q()
    for cid in cable_ids:
        q |= Q(_nodes__contains=[{"cable_id": cid}])
    affected_paths = CablePath.objects.filter(q).distinct()
    for path in affected_paths:
        path.retrace()


class WdmNodeViewSet(NetBoxModelViewSet):
    queryset = WdmNode.objects.prefetch_related("device", "tags")
    serializer_class = WdmNodeSerializer
    filterset_class = WdmNodeFilterSet

    @action(detail=True, methods=["post"], url_path="apply-mapping")
    def apply_mapping(self, request, pk=None):
        """Apply channel-to-port mapping changes atomically."""
        node = self.get_object()

        last_updated = request.data.get("last_updated")
        if last_updated and str(node.last_updated) != last_updated:
            return Response(
                {"detail": "Node was modified since editor loaded. Please reload."},
                status=status.HTTP_409_CONFLICT,
            )

        desired = request.data.get("mapping", {})
        desired = {int(k): (int(v) if v else None) for k, v in desired.items()}

        errors = WdmNode.validate_channel_mapping(node, desired)
        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            result = _apply_mapping(node, desired)

        return Response(result)


class WdmTrunkPortViewSet(NetBoxModelViewSet):
    queryset = WdmTrunkPort.objects.prefetch_related("wdm_node", "rear_port", "tags")
    serializer_class = WdmTrunkPortSerializer
    filterset_class = WdmTrunkPortFilterSet


class WavelengthChannelViewSet(NetBoxModelViewSet):
    queryset = WavelengthChannel.objects.prefetch_related("wdm_node", "tags")
    serializer_class = WavelengthChannelSerializer
    filterset_class = WavelengthChannelFilterSet


class WavelengthServiceViewSet(NetBoxModelViewSet):
    queryset = WavelengthService.objects.prefetch_related("tenant", "tags")
    serializer_class = WavelengthServiceSerializer
    filterset_class = WavelengthServiceFilterSet

    @action(detail=True, methods=["get"], url_path="stitch")
    def stitch(self, request, pk=None):
        """Return the stitched end-to-end wavelength path."""
        service = self.get_object()
        path = service.get_stitched_path()
        return Response(
            {
                "service_id": service.pk,
                "service_name": service.name,
                "wavelength_nm": float(service.wavelength_nm),
                "status": service.status,
                "is_complete": len(path) > 0,
                "hops": path,
            }
        )
```

- [ ] **Step 4: Create api/urls.py**

```python
from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()

router.register("wdm-profiles", views.WdmDeviceTypeProfileViewSet)
router.register("wdm-channel-templates", views.WdmChannelTemplateViewSet)
router.register("wdm-nodes", views.WdmNodeViewSet)
router.register("wdm-trunk-ports", views.WdmTrunkPortViewSet)
router.register("wavelength-channels", views.WavelengthChannelViewSet)
router.register("wavelength-services", views.WavelengthServiceViewSet)

urlpatterns = router.urls
```

- [ ] **Step 5: Write API tests**

Create `tests/test_api.py` with tests for:
- CRUD on each model endpoint (create, list, retrieve, update, delete)
- `apply-mapping` endpoint validation (reject lit channel remap, reject port conflict, 409 concurrent edit)
- `stitch` endpoint returning channel hops

- [ ] **Step 6: Run API tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/test_api.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add netbox_wdm/api/ tests/test_api.py
git commit -m "feat: add REST API for all WDM models with apply-mapping and stitch endpoints"
```

---

## Chunk 8: GraphQL

### Task 13: GraphQL types, filters, schema

**Files:**
- Create: `netbox_wdm/graphql/__init__.py`
- Create: `netbox_wdm/graphql/types.py`
- Create: `netbox_wdm/graphql/filters.py`
- Create: `netbox_wdm/graphql/schema.py`
- Create: `tests/test_graphql.py`

- [ ] **Step 1: Create graphql/__init__.py**

Empty file.

- [ ] **Step 2: Create graphql/types.py**

```python
from typing import Annotated

import strawberry
import strawberry_django

from netbox.graphql.types import NetBoxObjectType

from ..models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


@strawberry_django.type(WdmDeviceTypeProfile, fields="__all__")
class WdmDeviceTypeProfileType(NetBoxObjectType):
    channel_templates: list[Annotated["WdmChannelTemplateType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmChannelTemplate, fields="__all__")
class WdmChannelTemplateType(NetBoxObjectType):
    pass


@strawberry_django.type(WdmNode, fields="__all__")
class WdmNodeInstanceType(NetBoxObjectType):
    trunk_ports: list[Annotated["WdmTrunkPortType", strawberry.lazy(".types")]]
    channels: list[Annotated["WavelengthChannelType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmTrunkPort, fields="__all__")
class WdmTrunkPortType(NetBoxObjectType):
    pass


@strawberry_django.type(WavelengthChannel, fields="__all__")
class WavelengthChannelType(NetBoxObjectType):
    pass


@strawberry_django.type(WavelengthService, fields="__all__")
class WavelengthServiceType(NetBoxObjectType):
    pass
```

- [ ] **Step 3: Create graphql/filters.py**

```python
import strawberry_django

from ..models import WavelengthChannel, WavelengthService, WdmDeviceTypeProfile, WdmNode


@strawberry_django.filters.filter(WdmDeviceTypeProfile)
class WdmDeviceTypeProfileFilter:
    id: int | None
    node_type: str | None
    grid: str | None


@strawberry_django.filters.filter(WdmNode)
class WdmNodeFilter:
    id: int | None
    node_type: str | None
    grid: str | None
    device_id: int | None


@strawberry_django.filters.filter(WavelengthChannel)
class WavelengthChannelFilter:
    id: int | None
    wdm_node_id: int | None
    status: str | None
    grid_position: int | None


@strawberry_django.filters.filter(WavelengthService)
class WavelengthServiceFilter:
    id: int | None
    name: str | None
    status: str | None
```

- [ ] **Step 4: Create graphql/schema.py**

```python
import strawberry
import strawberry_django

from .types import (
    WavelengthChannelType,
    WavelengthServiceType,
    WdmChannelTemplateType,
    WdmDeviceTypeProfileType,
    WdmNodeInstanceType,
    WdmTrunkPortType,
)


@strawberry.type
class WdmQuery:
    wdm_device_type_profile: WdmDeviceTypeProfileType = strawberry_django.field()
    wdm_device_type_profile_list: list[WdmDeviceTypeProfileType] = strawberry_django.field()

    wdm_channel_template: WdmChannelTemplateType = strawberry_django.field()
    wdm_channel_template_list: list[WdmChannelTemplateType] = strawberry_django.field()

    wdm_node: WdmNodeInstanceType = strawberry_django.field()
    wdm_node_list: list[WdmNodeInstanceType] = strawberry_django.field()

    wdm_trunk_port: WdmTrunkPortType = strawberry_django.field()
    wdm_trunk_port_list: list[WdmTrunkPortType] = strawberry_django.field()

    wavelength_channel: WavelengthChannelType = strawberry_django.field()
    wavelength_channel_list: list[WavelengthChannelType] = strawberry_django.field()

    wavelength_service: WavelengthServiceType = strawberry_django.field()
    wavelength_service_list: list[WavelengthServiceType] = strawberry_django.field()


schema = [WdmQuery]
```

- [ ] **Step 5: Write GraphQL smoke tests**

Create `tests/test_graphql.py`:

```python
"""Smoke tests for GraphQL types and schema."""

import pytest


@pytest.mark.django_db
class TestGraphQLImports:
    def test_types_import(self):
        from netbox_wdm.graphql.types import (
            WavelengthChannelType,
            WavelengthServiceType,
            WdmChannelTemplateType,
            WdmDeviceTypeProfileType,
            WdmNodeInstanceType,
            WdmTrunkPortType,
        )

        assert WdmDeviceTypeProfileType is not None
        assert WdmChannelTemplateType is not None
        assert WdmNodeInstanceType is not None
        assert WdmTrunkPortType is not None
        assert WavelengthChannelType is not None
        assert WavelengthServiceType is not None

    def test_filters_import(self):
        from netbox_wdm.graphql.filters import (
            WavelengthChannelFilter,
            WavelengthServiceFilter,
            WdmDeviceTypeProfileFilter,
            WdmNodeFilter,
        )

        assert WdmDeviceTypeProfileFilter is not None
        assert WdmNodeFilter is not None
        assert WavelengthChannelFilter is not None
        assert WavelengthServiceFilter is not None

    def test_schema_import(self):
        from netbox_wdm.graphql.schema import schema

        assert isinstance(schema, list)
        assert len(schema) == 1
```

- [ ] **Step 6: Run GraphQL tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/test_graphql.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add netbox_wdm/graphql/ tests/test_graphql.py
git commit -m "feat: add GraphQL types, filters, and schema for all WDM models"
```

---

## Chunk 9: Signals & ROADM Editor

### Task 14: Signal handler for auto-creating WdmNode

**Files:**
- Modify: `netbox_wdm/signals.py`

- [ ] **Step 1: Implement signals.py**

```python
from django.db.models.signals import post_save


def _device_post_save(sender, instance, created, **kwargs):
    """Auto-create WdmNode when a Device is created from a DeviceType with a WDM profile."""
    if not created:
        return

    from .models import WdmDeviceTypeProfile, WdmNode

    try:
        profile = WdmDeviceTypeProfile.objects.get(device_type=instance.device_type)
    except WdmDeviceTypeProfile.DoesNotExist:
        return

    WdmNode.objects.create(
        device=instance,
        node_type=profile.node_type,
        grid=profile.grid,
    )


def connect_signals():
    """Connect device signals. Called from AppConfig.ready()."""
    from dcim.models import Device

    post_save.connect(_device_post_save, sender=Device, dispatch_uid="wdm_device_post_save")
```

- [ ] **Step 2: Commit**

```bash
git add netbox_wdm/signals.py
git commit -m "feat: add signal handler to auto-create WdmNode on device creation"
```

### Task 15: TypeScript wavelength editor

**Files:**
- Create: `netbox_wdm/static/netbox_wdm/package.json`
- Create: `netbox_wdm/static/netbox_wdm/tsconfig.json`
- Create: `netbox_wdm/static/netbox_wdm/bundle.cjs`
- Create: `netbox_wdm/static/netbox_wdm/src/wavelength-editor-types.ts`
- Create: `netbox_wdm/static/netbox_wdm/src/wavelength-editor.ts`

- [ ] **Step 1: Create static directory structure**

```bash
mkdir -p netbox_wdm/static/netbox_wdm/src netbox_wdm/static/netbox_wdm/dist
```

- [ ] **Step 2: Create package.json**

```json
{
  "private": true,
  "scripts": {
    "build": "node bundle.cjs",
    "watch": "node bundle.cjs --watch",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "esbuild": "^0.27.4",
    "typescript": "~5.8.0"
  }
}
```

- [ ] **Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2016",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "declaration": false,
    "sourceMap": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 4: Create bundle.cjs**

```javascript
const esbuild = require('esbuild');
const path = require('path');

const isWatch = process.argv.includes('--watch');

const shared = {
  bundle: true,
  minify: !isWatch,
  sourcemap: 'linked',
  target: 'es2016',
  format: 'iife',
  logLevel: 'info',
};

const entries = [
  {
    entryPoints: [path.join(__dirname, 'src', 'wavelength-editor.ts')],
    globalName: 'WavelengthEditor',
    outfile: path.join(__dirname, 'dist', 'wavelength-editor.min.js'),
  },
];

async function main() {
  if (isWatch) {
    for (const entry of entries) {
      const ctx = await esbuild.context({ ...shared, ...entry });
      await ctx.watch();
    }
    console.log('Watching for changes...');
  } else {
    await Promise.all(entries.map((entry) => esbuild.build({ ...shared, ...entry })));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

- [ ] **Step 5: Create wavelength-editor-types.ts**

```typescript
export interface ChannelData {
  id: number;
  grid_position: number;
  wavelength_nm: number;
  label: string;
  front_port_id: number | null;
  front_port_name: string | null;
  status: 'available' | 'reserved' | 'lit';
  service_name: string | null;
}

export interface PortData {
  id: number;
  name: string;
}

export interface EditorConfig {
  nodeId: number;
  nodeType: string;
  lastUpdated: string;
  applyUrl: string;
  channels: ChannelData[];
  availablePorts: PortData[];
}
```

- [ ] **Step 6: Create wavelength-editor.ts**

```typescript
import type { ChannelData, EditorConfig, PortData } from './wavelength-editor-types';

interface Change {
  channelId: number;
  oldPortId: number | null;
  newPortId: number | null;
}

function getCsrfToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

function clearElement(el: HTMLElement): void {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

class WavelengthEditor {
  private config: EditorConfig;
  private container: HTMLElement;
  private currentMapping: Map<number, number | null>;
  private initialMapping: Map<number, number | null>;
  private undoStack: Change[] = [];
  private redoStack: Change[] = [];
  private lastUpdated: string;

  private undoBtn!: HTMLButtonElement;
  private redoBtn!: HTMLButtonElement;
  private saveBtn!: HTMLButtonElement;
  private dirtyBadge!: HTMLSpanElement;
  private messageArea!: HTMLDivElement;

  constructor(container: HTMLElement, config: EditorConfig) {
    this.container = container;
    this.config = config;
    this.lastUpdated = config.lastUpdated;

    this.currentMapping = new Map();
    this.initialMapping = new Map();
    for (const ch of config.channels) {
      this.currentMapping.set(ch.id, ch.front_port_id);
      this.initialMapping.set(ch.id, ch.front_port_id);
    }

    this.render();
    this.bindKeyboard();
    this.bindBeforeUnload();
  }

  private render(): void {
    clearElement(this.container);

    this.messageArea = document.createElement('div');
    this.container.appendChild(this.messageArea);

    const toolbar = document.createElement('div');
    toolbar.className = 'd-flex align-items-center gap-2 mb-3';

    this.undoBtn = this.makeButton('mdi mdi-undo', 'Undo', () => this.undo());
    this.redoBtn = this.makeButton('mdi mdi-redo', 'Redo', () => this.redo());
    this.saveBtn = this.makeButton('mdi mdi-content-save', 'Save', () => this.save());
    this.saveBtn.classList.replace('btn-outline-secondary', 'btn-primary');

    this.dirtyBadge = document.createElement('span');
    this.dirtyBadge.className = 'badge bg-warning text-dark ms-2 d-none';
    this.dirtyBadge.textContent = 'Unsaved changes';

    toolbar.appendChild(this.undoBtn);
    toolbar.appendChild(this.redoBtn);
    toolbar.appendChild(this.saveBtn);
    toolbar.appendChild(this.dirtyBadge);
    this.container.appendChild(toolbar);

    const table = document.createElement('table');
    table.className = 'table table-sm table-hover';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const h of ['Grid Pos', 'Label', 'Wavelength (nm)', 'Port Assignment', 'Status']) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = h;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const sorted = [...this.config.channels].sort((a, b) => a.grid_position - b.grid_position);
    for (const ch of sorted) {
      const tr = document.createElement('tr');
      tr.dataset.channelId = String(ch.id);

      this.addCell(tr, String(ch.grid_position));
      this.addCell(tr, ch.label);
      this.addCell(tr, String(ch.wavelength_nm));

      const portTd = document.createElement('td');
      if (ch.status === 'available') {
        const select = this.buildPortSelect(ch);
        portTd.appendChild(select);
      } else {
        const span = document.createElement('span');
        const lockIcon = document.createElement('i');
        lockIcon.className = 'mdi mdi-lock me-1';
        if (ch.service_name) {
          lockIcon.title = ch.service_name;
        }
        span.appendChild(lockIcon);
        span.appendChild(document.createTextNode(ch.front_port_name || 'Unassigned'));
        portTd.appendChild(span);
      }
      tr.appendChild(portTd);

      const statusTd = document.createElement('td');
      const badge = document.createElement('span');
      if (ch.status === 'lit') {
        badge.className = 'badge bg-success';
        badge.textContent = 'Lit';
      } else if (ch.status === 'reserved') {
        badge.className = 'badge bg-warning';
        badge.textContent = 'Reserved';
      } else {
        badge.className = 'badge bg-secondary';
        badge.textContent = 'Available';
      }
      statusTd.appendChild(badge);
      tr.appendChild(statusTd);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    this.container.appendChild(table);

    this.updateToolbar();
  }

  private addCell(tr: HTMLTableRowElement, text: string): void {
    const td = document.createElement('td');
    td.textContent = text;
    tr.appendChild(td);
  }

  private buildPortSelect(ch: ChannelData): HTMLSelectElement {
    const select = document.createElement('select');
    select.className = 'form-select form-select-sm';
    select.dataset.channelId = String(ch.id);

    const unassigned = document.createElement('option');
    unassigned.value = '';
    unassigned.textContent = '-- Unassigned --';
    select.appendChild(unassigned);

    const currentPortId = this.currentMapping.get(ch.id);
    const availableIds = new Set(this.config.availablePorts.map(p => p.id));

    if (ch.front_port_id && !availableIds.has(ch.front_port_id)) {
      const opt = document.createElement('option');
      opt.value = String(ch.front_port_id);
      opt.textContent = ch.front_port_name || `Port ${ch.front_port_id}`;
      select.appendChild(opt);
    }

    const otherAssigned = new Map<number, string>();
    for (const other of this.config.channels) {
      if (other.id !== ch.id && other.status === 'available' && other.front_port_id && !availableIds.has(other.front_port_id)) {
        otherAssigned.set(other.front_port_id, other.front_port_name || `Port ${other.front_port_id}`);
      }
    }

    for (const port of this.config.availablePorts) {
      const opt = document.createElement('option');
      opt.value = String(port.id);
      opt.textContent = port.name;
      select.appendChild(opt);
    }

    for (const [portId, portName] of otherAssigned) {
      const opt = document.createElement('option');
      opt.value = String(portId);
      opt.textContent = portName;
      select.appendChild(opt);
    }

    select.value = currentPortId ? String(currentPortId) : '';

    select.addEventListener('change', () => {
      const newPortId = select.value ? Number(select.value) : null;
      const oldPortId = this.currentMapping.get(ch.id) ?? null;
      if (newPortId === oldPortId) return;

      this.currentMapping.set(ch.id, newPortId);
      this.undoStack.push({ channelId: ch.id, oldPortId, newPortId });
      this.redoStack = [];
      this.updateToolbar();
    });

    return select;
  }

  private makeButton(iconClass: string, label: string, onClick: () => void): HTMLButtonElement {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-outline-secondary';
    btn.title = label;
    const icon = document.createElement('i');
    icon.className = iconClass;
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(' ' + label));
    btn.addEventListener('click', onClick);
    return btn;
  }

  private isDirty(): boolean {
    for (const [chId, portId] of this.currentMapping) {
      if (this.initialMapping.get(chId) !== portId) return true;
    }
    return false;
  }

  private updateToolbar(): void {
    this.undoBtn.disabled = this.undoStack.length === 0;
    this.redoBtn.disabled = this.redoStack.length === 0;
    const dirty = this.isDirty();
    this.saveBtn.disabled = !dirty;
    if (dirty) {
      this.dirtyBadge.classList.remove('d-none');
    } else {
      this.dirtyBadge.classList.add('d-none');
    }
  }

  private undo(): void {
    const change = this.undoStack.pop();
    if (!change) return;
    this.currentMapping.set(change.channelId, change.oldPortId);
    this.redoStack.push(change);
    this.syncSelect(change.channelId);
    this.updateToolbar();
  }

  private redo(): void {
    const change = this.redoStack.pop();
    if (!change) return;
    this.currentMapping.set(change.channelId, change.newPortId);
    this.undoStack.push(change);
    this.syncSelect(change.channelId);
    this.updateToolbar();
  }

  private syncSelect(channelId: number): void {
    const select = this.container.querySelector(
      `select[data-channel-id="${channelId}"]`
    ) as HTMLSelectElement | null;
    if (select) {
      const val = this.currentMapping.get(channelId);
      select.value = val ? String(val) : '';
    }
  }

  private async save(): Promise<void> {
    this.saveBtn.disabled = true;
    clearElement(this.saveBtn);
    this.saveBtn.textContent = 'Saving...';

    const mapping: Record<string, number | null> = {};
    for (const [chId, portId] of this.currentMapping) {
      mapping[String(chId)] = portId;
    }

    try {
      const resp = await fetch(this.config.applyUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({
          mapping,
          last_updated: this.lastUpdated,
        }),
      });

      if (resp.status === 200) {
        const data = await resp.json() as { added: number; removed: number; changed: number; last_updated?: string };
        if (data.last_updated) {
          this.lastUpdated = data.last_updated;
        }
        for (const [chId, portId] of this.currentMapping) {
          this.initialMapping.set(chId, portId);
        }
        this.undoStack = [];
        this.redoStack = [];
        this.showMessage(
          'success',
          `Saved: ${data.added} added, ${data.removed} removed, ${data.changed} changed.`
        );
      } else if (resp.status === 409) {
        this.showConflict();
      } else {
        const data = await resp.json() as { errors?: string[] };
        const msg = data.errors ? data.errors.join(', ') : 'Validation error';
        this.showMessage('danger', msg);
      }
    } catch (err) {
      this.showMessage('danger', 'Network error: ' + (err as Error).message);
    }

    clearElement(this.saveBtn);
    const icon = document.createElement('i');
    icon.className = 'mdi mdi-content-save';
    this.saveBtn.appendChild(icon);
    this.saveBtn.appendChild(document.createTextNode(' Save'));
    this.updateToolbar();
  }

  private showMessage(type: string, text: string): void {
    clearElement(this.messageArea);
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');
    alert.textContent = text;
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('data-bs-dismiss', 'alert');
    alert.appendChild(closeBtn);
    this.messageArea.appendChild(alert);
  }

  private showConflict(): void {
    clearElement(this.messageArea);
    const alert = document.createElement('div');
    alert.className = 'alert alert-warning';
    alert.setAttribute('role', 'alert');
    alert.textContent = 'This node was modified by another user. ';
    const reloadBtn = document.createElement('button');
    reloadBtn.type = 'button';
    reloadBtn.className = 'btn btn-sm btn-outline-warning ms-2';
    reloadBtn.textContent = 'Reload';
    reloadBtn.addEventListener('click', () => window.location.reload());
    alert.appendChild(reloadBtn);
    this.messageArea.appendChild(alert);
  }

  private bindKeyboard(): void {
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        if (e.shiftKey) {
          e.preventDefault();
          this.redo();
        } else {
          e.preventDefault();
          this.undo();
        }
      }
    });
  }

  private bindBeforeUnload(): void {
    window.addEventListener('beforeunload', (e: BeforeUnloadEvent) => {
      if (this.isDirty()) {
        e.preventDefault();
      }
    });
  }
}

// Entry point
const config = (window as unknown as { WAVELENGTH_EDITOR_CONFIG?: EditorConfig }).WAVELENGTH_EDITOR_CONFIG;
if (config) {
  const container = document.getElementById('wavelength-editor-container');
  if (container) {
    new WavelengthEditor(container, config);
  }
}
```

- [ ] **Step 7: Build TypeScript**

```bash
cd netbox_wdm/static/netbox_wdm && npm install && npm run build
```

- [ ] **Step 8: Commit**

```bash
git add netbox_wdm/static/
git commit -m "feat: add TypeScript wavelength editor with undo/redo and save"
```

---

## Chunk 10: ROADM Tests & DevContainer

### Task 16: ROADM editor tests

**Files:**
- Create: `tests/test_roadm.py`

- [ ] **Step 1: Write ROADM apply-mapping tests**

Test the `_apply_mapping` function and the API endpoint:
- Test adding a port mapping creates PortMapping records
- Test removing a port mapping deletes PortMapping records
- Test concurrent edit returns 409
- Test validation rejects lit channel remap via API

- [ ] **Step 2: Run all tests**

Run: `cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_roadm.py
git commit -m "feat: add ROADM apply-mapping tests"
```

### Task 17: DevContainer setup

**Files:**
- Create: `.devcontainer/devcontainer.json`
- Create: `.devcontainer/docker-compose.yml`
- Create: `.devcontainer/Dockerfile-plugin_dev`
- Create: `.devcontainer/entrypoint-dev.sh`
- Create: `.devcontainer/requirements-dev.txt`
- Create: `.devcontainer/configuration/configuration.py`
- Create: `.devcontainer/configuration/plugins.py`
- Create: `.devcontainer/configuration/logging.py`

- [ ] **Step 1: Create all devcontainer files**

Create the following files with content from the spec (lines 623-843):
- `.devcontainer/devcontainer.json` (spec lines 625-651)
- `.devcontainer/docker-compose.yml` (spec lines 655-692)
- `.devcontainer/Dockerfile-plugin_dev` (spec lines 696-732)
- `.devcontainer/entrypoint-dev.sh` (spec lines 736-742)
- `.devcontainer/requirements-dev.txt` (spec lines 746-754)
- `.devcontainer/configuration/configuration.py` (spec lines 794-830)
- `.devcontainer/configuration/plugins.py` (spec lines 834-837)
- `.devcontainer/configuration/logging.py` (spec lines 841-843)

Key adaptations from netbox-fms:
- Container name: `netbox-wdm-devcontainer` (not `netbox-fms-devcontainer`)
- Volume mount: `/opt/netbox-wdm` (not `/opt/netbox-fms`)
- Plugin: `netbox_wdm` (not `netbox_fms`)
- Port: 8090

- [ ] **Step 2: Create env template files**

Create `.devcontainer/env/` directory with:
- `netbox.env` (spec lines 758-776)
- `postgres.env` (spec lines 780-784)
- `redis.env` (spec lines 788-790)

- [ ] **Step 3: Commit**

```bash
git add .devcontainer/
git commit -m "feat: add devcontainer configuration for NetBox development"
```

### Task 18: CI/CD workflows

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/publish.yml`

- [ ] **Step 1: Create CI and publish workflows**

Create the following files with content from the spec:
- `.github/workflows/ci.yml` (spec lines 489-596)
- `.github/workflows/publish.yml` (spec lines 600-621)

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "feat: add CI and PyPI publish GitHub Actions workflows"
```

---

## Chunk 11: Final Verification

### Task 19: Lint and verify

- [ ] **Step 1: Run ruff check**

```bash
ruff check netbox_wdm/
ruff format --check netbox_wdm/
```

Fix any issues.

- [ ] **Step 2: Run full test suite**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v --cov=netbox_wdm --cov-report=term-missing
```

Expected: All tests PASS, coverage > 80%

- [ ] **Step 3: TypeScript typecheck**

```bash
cd netbox_wdm/static/netbox_wdm && npx tsc --noEmit
```

- [ ] **Step 4: Verify plugin loads**

```bash
cd /opt/netbox/netbox && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from netbox_wdm.models import *; from netbox_wdm.forms import *; from netbox_wdm.filters import *; print('OK')"
```

- [ ] **Step 5: Final commit if needed**

Stage only the specific files that were fixed (avoid staging untracked/sensitive files).
