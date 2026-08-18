# Modular Chassis

Some WDM hardware is not a fixed-function box: it is a bare chassis with
module bays that take swappable cassettes. A 1RU shelf might hold two
independent CWDM MUX/DEMUX cassettes, each wired to its own pair of trunk
fibres, sharing nothing but rack space and a device shell. netbox-wdm
models this with a WDM profile on the **ModuleType** rather than (or in
addition to) the DeviceType, so each installed module gets its own
channels and line ports.

## Profile on ModuleType

`WdmProfile` has two mutually-optional one-to-one fields:
`device_type` and `module_type`. Everything described in
[WDM Profiles](wdm-profiles.md) and [DeviceType Setup](device-types.md) --
`node_type`, `grid`, `fiber_type`, channel plans, line port plans -- works
identically whether the profile hangs off a DeviceType or a ModuleType.
The only difference is *when* it gets used:

- A **DeviceType** profile populates channels and line ports once, when a
  Device of that type is created.
- A **ModuleType** profile populates channels and line ports once per
  **Module**, when that module is installed into a device.

A chassis DeviceType with module bays typically carries no WDM profile of
its own -- it is just a mechanical shell. The bays are what turn it into a
WDM node, one cassette at a time.

FrontPortTemplate and RearPortTemplate names on a module-scoped ModuleType
use NetBox's `{module}` placeholder (for example, `{module} COM-TX`), the
same convention NetBox uses for any module port template. NetBox expands
the placeholder against the module's bay when the real ports are created;
the plugin resolves the same substitution when it matches a channel plan
or line port plan back to the module's real FrontPorts and RearPorts.

## Per-module scoping

`WdmChannel.module` and `WdmLinePort.module` are nullable foreign keys to
`dcim.Module`. `null` means "this row belongs to the device-level profile,
not to any particular module" -- the same shape channels and line ports
have always had for a non-modular WDM device. A populated `module` scopes
the row to exactly one installed cassette.

This matters most on a chassis with two or more cassettes of the same
ModuleType: without module scoping there would be no way to tell CH1 on
bay MUX1 apart from CH1 on bay MUX2, since both channel plans resolve to
`grid_position = 1`. With module scoping, the two are entirely separate
`WdmChannel` rows pointing at different FrontPorts, and the wavelength
editor, live trace, and port-sync repair all key off `(node, module)`
rather than `(node,)` alone. Tables and forms show a **Module** column
next to the channel/line-port fields for exactly this reason -- the
channel list for a modular node is effectively a grid of per-module rows.

## Install and remove lifecycle

Channels and line ports for a module are **not** something you create by
hand. They follow the module's own lifecycle:

- **Install.** When a `Module` is created (assigned to a bay), and its
  `ModuleType` carries a WDM profile, the plugin creates one `WdmChannel`
  per channel plan and one `WdmLinePort` per line port plan on that
  module, using the same auto-population logic a DeviceType profile uses
  for device-level ports. This runs after the transaction that created
  the module commits, so the module's real FrontPorts and RearPorts
  already exist to link against.
- **Remove.** Deleting a `Module` cascades away its `WdmChannel` and
  `WdmLinePort` rows (and, through those, any `WdmWavelengthPathChannel`
  entries referencing them) via plain foreign-key `CASCADE` -- wavelength
  paths are derived data, not source of truth, so nothing needs to
  protect against the delete. Any wavelength path left with fewer than
  two channel entries after the cascade is meaningless and is pruned;
  every node that had a path through the removed module (including the
  far end of the link) is automatically retraced and rechecked for port
  sync once the deletion commits.
- **Swap.** Swapping a cassette is a remove followed by an install: the
  old module's channels and line ports disappear, the new module's are
  created fresh, and both sides of any wavelength path through that bay
  are retraced.

None of this requires the WDM Profile tab, the wavelength editor, or any
manual line-port creation step -- it happens purely from NetBox's own
Module create/delete signals.

## Line port plans

A `WdmLinePortPlan` is the module-scoped equivalent of manually creating
`WdmLinePort` rows (see [Creating line ports](device-types.md#creating-line-ports)
for the DeviceType-level manual process). It lives on the profile, points
at a `RearPortTemplate`, and carries the `direction` and `role` that
should apply wherever that template resolves to a real RearPort:

| Field | Notes |
|-------|-------|
| `profile` | Parent WDM profile (device-type or module-type scoped) |
| `rear_port_template` | FK to a `dcim.RearPortTemplate` on the same DeviceType/ModuleType |
| `direction` | `common`, `east`, or `west` |
| `role` | `tx`, `rx`, or `bidi` |

Because line port plans live on the profile, they are created once per
hardware type and then apply to every device or module built from that
type -- there is no per-instance line-port setup step for modular
chassis, unlike the manual process for a plain DeviceType profile.

## Worked example

The bundled `create_wdm_sample_data` management command builds a modular
topology (`modular_chassis_span`) alongside its other sample topologies:
a 2-cassette hub chassis (bays `MUX1` and `MUX2`) connects through two
patch panel pairs to two single-cassette peer chassis. Each of the three
chassis devices shares one `WdmProfile`-carrying `ModuleType`
(`CWDM-CASSETTE-8-DX`), and each installed cassette gets its own
independent set of channels and line ports scoped to that module.

```python
from netbox_wdm.testing import (
    create_cwdm_cassette_module_type,
    create_fiber_pp_type,
    create_manufacturer,
    create_modular_chassis,
    create_site,
    create_device_roles,
)

mfr = create_manufacturer("Acme Photonics")
site = create_site("Demo-Site")
roles = create_device_roles()
mt_cassette = create_cwdm_cassette_module_type(mfr)

chassis = create_modular_chassis(
    site, roles["wdm-mux"], "CHASSIS-1", mt_cassette, bays=("MUX1", "MUX2")
)
# chassis.modules["MUX1"], chassis.modules["MUX2"]: installed Module instances
# chassis.node.channels.filter(module=chassis.modules["MUX1"]): that bay's channels
```

`create_modular_chassis` creates the bare chassis Device, installs one
cassette per requested bay, and creates the WdmNode -- the module-install
signal (or, in test/fixture code where signals do not run inside an
atomic block, an explicit repair call) populates each module's channels
and line ports from there. See `netbox_wdm/testing/devices.py` and
`netbox_wdm/testing/topologies.py` for the full builder and topology
source.
