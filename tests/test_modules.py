"""Module-scoped overlay: profile anchors, per-module uniqueness, consistency rules."""

import pytest
from dcim.models import (
    Device,
    DeviceType,
    FrontPortTemplate,
    Module,
    ModuleBay,
    ModuleType,
    RearPort,
    RearPortTemplate,
)
from dcim.models.device_component_templates import PortTemplateMapping
from django.core.exceptions import ValidationError

from netbox_wdm.choices import (
    WdmFiberTypeChoices,
    WdmGridChoices,
    WdmLineDirectionChoices,
    WdmLineRoleChoices,
    WdmNodeTypeChoices,
)
from netbox_wdm.models import (
    WdmChannel,
    WdmChannelPlan,
    WdmLinePort,
    WdmLinePortPlan,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
    WdmWavelengthPathChannel,
)
from netbox_wdm.testing import (
    create_cwdm_mux_dx_type,
    create_cwdm_mux_sf_type,
    create_duplex_mux,
    create_roadm_2d_type,
    create_sf_mux,
)
from netbox_wdm.wdm_constants import DWDM_100GHZ_CHANNELS

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


class TestAmplifierProfileLinePorts:
    def test_amplifier_profile_gets_line_ports_but_no_channels(self, wdm_site, wdm_manufacturer, wdm_roles):
        """_create_line_ports is intentionally not amplifier-gated, unlike _create_channels:

        amplifiers are pass-through devices whose trunk rear ports are the line ports
        themselves, so an amplifier profile's line port plans must still populate, while
        its (nonexistent) channel plans never do.
        """
        dt = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="EDFA-TEST", slug="edfa-test")
        rpt = RearPortTemplate.objects.create(device_type=dt, name="LINE-OUT", type="lc-apc", positions=1)
        profile = WdmProfile.objects.create(
            device_type=dt,
            node_type=WdmNodeTypeChoices.AMPLIFIER,
            grid=WdmGridChoices.DWDM_100GHZ,
        )
        WdmLinePortPlan.objects.create(
            profile=profile,
            rear_port_template=rpt,
            direction=WdmLineDirectionChoices.COMMON,
            role=WdmLineRoleChoices.BIDI,
        )
        device = Device.objects.create(name="AMP-A", site=wdm_site, device_type=dt, role=wdm_roles["wdm-amplifier"])
        node = WdmNode.objects.create(
            device=device, node_type=WdmNodeTypeChoices.AMPLIFIER, grid=WdmGridChoices.DWDM_100GHZ
        )
        assert node.channels.count() == 0
        assert node.line_ports.count() == 1
        assert node.line_ports.get().role == WdmLineRoleChoices.BIDI


class TestModularAutoPopulate:
    def test_chassis_gets_channels_and_line_ports_per_module(self, wdm_site, wdm_manufacturer, wdm_roles):
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-A", mt, bays=("MUX1", "MUX2"))
        node = bundle.node
        assert node.channels.filter(module=bundle.modules["MUX1"]).count() == 8
        assert node.channels.filter(module=bundle.modules["MUX2"]).count() == 8
        # {module} resolution: the MUX1 cassette's CH1-MUX port carries the bay position prefix
        ch1 = node.channels.filter(module=bundle.modules["MUX1"], grid_position=1).first()
        assert ch1.mux_front_port.name == "MUX1 CH1-MUX"
        assert ch1.mux_front_port.module == bundle.modules["MUX1"]
        # per-module line ports
        assert node.line_ports.filter(module=bundle.modules["MUX1"]).count() == 2
        assert node.line_ports.filter(module=bundle.modules["MUX2"]).count() == 2

    def test_same_wavelength_present_on_both_modules(self, wdm_site, wdm_manufacturer, wdm_roles):
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-B", mt)
        assert bundle.node.channels.filter(grid_position=1).count() == 2


class TestModuleLifecycleSignals:
    def test_installing_module_populates_channels(
        self, wdm_site, wdm_manufacturer, wdm_roles, django_capture_on_commit_callbacks
    ):
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-SIG", mt, bays=("MUX1",))
        bay = ModuleBay.objects.create(device=bundle.device, name="MUX2", position="MUX2")
        with django_capture_on_commit_callbacks(execute=True):
            new_module = Module.objects.create(device=bundle.device, module_bay=bay, module_type=mt)
        assert bundle.node.channels.filter(module=new_module).count() == 8
        assert bundle.node.line_ports.filter(module=new_module).count() == 2

    def test_removing_module_cleans_up_without_protect_error(self, wdm_site, wdm_manufacturer, wdm_roles):
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-DEL", mt)
        node = bundle.node
        victim = bundle.modules["MUX2"]
        victim_pk = victim.pk
        assert node.line_ports.filter(module=victim).exists()
        victim.delete()  # must not raise ProtectedError from WdmLinePort.rear_port
        # delete() clears victim.pk; filter by the saved pk instead of the (now unsaved) instance
        assert not node.channels.filter(module_id=victim_pk).exists()
        assert not node.line_ports.filter(module_id=victim_pk).exists()
        # the surviving module is untouched
        assert node.channels.filter(module=bundle.modules["MUX1"]).count() == 8

    def test_removing_pathed_module_cascades_wavelength_path(
        self, wdm_site, wdm_manufacturer, wdm_roles, django_capture_on_commit_callbacks
    ):
        """A module whose channels are part of a live wavelength path must still be
        removable: wavelength paths are derived data, not something a channel
        deletion should be blocked by (per the module-scoped-wdm design ruling)."""
        from netbox_wdm.testing import (
            cable_duplex_through_pp_pair,
            create_cwdm_cassette_module_type,
            create_fiber_pp_type,
            create_modular_chassis,
            create_patch_panel,
        )
        from netbox_wdm.trace import rebuild_wavelength_paths_for_node

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle_a = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-PATH-A", mt, bays=("MUX1",))
        bundle_b = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-PATH-B", mt, bays=("MUX1",))
        dt_pp = create_fiber_pp_type(wdm_manufacturer)
        pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "PP-PATH-A")
        pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], "PP-PATH-B")

        node_a = bundle_a.node
        node_b = bundle_b.node
        victim = bundle_a.modules["MUX1"]
        survivor = bundle_b.modules["MUX1"]

        cable_duplex_through_pp_pair(
            device_a_tx_rp=RearPort.objects.get(device=bundle_a.device, name="MUX1 COM-TX"),
            device_a_rx_rp=RearPort.objects.get(device=bundle_a.device, name="MUX1 COM-RX"),
            pp_a_device=pp_a,
            pp_b_device=pp_b,
            device_b_rx_rp=RearPort.objects.get(device=bundle_b.device, name="MUX1 COM-RX"),
            device_b_tx_rp=RearPort.objects.get(device=bundle_b.device, name="MUX1 COM-TX"),
            label_prefix="PATH",
        )
        rebuild_wavelength_paths_for_node(node_a)
        rebuild_wavelength_paths_for_node(node_b)

        assert WdmWavelengthPath.objects.filter(path_channels__channel__module=victim).exists()
        assert WdmWavelengthPath.objects.filter(path_channels__channel__module=survivor).exists()

        victim_pk = victim.pk
        with django_capture_on_commit_callbacks(execute=True):
            victim.delete()  # must not raise ProtectedError from WdmWavelengthPathChannel.channel

        assert not WdmChannel.objects.filter(module_id=victim_pk).exists()
        assert not WdmLinePort.objects.filter(module_id=victim_pk).exists()
        assert not WdmWavelengthPathChannel.objects.filter(channel__module_id=victim_pk).exists()
        # no dangling one-entry (broken) paths left over from the half that cascaded away
        assert not any(path.path_channels.count() < 2 for path in WdmWavelengthPath.objects.all())
        # the far node's channels are back to having no path entries at all -- the
        # only path they were part of was pruned along with the victim's half
        for channel in WdmChannel.objects.filter(module=survivor):
            assert not channel.wavelength_path_entries.exists()


class TestDeviceLevelRearPortDeletion:
    def test_deleting_rear_port_cascades_line_port(self, wdm_site, wdm_manufacturer, wdm_roles):
        """Device-level (non-modular) line ports also cascade when their rear port is
        deleted directly. WdmLinePort.rear_port is CASCADE, not PROTECT, matching the
        module-scoped case: this is a deliberate, silent behavior change (deleting a
        COM rear port used to raise ProtectedError; now it just takes the line port
        down with it), so it needs its own coverage independent of module removal."""
        dt = create_cwdm_mux_dx_type(wdm_manufacturer)
        bundle = create_duplex_mux(wdm_site, dt, wdm_roles["wdm-mux"], "MUX-RP-DEL")
        node = bundle.node
        channel_count = node.channels.count()
        tx_rear_port = bundle.line_ports["tx"].rear_port

        tx_rear_port.delete()  # must not raise ProtectedError from WdmLinePort.rear_port

        assert not WdmLinePort.objects.filter(wdm_node=node, role=WdmLineRoleChoices.TX).exists()
        assert WdmLinePort.objects.filter(wdm_node=node, role=WdmLineRoleChoices.RX).exists()
        assert node.channels.count() == channel_count


class TestModularTracing:
    @pytest.fixture
    def chassis_two_spans(self, wdm_site, wdm_manufacturer, wdm_roles):
        """One chassis with 2 cassettes, each cabled through a PP pair to its own peer chassis."""
        from netbox_wdm.testing import (
            cable_duplex_through_pp_pair,
            create_cwdm_cassette_module_type,
            create_fiber_pp_type,
            create_modular_chassis,
            create_patch_panel,
        )

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        dt_pp = create_fiber_pp_type(wdm_manufacturer)
        hub = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "HUB", mt, bays=("MUX1", "MUX2"))
        peer1 = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "PEER1", mt, bays=("MUX1",))
        peer2 = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "PEER2", mt, bays=("MUX1",))

        def lp(bundle, bay, role):
            return bundle.node.line_ports.get(module=bundle.modules[bay], role=role)

        for i, (bay, peer) in enumerate((("MUX1", peer1), ("MUX2", peer2)), start=1):
            pp_a = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], f"PP-A{i}")
            pp_b = create_patch_panel(wdm_site, dt_pp, wdm_roles["fiber-pp"], f"PP-B{i}")
            cable_duplex_through_pp_pair(
                device_a_tx_rp=lp(hub, bay, "tx").rear_port,
                device_a_rx_rp=lp(hub, bay, "rx").rear_port,
                pp_a_device=pp_a,
                pp_b_device=pp_b,
                device_b_rx_rp=lp(peer, "MUX1", "rx").rear_port,
                device_b_tx_rp=lp(peer, "MUX1", "tx").rear_port,
                label_prefix=f"SPAN{i}",
            )
        return hub, peer1, peer2

    def test_same_wavelength_traces_per_cassette(self, chassis_two_spans):
        from netbox_wdm.models import WdmWavelengthPathChannel
        from netbox_wdm.trace import rebuild_wavelength_paths_for_node

        hub, peer1, peer2 = chassis_two_spans
        for bundle in (hub, peer1, peer2):
            rebuild_wavelength_paths_for_node(bundle.node)

        ch_mux1 = hub.node.channels.get(module=hub.modules["MUX1"], grid_position=1)
        entry = WdmWavelengthPathChannel.objects.get(channel=ch_mux1, sequence=0)
        far = entry.path.path_channels.get(sequence=1).channel
        assert far.wdm_node == peer1.node

        ch_mux2 = hub.node.channels.get(module=hub.modules["MUX2"], grid_position=1)
        entry2 = WdmWavelengthPathChannel.objects.get(channel=ch_mux2, sequence=0)
        far2 = entry2.path.path_channels.get(sequence=1).channel
        assert far2.wdm_node == peer2.node

    def test_reverse_direction_selects_correct_cassette(self, chassis_two_spans):
        from netbox_wdm.models import WdmWavelengthPathChannel
        from netbox_wdm.trace import rebuild_wavelength_paths_for_node

        hub, peer1, peer2 = chassis_two_spans
        for bundle in (hub, peer1, peer2):
            rebuild_wavelength_paths_for_node(bundle.node)

        ch_peer2 = peer2.node.channels.get(grid_position=1)
        entry = WdmWavelengthPathChannel.objects.get(channel=ch_peer2, sequence=0)
        far = entry.path.path_channels.get(sequence=1).channel
        assert far.wdm_node == hub.node
        assert far.module == hub.modules["MUX2"]


def _create_roadm_cassette_module_type(manufacturer, num_channels=2):
    """Small ROADM-profile cassette ModuleType: ADD/DROP front ports, LINE-{dir}-TX/RX rear ports.

    Mirrors `create_cwdm_cassette_module_type`'s {module}-tokenized template pattern but
    scaled down (2 channels, one direction wired to PortTemplateMappings) since this is
    only used to exercise the ROADM side of a mixed-group chassis in tests.
    """
    mt, _ = ModuleType.objects.get_or_create(manufacturer=manufacturer, model=f"ROADM-CASSETTE-{num_channels}CH")

    line_east_tx, _ = RearPortTemplate.objects.get_or_create(
        module_type=mt, name="{module} LINE-EAST-TX", defaults={"type": "lc-apc", "positions": num_channels}
    )
    line_east_rx, _ = RearPortTemplate.objects.get_or_create(
        module_type=mt, name="{module} LINE-EAST-RX", defaults={"type": "lc-apc", "positions": num_channels}
    )
    line_west_tx, _ = RearPortTemplate.objects.get_or_create(
        module_type=mt, name="{module} LINE-WEST-TX", defaults={"type": "lc-apc", "positions": num_channels}
    )
    line_west_rx, _ = RearPortTemplate.objects.get_or_create(
        module_type=mt, name="{module} LINE-WEST-RX", defaults={"type": "lc-apc", "positions": num_channels}
    )

    add_fps, drop_fps = [], []
    for i in range(1, num_channels + 1):
        fp_add, _ = FrontPortTemplate.objects.get_or_create(
            module_type=mt, name=f"{{module}} ADD-{i:02d}", defaults={"type": "lc-upc"}
        )
        fp_drop, _ = FrontPortTemplate.objects.get_or_create(
            module_type=mt, name=f"{{module}} DROP-{i:02d}", defaults={"type": "lc-upc"}
        )
        add_fps.append(fp_add)
        drop_fps.append(fp_drop)

    for pos_idx, (fp_add, fp_drop) in enumerate(zip(add_fps, drop_fps, strict=True), start=1):
        PortTemplateMapping.objects.get_or_create(
            module_type=mt,
            front_port=fp_add,
            rear_port=line_east_tx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )
        PortTemplateMapping.objects.get_or_create(
            module_type=mt,
            front_port=fp_drop,
            rear_port=line_east_rx,
            defaults={"front_port_position": 1, "rear_port_position": pos_idx},
        )

    profile, _ = WdmProfile.objects.get_or_create(
        module_type=mt,
        defaults={
            "node_type": WdmNodeTypeChoices.ROADM,
            "grid": WdmGridChoices.DWDM_100GHZ,
            "fiber_type": WdmFiberTypeChoices.DUPLEX,
        },
    )
    for i, (fp_add, fp_drop) in enumerate(zip(add_fps, drop_fps, strict=True)):
        pos, label, wl = DWDM_100GHZ_CHANNELS[i]
        WdmChannelPlan.objects.get_or_create(
            profile=profile,
            grid_position=pos,
            defaults={
                "wavelength_nm": wl,
                "label": label,
                "mux_front_port_template": fp_add,
                "demux_front_port_template": fp_drop,
            },
        )
    for rpt, direction, role in (
        (line_east_tx, WdmLineDirectionChoices.EAST, WdmLineRoleChoices.TX),
        (line_east_rx, WdmLineDirectionChoices.EAST, WdmLineRoleChoices.RX),
        (line_west_tx, WdmLineDirectionChoices.WEST, WdmLineRoleChoices.TX),
        (line_west_rx, WdmLineDirectionChoices.WEST, WdmLineRoleChoices.RX),
    ):
        WdmLinePortPlan.objects.get_or_create(
            profile=profile,
            rear_port_template=rpt,
            defaults={"direction": direction, "role": role},
        )
    return mt


@pytest.fixture
def mixed_chassis(wdm_site, wdm_manufacturer, wdm_roles):
    """Chassis mixing a fixed cassette module (MUX1) with a ROADM-profile module (ROADM1)."""
    from netbox_wdm.testing import create_cwdm_cassette_module_type, ensure_populated

    mt_fixed = create_cwdm_cassette_module_type(wdm_manufacturer)
    mt_roadm = _create_roadm_cassette_module_type(wdm_manufacturer)

    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=wdm_manufacturer,
        slug="wdm-chassis-mixed",
        defaults={"model": "WDM-CHASSIS-MIXED", "u_height": 1},
    )
    device = Device.objects.create(name="CHASSIS-MIXED", site=wdm_site, device_type=dt, role=wdm_roles["wdm-mux"])
    bay_fixed = ModuleBay.objects.create(device=device, name="MUX1", position="MUX1")
    module_fixed = Module.objects.create(device=device, module_bay=bay_fixed, module_type=mt_fixed)
    bay_roadm = ModuleBay.objects.create(device=device, name="ROADM1", position="ROADM1")
    module_roadm = Module.objects.create(device=device, module_bay=bay_roadm, module_type=mt_roadm)

    node = WdmNode.objects.create(device=device)
    ensure_populated(node)

    return node, module_fixed, module_roadm


class TestModularPortSync:
    def test_chassis_in_sync_after_populate(self, wdm_site, wdm_manufacturer, wdm_roles):
        from netbox_wdm.port_sync import check_port_sync
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-PS", mt)
        assert check_port_sync(bundle.node) is True

    def test_broken_mapping_detected_per_module(self, wdm_site, wdm_manufacturer, wdm_roles):
        from dcim.models import PortMapping

        from netbox_wdm.port_sync import check_port_sync
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-PS2", mt)
        victim_ch = bundle.node.channels.filter(module=bundle.modules["MUX2"]).first()
        PortMapping.objects.filter(front_port=victim_ch.mux_front_port).delete()
        assert check_port_sync(bundle.node) is False

    def test_mixed_fixed_and_roadm_module_chassis(self, mixed_chassis):
        """A chassis mixing a fixed cassette module with a ROADM-profile module: each
        group is judged by its own fixedness, and compute_sync_diff/apply_sync operate
        correctly on module-scoped data (not just check_port_sync)."""
        from dcim.models import PortMapping

        from netbox_wdm.port_sync import apply_sync, check_port_sync, compute_sync_diff

        node, module_fixed, module_roadm = mixed_chassis
        device = node.device

        # a. each group (fixed cassette, ROADM module) is judged by its own fixedness,
        # and both are in sync right after auto-populate
        assert node.channels.filter(module=module_fixed).count() == 8
        assert node.channels.filter(module=module_roadm).count() == 2
        assert check_port_sync(node) is True

        # b. corrupt one PortMapping in the ROADM module's group only
        roadm_ch = node.channels.filter(module=module_roadm).order_by("grid_position").first()
        PortMapping.objects.filter(device=device, front_port_id=roadm_ch.mux_front_port_id).update(
            rear_port_position=999
        )
        assert check_port_sync(node) is False

        diff = compute_sync_diff(node)
        # exactly the one corrupted mapping: the fixed cassette's group is untouched
        assert diff["changes"]["port_mappings"]["delete"] == 1
        assert diff["changes"]["port_mappings"]["create"] == 1

        # c. apply_sync repairs the ROADM group via Phase 2 only (no ports are missing,
        # so Phase 1 structural repair is a no-op) and the node is back in sync
        result = apply_sync(node)
        assert result["changes"]["port_mappings"]["delete"] == 1
        assert result["changes"]["port_mappings"]["create"] == 1
        assert result["changes"]["rear_ports"]["create"] == []
        assert result["changes"]["front_ports"]["create"] == []
        assert check_port_sync(node) is True

    def test_apply_mapping_scoped_to_channel_module_and_role(self, mixed_chassis):
        """_apply_mapping's create/delete loops must scope to the changed channel's
        own module's line ports, AND further scope by TX/RX role: a MUX front port
        only fans out to that group's TX/BIDI line ports, a DEMUX front port only to
        RX/BIDI. Before the fix, both loops iterated every line port in the module
        group regardless of role, so remapping a ROADM channel's front port also
        wrote garbage PortMappings against the fixed cassette's COM rear ports, and
        (once a group has more than one line port, as any real ROADM does with
        east/west TX+RX) collided with PortMapping's (front_port, front_port_position)
        uniqueness.

        Uses the mixed_chassis fixture's realistic 4-line-port ROADM group (east/west
        TX+RX) unmodified, instead of narrowing it down to a single line port.
        """
        from dcim.models import FrontPort, PortMapping

        from netbox_wdm.api.views import _apply_mapping

        node, module_fixed, module_roadm = mixed_chassis
        fixed_rear_port_ids = set(node.line_ports.filter(module=module_fixed).values_list("rear_port_id", flat=True))
        roadm_tx_rear_port_ids = set(
            node.line_ports.filter(module=module_roadm, role=WdmLineRoleChoices.TX).values_list(
                "rear_port_id", flat=True
            )
        )
        roadm_rx_rear_port_ids = set(
            node.line_ports.filter(module=module_roadm, role=WdmLineRoleChoices.RX).values_list(
                "rear_port_id", flat=True
            )
        )
        assert fixed_rear_port_ids
        assert roadm_tx_rear_port_ids == {
            lp.rear_port_id
            for lp in node.line_ports.filter(
                module=module_roadm, direction__in=(WdmLineDirectionChoices.EAST, WdmLineDirectionChoices.WEST)
            )
            if lp.role == WdmLineRoleChoices.TX
        }
        assert len(roadm_tx_rear_port_ids) == 2  # east + west
        assert len(roadm_rx_rear_port_ids) == 2  # east + west

        roadm_ch = node.channels.filter(module=module_roadm).order_by("grid_position").first()
        spare_mux_fp = FrontPort.objects.create(
            device=node.device, module=module_roadm, name="ROADM1 ADD-SPARE", type="lc-upc"
        )
        spare_demux_fp = FrontPort.objects.create(
            device=node.device, module=module_roadm, name="ROADM1 DROP-SPARE", type="lc-upc"
        )

        _apply_mapping(node, {roadm_ch.pk: {"mux": spare_mux_fp.pk, "demux": spare_demux_fp.pk}})

        mux_mappings = PortMapping.objects.filter(front_port=spare_mux_fp)
        demux_mappings = PortMapping.objects.filter(front_port=spare_demux_fp)

        # mux fanned out to exactly the ROADM module's TX rear ports, nothing else
        assert set(mux_mappings.values_list("rear_port_id", flat=True)) == roadm_tx_rear_port_ids
        # demux fanned out to exactly the ROADM module's RX rear ports, nothing else
        assert set(demux_mappings.values_list("rear_port_id", flat=True)) == roadm_rx_rear_port_ids
        # nothing crossed roles or modules
        assert not mux_mappings.filter(rear_port_id__in=roadm_rx_rear_port_ids | fixed_rear_port_ids).exists()
        assert not demux_mappings.filter(rear_port_id__in=roadm_tx_rear_port_ids | fixed_rear_port_ids).exists()


class TestStructuralRepair:
    def test_apply_sync_recreates_deleted_module_port_with_mapping(self, wdm_site, wdm_manufacturer, wdm_roles):
        from dcim.models import FrontPort, PortMapping

        from netbox_wdm.port_sync import apply_sync
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-FIX", mt, bays=("MUX1",))
        victim = FrontPort.objects.get(module=bundle.modules["MUX1"], name="MUX1 CH1-MUX")
        victim.delete()

        apply_sync(bundle.node)

        recreated = FrontPort.objects.get(module=bundle.modules["MUX1"], name="MUX1 CH1-MUX")
        assert PortMapping.objects.filter(front_port=recreated).exists()

    def test_apply_sync_recreates_deleted_line_port_from_plan(self, wdm_site, wdm_manufacturer, wdm_roles):
        from netbox_wdm.port_sync import apply_sync
        from netbox_wdm.testing import create_cwdm_cassette_module_type, create_modular_chassis

        mt = create_cwdm_cassette_module_type(wdm_manufacturer)
        bundle = create_modular_chassis(wdm_site, wdm_roles["wdm-mux"], "CHASSIS-LP", mt, bays=("MUX1",))
        bundle.node.line_ports.filter(role="tx").delete()

        apply_sync(bundle.node)

        assert bundle.node.line_ports.filter(module=bundle.modules["MUX1"], role="tx").exists()

    def test_repair_recreates_front_port_with_multiple_rear_port_mappings(self, wdm_site, wdm_manufacturer, wdm_roles):
        """A single FrontPortTemplate may be wired to more than one RearPortTemplate (e.g.
        a splitter tap). _repair_missing_ports's ptms_by_fpt defaultdict(list) must recreate
        every PortMapping row for the recreated front port, not just the first one found."""
        from dcim.models import FrontPort, PortMapping

        from netbox_wdm.port_sync import _repair_missing_ports

        dt = DeviceType.objects.create(manufacturer=wdm_manufacturer, model="DT-SPLIT", slug="dt-split")
        fpt = FrontPortTemplate.objects.create(device_type=dt, name="SPLIT-IN", type="lc-upc")
        rpt_a = RearPortTemplate.objects.create(device_type=dt, name="OUT-A", type="lc", positions=1)
        rpt_b = RearPortTemplate.objects.create(device_type=dt, name="OUT-B", type="lc", positions=1)
        PortTemplateMapping.objects.create(
            device_type=dt, front_port=fpt, rear_port=rpt_a, front_port_position=1, rear_port_position=1
        )
        PortTemplateMapping.objects.create(
            device_type=dt, front_port=fpt, rear_port=rpt_b, front_port_position=2, rear_port_position=1
        )
        device = Device.objects.create(name="SPLIT-DEV", site=wdm_site, device_type=dt, role=wdm_roles["wdm-mux"])

        victim = FrontPort.objects.get(device=device, name="SPLIT-IN")
        PortMapping.objects.filter(front_port=victim).delete()
        victim.delete()

        _repair_missing_ports(device)

        recreated = FrontPort.objects.get(device=device, name="SPLIT-IN")
        mappings = PortMapping.objects.filter(front_port=recreated)
        assert mappings.count() == 2
        assert set(mappings.values_list("rear_port__name", flat=True)) == {"OUT-A", "OUT-B"}
