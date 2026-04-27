# NetBox WDM

Wavelength Division Multiplexing (WDM) device management for NetBox: ITU channel plans, channel-to-port assignments, ROADM live editing, wavelength service tracking, and interactive circuit trace visualization.

## Overlay pattern

netbox-wdm follows NetBox's Device/DeviceType pattern with overlay models:

- **WdmDeviceTypeProfile** → 1:1 on `dcim.DeviceType` (the blueprint).
- **WdmNode** → 1:1 on `dcim.Device` (the instance).
- **WdmChannelTemplate** → channel-to-port blueprint on a profile.
- **WdmChannel** → one per ITU channel, links MUX/DEMUX front ports.
- **WdmWavelengthPath** → end-to-end traced path between WDM nodes.
- **WdmCircuit** → logical service grouping one or more wavelength paths.

## Quick links

- [User: Port Sync](user/port-sync.md)
- [Developer: Architecture & Port Sync](developer/port-sync.md)
- [Developer: Style Guide](developer/style-guide.md)
- [GitHub repository](https://github.com/jsenecal/netbox-wdm)
- [Issue tracker](https://github.com/jsenecal/netbox-wdm/issues)
