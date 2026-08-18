from typing import Annotated

import strawberry
import strawberry_django
from netbox.graphql.types import NetBoxObjectType

from ..models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmLinePortPlan,
    WdmNode,
    WdmProfile,
)
from .filters import WdmChannelFilter, WdmLinePortPlanFilter


@strawberry_django.type(WdmProfile, fields="__all__")
class WdmProfileType(NetBoxObjectType):
    channel_plans: list[Annotated["WdmChannelPlanType", strawberry.lazy(".types")]]
    line_port_plans: list[Annotated["WdmLinePortPlanType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmChannelPlan, fields="__all__")
class WdmChannelPlanType(NetBoxObjectType):
    pass


@strawberry_django.type(WdmNode, fields="__all__")
class WdmNodeInstanceType(NetBoxObjectType):
    line_ports: list[Annotated["WdmLinePortType", strawberry.lazy(".types")]]
    channels: list[Annotated["WdmChannelType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmLinePort, fields="__all__")
class WdmLinePortType(NetBoxObjectType):
    pass


@strawberry_django.type(WdmLinePortPlan, fields="__all__", filters=WdmLinePortPlanFilter)
class WdmLinePortPlanType(NetBoxObjectType):
    pass


@strawberry_django.type(WdmChannel, fields="__all__", filters=WdmChannelFilter)
class WdmChannelType(NetBoxObjectType):
    pass


@strawberry_django.type(WdmCircuit, fields="__all__")
class WdmCircuitType(NetBoxObjectType):
    pass
