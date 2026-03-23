import strawberry_django

from ..models import WavelengthChannel, WavelengthService, WdmDeviceTypeProfile, WdmNode


@strawberry_django.filters.filter(WdmDeviceTypeProfile)
class WdmDeviceTypeProfileFilter:
    id: int | None
    node_type: str | None
    grid: str | None


@strawberry_django.filters.filter(WdmNode)
class WdmNodeFilter:
    id: int | None
    node_type: str | None
    grid: str | None
    device_id: int | None


@strawberry_django.filters.filter(WavelengthChannel)
class WavelengthChannelFilter:
    id: int | None
    wdm_node_id: int | None
    status: str | None
    grid_position: int | None


@strawberry_django.filters.filter(WavelengthService)
class WavelengthServiceFilter:
    id: int | None
    name: str | None
    status: str | None
