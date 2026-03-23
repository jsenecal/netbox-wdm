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
