"""Module-scoped overlay: profile anchors, per-module uniqueness, consistency rules."""

import pytest
from dcim.models import Device, DeviceType, Module, ModuleBay, ModuleType, RearPort, RearPortTemplate
from django.core.exceptions import ValidationError

from netbox_wdm.choices import (
    WdmFiberTypeChoices,
    WdmGridChoices,
    WdmLineDirectionChoices,
    WdmLineRoleChoices,
    WdmNodeTypeChoices,
)
from netbox_wdm.models import WdmChannel, WdmLinePort, WdmLinePortPlan, WdmNode, WdmProfile
from netbox_wdm.testing import (
    create_cwdm_mux_dx_type,
    create_cwdm_mux_sf_type,
    create_duplex_mux,
    create_roadm_2d_type,
    create_sf_mux,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cassette_module_type(wdm_manufacturer):
    return ModuleType.objects.create(manufacturer=wdm_manufacturer, model="CASSETTE-8CH")


@pytest.fixture
def chassis(wdm_site, wdm_manufacturer, wdm_roles, cassette_module_type):
    """Bare chassis device with two cassette modules and a WdmNode (no profiles yet)."""
    dt = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="CHASSIS-1RU", slug="chassis-1ru", u_height=1)
    device = Device.objects.create(name="chassis-1", site=wdm_site, device_type=dt, role=wdm_roles["wdm-mux"])
    modules = {}
    for bay_name in ("MUX1", "MUX2"):
        bay = ModuleBay.objects.create(device=device, name=bay_name, position=bay_name)
        modules[bay_name] = Module.objects.create(device=device, module_bay=bay, module_type=cassette_module_type)
    node = WdmNode.objects.create(device=device, node_type=WdmNodeTypeChoices.TERMINAL_MUX, grid=WdmGridChoices.CWDM)
    return device, node, modules


class TestProfileAnchor:
    def test_profile_requires_exactly_one_anchor(self, wdm_manufacturer, cassette_module_type):
        dt = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="DT-X", slug="dt-x")
        with pytest.raises(ValidationError):
            WdmProfile(node_type=WdmNodeTypeChoices.TERMINAL_MUX, grid=WdmGridChoices.CWDM).full_clean()
        with pytest.raises(ValidationError):
            WdmProfile(
                device_type=dt,
                module_type=cassette_module_type,
                node_type=WdmNodeTypeChoices.TERMINAL_MUX,
                grid=WdmGridChoices.CWDM,
            ).full_clean()

    def test_module_type_profile_valid(self, cassette_module_type):
        profile = WdmProfile(
            module_type=cassette_module_type,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.CWDM,
            fiber_type=WdmFiberTypeChoices.DUPLEX,
        )
        profile.full_clean()
        profile.save()
        assert profile.anchor == cassette_module_type


class TestModuleScopedUniqueness:
    def test_same_grid_position_on_two_modules(self, chassis):
        device, node, modules = chassis
        WdmChannel.objects.create(wdm_node=node, module=modules["MUX1"], grid_position=3)
        WdmChannel.objects.create(wdm_node=node, module=modules["MUX2"], grid_position=3)
        assert node.channels.filter(grid_position=3).count() == 2

    def test_duplicate_grid_position_same_module_rejected(self, chassis):
        from django.db import IntegrityError

        device, node, modules = chassis
        WdmChannel.objects.create(wdm_node=node, module=modules["MUX1"], grid_position=3)
        with pytest.raises(IntegrityError):
            WdmChannel.objects.create(wdm_node=node, module=modules["MUX1"], grid_position=3)

    def test_line_port_direction_role_unique_per_module(self, chassis):
        device, node, modules = chassis
        rp1 = RearPort.objects.create(device=device, module=modules["MUX1"], name="MUX1 COM-TX", type="lc", positions=1)
        rp2 = RearPort.objects.create(device=device, module=modules["MUX2"], name="MUX2 COM-TX", type="lc", positions=1)
        WdmLinePort.objects.create(
            wdm_node=node,
            module=modules["MUX1"],
            rear_port=rp1,
            direction=WdmLineDirectionChoices.COMMON,
            role=WdmLineRoleChoices.TX,
        )
        WdmLinePort.objects.create(
            wdm_node=node,
            module=modules["MUX2"],
            rear_port=rp2,
            direction=WdmLineDirectionChoices.COMMON,
            role=WdmLineRoleChoices.TX,
        )
        assert node.line_ports.count() == 2


class TestConsistencyRules:
    def test_channel_module_must_belong_to_node_device(self, chassis, wdm_site, wdm_manufacturer, wdm_roles):
        device, node, modules = chassis
        other_dt = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="CHASSIS-2", slug="chassis-2")
        other = Device.objects.create(name="chassis-2", site=wdm_site, device_type=other_dt, role=wdm_roles["wdm-mux"])
        bay = ModuleBay.objects.create(device=other, name="MUX1", position="MUX1")
        foreign_module = Module.objects.create(device=other, module_bay=bay, module_type=modules["MUX1"].module_type)
        ch = WdmChannel(wdm_node=node, module=foreign_module, grid_position=3)
        with pytest.raises(ValidationError):
            ch.full_clean()

    def test_line_port_rear_port_must_match_module(self, chassis):
        device, node, modules = chassis
        rp_mux2 = RearPort.objects.create(
            device=device, module=modules["MUX2"], name="MUX2 COM-TX", type="lc", positions=1
        )
        lp = WdmLinePort(
            wdm_node=node,
            module=modules["MUX1"],
            rear_port=rp_mux2,
            direction=WdmLineDirectionChoices.COMMON,
            role=WdmLineRoleChoices.TX,
        )
        with pytest.raises(ValidationError):
            lp.full_clean()


class TestLinePortPlan:
    def test_plan_template_must_belong_to_anchor(self, wdm_manufacturer, cassette_module_type):
        dt = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="DT-Y", slug="dt-y")
        rpt_on_dt = RearPortTemplate.objects.create(device_type=dt, name="COM", type="lc", positions=1)
        profile = WdmProfile.objects.create(
            module_type=cassette_module_type,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.CWDM,
        )
        plan = WdmLinePortPlan(
            profile=profile,
            rear_port_template=rpt_on_dt,
            direction=WdmLineDirectionChoices.COMMON,
            role=WdmLineRoleChoices.TX,
        )
        with pytest.raises(ValidationError):
            plan.full_clean()


class TestEffectiveGridAndFixedness:
    def test_module_channel_uses_module_profile_grid(self, chassis, cassette_module_type):
        device, node, modules = chassis
        WdmProfile.objects.create(
            module_type=cassette_module_type,
            node_type=WdmNodeTypeChoices.TERMINAL_MUX,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(wdm_node=node, module=modules["MUX1"], grid_position=1)
        assert ch.effective_grid == WdmGridChoices.DWDM_100GHZ
        # node grid is CWDM; a module-null channel keeps using it
        ch_dev = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        assert ch_dev.effective_grid == WdmGridChoices.CWDM

    def test_roadm_module_channel_not_fixed_on_fixed_node(self, chassis, cassette_module_type):
        device, node, modules = chassis
        WdmProfile.objects.create(
            module_type=cassette_module_type,
            node_type=WdmNodeTypeChoices.ROADM,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        ch = WdmChannel.objects.create(wdm_node=node, module=modules["MUX1"], grid_position=1)
        assert ch.is_fixed is False
        ch_dev = WdmChannel.objects.create(wdm_node=node, grid_position=1)
        assert ch_dev.is_fixed is True


class TestPlanDrivenLinePorts:
    def test_duplex_factory_creates_line_port_plans(self, wdm_manufacturer):
        dt = create_cwdm_mux_dx_type(wdm_manufacturer)
        plans = dt.wdm_profile.line_port_plans.order_by("role")
        assert [(p.rear_port_template.name, p.direction, p.role) for p in plans] == [
            ("COM-RX", "common", "rx"),
            ("COM-TX", "common", "tx"),
        ]

    def test_duplex_node_auto_populates_line_ports(self, wdm_site, wdm_manufacturer, wdm_roles):
        dt = create_cwdm_mux_dx_type(wdm_manufacturer)
        bundle = create_duplex_mux(wdm_site, dt, wdm_roles["wdm-mux"], "MUX-LP-A")
        assert bundle.line_ports["tx"].rear_port.name == "COM-TX"
        assert bundle.line_ports["rx"].rear_port.name == "COM-RX"

    def test_sf_node_auto_populates_bidi_line_port(self, wdm_site, wdm_manufacturer, wdm_roles):
        dt = create_cwdm_mux_sf_type(wdm_manufacturer)
        bundle = create_sf_mux(wdm_site, dt, wdm_roles["wdm-mux"], "MUX-SF-A")
        assert bundle.line_ports["bidi"].role == "bidi"
        assert bundle.line_ports["bidi"].rear_port.name == "COM"

    def test_roadm_line_ports_stay_editable(self, wdm_site, wdm_manufacturer, wdm_roles):
        from netbox_wdm.testing import create_roadm

        dt = create_roadm_2d_type(wdm_manufacturer)
        bundle = create_roadm(wdm_site, dt, wdm_roles["wdm-roadm"], "ROADM-LP-A")
        lp = bundle.line_ports["line_east_tx"]
        # "common"/"rx" isn't used by any of the ROADM's other auto-populated line ports
        # (all four are east/west), so this only exercises fixedness, not the
        # (wdm_node, direction, role) uniqueness constraint.
        lp.direction = "common"
        lp.role = "rx"
        lp.full_clean()  # would raise on a fixed node
