from typing import Annotated

import strawberry
import strawberry_django
from netbox.graphql.types import NetBoxObjectType

from ..models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


@strawberry_django.type(WdmDeviceTypeProfile, fields="__all__")
class WdmDeviceTypeProfileType(NetBoxObjectType):
    channel_templates: list[Annotated["WdmChannelTemplateType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmChannelTemplate, fields="__all__")
class WdmChannelTemplateType(NetBoxObjectType):
    pass


@strawberry_django.type(WdmNode, fields="__all__")
class WdmNodeInstanceType(NetBoxObjectType):
    trunk_ports: list[Annotated["WdmTrunkPortType", strawberry.lazy(".types")]]
    channels: list[Annotated["WavelengthChannelType", strawberry.lazy(".types")]]


@strawberry_django.type(WdmTrunkPort, fields="__all__")
class WdmTrunkPortType(NetBoxObjectType):
    pass


@strawberry_django.type(WavelengthChannel, fields="__all__")
class WavelengthChannelType(NetBoxObjectType):
    pass


@strawberry_django.type(WavelengthService, fields="__all__")
class WavelengthServiceType(NetBoxObjectType):
    pass
