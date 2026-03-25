from django.contrib.contenttypes.models import ContentType
from netbox.plugins import PluginTemplateExtension

from .models import WavelengthServiceChannelAssignment, WdmNode


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


class CableWdmServicesPanel(PluginTemplateExtension):
    """Show wavelength services traversing a cable.

    Finds all FrontPorts and RearPorts terminated by this cable, looks up
    which WavelengthChannels use those ports (mux or demux), then returns
    the distinct services assigned to those channels.
    """

    models = ["dcim.cable"]

    def right_page(self):
        from dcim.models import CableTermination, FrontPort, RearPort

        cable = self.context["object"]

        # Get all port IDs terminated by this cable
        terminations = CableTermination.objects.filter(cable=cable)

        fp_ct = ContentType.objects.get_for_model(FrontPort)
        rp_ct = ContentType.objects.get_for_model(RearPort)

        fp_ids = set(
            terminations.filter(termination_type=fp_ct).values_list("termination_id", flat=True)
        )
        rp_ids = set(
            terminations.filter(termination_type=rp_ct).values_list("termination_id", flat=True)
        )

        if not fp_ids and not rp_ids:
            return ""

        # Find channels whose mux/demux front ports are terminated by this cable
        from django.db.models import Q

        from .models import WavelengthChannel

        channel_q = Q()
        if fp_ids:
            channel_q |= Q(mux_front_port_id__in=fp_ids) | Q(demux_front_port_id__in=fp_ids)

        # Also find channels on WDM nodes whose line port rear ports are terminated
        if rp_ids:
            from .models import WdmLinePort

            line_port_node_ids = WdmLinePort.objects.filter(
                rear_port_id__in=rp_ids
            ).values_list("wdm_node_id", flat=True)
            if line_port_node_ids:
                channel_q |= Q(wdm_node_id__in=line_port_node_ids)

        if not channel_q:
            return ""

        channel_ids = WavelengthChannel.objects.filter(channel_q).values_list("pk", flat=True)
        if not channel_ids:
            return ""

        # Find services using these channels
        service_ids = (
            WavelengthServiceChannelAssignment.objects.filter(channel_id__in=channel_ids)
            .values_list("service_id", flat=True)
            .distinct()
        )

        from .models import WavelengthService

        services = list(WavelengthService.objects.filter(pk__in=service_ids).order_by("name"))
        if not services:
            return ""

        return self.render(
            "netbox_wdm/inc/cable_wdm_services_panel.html",
            extra_context={"wdm_services": services},
        )


template_extensions = [DeviceWdmNodePanel, CableWdmServicesPanel]
