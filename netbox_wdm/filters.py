import django_filters
from dcim.models import Device
from django.db import models
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant

from .choices import (
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .models import (
    WavelengthChannel,
    WavelengthService,
    WdmChannelTemplate,
    WdmDeviceTypeProfile,
    WdmNode,
    WdmTrunkPort,
)


class SearchFieldsMixin:
    """Mixin providing declarative search_fields for FilterSets."""

    search_fields: tuple[str, ...] = ()

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        q = models.Q()
        for field in self.search_fields:
            q |= models.Q(**{field: value})
        return queryset.filter(q)


class WdmDeviceTypeProfileFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)
    search_fields = ("device_type__model__icontains",)

    class Meta:
        model = WdmDeviceTypeProfile
        fields = ("id", "node_type", "grid")


class WdmChannelTemplateFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    profile_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmDeviceTypeProfile.objects.all(), field_name="profile", label=_("Profile (ID)")
    )
    search_fields = ("label__icontains",)

    class Meta:
        model = WdmChannelTemplate
        fields = ("id", "profile", "grid_position", "wavelength_nm", "label")


class WdmNodeFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)
    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(), field_name="device", label=_("Device (ID)")
    )
    search_fields = ("device__name__icontains",)

    class Meta:
        model = WdmNode
        fields = ("id", "node_type", "grid")


class WdmTrunkPortFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    search_fields = ("direction__icontains",)

    class Meta:
        model = WdmTrunkPort
        fields = ("id", "wdm_node", "direction", "position")


class WavelengthChannelFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    status = django_filters.MultipleChoiceFilter(choices=WavelengthChannelStatusChoices)
    search_fields = ("label__icontains",)

    class Meta:
        model = WavelengthChannel
        fields = ("id", "wdm_node", "status", "grid_position", "wavelength_nm")


class WavelengthServiceFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    status = django_filters.MultipleChoiceFilter(choices=WavelengthServiceStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(), field_name="tenant", label=_("Tenant (ID)")
    )
    search_fields = ("name__icontains", "description__icontains")

    class Meta:
        model = WavelengthService
        fields = ("id", "name", "status", "wavelength_nm")
