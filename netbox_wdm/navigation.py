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
