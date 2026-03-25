from netbox.search import SearchIndex, register_search

from .models import WdmChannel, WdmCircuit, WdmNode


@register_search
class WdmNodeIndex(SearchIndex):
    model = WdmNode
    fields = (("description", 500),)
    display_attrs = ("device", "node_type", "grid")


@register_search
class WdmChannelIndex(SearchIndex):
    model = WdmChannel
    fields = (("label", 100),)
    display_attrs = ("wdm_node", "wavelength_nm", "status")


@register_search
class WdmCircuitIndex(SearchIndex):
    model = WdmCircuit
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("status", "wavelength_nm", "tenant")
