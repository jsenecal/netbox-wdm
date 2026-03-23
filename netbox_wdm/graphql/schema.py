import strawberry
import strawberry_django

from .types import (
    WavelengthChannelType,
    WavelengthServiceType,
    WdmChannelTemplateType,
    WdmDeviceTypeProfileType,
    WdmNodeInstanceType,
    WdmTrunkPortType,
)


@strawberry.type
class WdmQuery:
    wdm_device_type_profile: WdmDeviceTypeProfileType = strawberry_django.field()
    wdm_device_type_profile_list: list[WdmDeviceTypeProfileType] = strawberry_django.field()

    wdm_channel_template: WdmChannelTemplateType = strawberry_django.field()
    wdm_channel_template_list: list[WdmChannelTemplateType] = strawberry_django.field()

    wdm_node: WdmNodeInstanceType = strawberry_django.field()
    wdm_node_list: list[WdmNodeInstanceType] = strawberry_django.field()

    wdm_trunk_port: WdmTrunkPortType = strawberry_django.field()
    wdm_trunk_port_list: list[WdmTrunkPortType] = strawberry_django.field()

    wavelength_channel: WavelengthChannelType = strawberry_django.field()
    wavelength_channel_list: list[WavelengthChannelType] = strawberry_django.field()

    wavelength_service: WavelengthServiceType = strawberry_django.field()
    wavelength_service_list: list[WavelengthServiceType] = strawberry_django.field()


schema = [WdmQuery]
