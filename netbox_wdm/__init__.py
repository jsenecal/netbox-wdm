from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class NetBoxWDMConfig(PluginConfig):
    name = "netbox_wdm"
    verbose_name = "WDM Wavelength Management"
    description = "WDM wavelength management for NetBox"
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
