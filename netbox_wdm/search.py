from netbox.search import SearchIndex, register_search

from .models import WavelengthChannel, WavelengthService, WdmNode


@register_search
class WdmNodeIndex(SearchIndex):
    model = WdmNode
    fields = (("description", 500),)
    display_attrs = ("device", "node_type", "grid")


@register_search
class WavelengthChannelIndex(SearchIndex):
    model = WavelengthChannel
    fields = (("label", 100),)
    display_attrs = ("wdm_node", "wavelength_nm", "status")


@register_search
class WavelengthServiceIndex(SearchIndex):
    model = WavelengthService
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = ("status", "wavelength_nm", "tenant")
