from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

menu = PluginMenu(
    label="WDM",
    groups=(
        (
            "WDM",
            (
                PluginMenuItem(
                    link="plugins:netbox_wdm:wdmprofile_list",
                    link_text="WDM Profiles",
                    permissions=["netbox_wdm.view_wdmprofile"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_wdm:wdmprofile_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_wdm.add_wdmprofile"],
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
                    link="plugins:netbox_wdm:wdmchannel_list",
                    link_text="WDM Channels",
                    permissions=["netbox_wdm.view_wdmchannel"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_wdm:wdmcircuit_list",
                    link_text="WDM Circuits",
                    permissions=["netbox_wdm.view_wdmcircuit"],
                    buttons=(
                        PluginMenuButton(
                            link="plugins:netbox_wdm:wdmcircuit_add",
                            title="Add",
                            icon_class="mdi mdi-plus-thick",
                            permissions=["netbox_wdm.add_wdmcircuit"],
                        ),
                    ),
                ),
            ),
        ),
    ),
    icon_class="mdi mdi-sine-wave",
)
