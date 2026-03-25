import strawberry_django

from ..models import WdmChannel, WdmCircuit, WdmNode, WdmProfile


@strawberry_django.filters.filter_type(WdmProfile)
class WdmProfileFilter:
    id: int | None
    node_type: str | None
    grid: str | None


@strawberry_django.filters.filter_type(WdmNode)
class WdmNodeFilter:
    id: int | None
    node_type: str | None
    grid: str | None
    device_id: int | None


@strawberry_django.filters.filter_type(WdmChannel)
class WdmChannelFilter:
    id: int | None
    wdm_node_id: int | None
    status: str | None
    grid_position: int | None


@strawberry_django.filters.filter_type(WdmCircuit)
class WdmCircuitFilter:
    id: int | None
    name: str | None
    status: str | None
