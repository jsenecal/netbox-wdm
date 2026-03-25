import strawberry
import strawberry_django

from .types import (
    WdmChannelPlanType,
    WdmChannelType,
    WdmCircuitType,
    WdmLinePortType,
    WdmNodeInstanceType,
    WdmProfileType,
)


@strawberry.type
class WdmQuery:
    wdm_profile: WdmProfileType = strawberry_django.field()
    wdm_profile_list: list[WdmProfileType] = strawberry_django.field()

    wdm_channel_plan: WdmChannelPlanType = strawberry_django.field()
    wdm_channel_plan_list: list[WdmChannelPlanType] = strawberry_django.field()

    wdm_node: WdmNodeInstanceType = strawberry_django.field()
    wdm_node_list: list[WdmNodeInstanceType] = strawberry_django.field()

    wdm_line_port: WdmLinePortType = strawberry_django.field()
    wdm_line_port_list: list[WdmLinePortType] = strawberry_django.field()

    wdm_channel: WdmChannelType = strawberry_django.field()
    wdm_channel_list: list[WdmChannelType] = strawberry_django.field()

    wdm_circuit: WdmCircuitType = strawberry_django.field()
    wdm_circuit_list: list[WdmCircuitType] = strawberry_django.field()


schema = [WdmQuery]
