from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from netbox.plugins import PluginTemplateExtension

from .models import WdmNode, WdmWavelengthPathChannel


class DeviceWdmNodePanel(PluginTemplateExtension):
    models = ["dcim.device"]

    def right_page(self) -> str:
        device = self.context["object"]
        wdm_node = WdmNode.objects.filter(device=device).first()
        if wdm_node:
            return self.render(
                "netbox_wdm/inc/device_wdm_panel.html",
                extra_context={"wdm_node": wdm_node},
            )
        return ""


class CableWdmCircuitsPanel(PluginTemplateExtension):
    """Show WDM circuits traversing a cable.

    Finds all FrontPorts and RearPorts terminated by this cable, looks up
    which WdmChannels use those ports (mux or demux), then returns
    the distinct circuits assigned to those channels.
    """

    models = ["dcim.cable"]

    def right_page(self) -> str:
        from dcim.models import CableTermination, FrontPort, RearPort

        cable = self.context["object"]

        # Get all port IDs terminated by this cable
        terminations = CableTermination.objects.filter(cable=cable)

        fp_ct = ContentType.objects.get_for_model(FrontPort)
        rp_ct = ContentType.objects.get_for_model(RearPort)

        fp_ids = set(terminations.filter(termination_type=fp_ct).values_list("termination_id", flat=True))
        rp_ids = set(terminations.filter(termination_type=rp_ct).values_list("termination_id", flat=True))

        if not fp_ids and not rp_ids:
            return ""

        # Find channels whose mux/demux front ports are terminated by this cable
        from django.db.models import Q

        from .models import WdmChannel

        channel_q = Q()
        if fp_ids:
            channel_q |= Q(mux_front_port_id__in=fp_ids) | Q(demux_front_port_id__in=fp_ids)

        # Also find channels on WDM nodes whose line port rear ports are terminated
        if rp_ids:
            from .models import WdmLinePort

            line_port_node_ids = WdmLinePort.objects.filter(rear_port_id__in=rp_ids).values_list(
                "wdm_node_id", flat=True
            )
            if line_port_node_ids:
                channel_q |= Q(wdm_node_id__in=line_port_node_ids)

        if not channel_q:
            return ""

        channel_ids = WdmChannel.objects.filter(channel_q).values_list("pk", flat=True)
        if not channel_ids:
            return ""

        # Find circuits using these channels via wavelength paths
        path_ids = (
            WdmWavelengthPathChannel.objects.filter(channel_id__in=channel_ids)
            .values_list("path_id", flat=True)
            .distinct()
        )

        from .models import WdmCircuit

        circuits = list(WdmCircuit.objects.filter(wavelength_paths__id__in=path_ids).distinct().order_by("name"))
        if not circuits:
            return ""

        return self.render(
            "netbox_wdm/inc/cable_wdm_services_panel.html",
            extra_context={"wdm_services": circuits},
        )


template_extensions = [DeviceWdmNodePanel, CableWdmCircuitsPanel]
