from __future__ import annotations

import django_filters
from dcim.models import Device, DeviceType, Module, ModuleType
from django.db import models
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant

from .choices import (
    WdmChannelStatusChoices,
    WdmCircuitStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
)
from .models import (
    WdmChannel,
    WdmChannelPlan,
    WdmCircuit,
    WdmLinePort,
    WdmLinePortPlan,
    WdmNode,
    WdmProfile,
    WdmWavelengthPath,
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


class WdmProfileFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    node_type = django_filters.MultipleChoiceFilter(choices=WdmNodeTypeChoices)
    grid = django_filters.MultipleChoiceFilter(choices=WdmGridChoices)
    device_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=DeviceType.objects.all(), field_name="device_type", label=_("Device Type (ID)")
    )
    module_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ModuleType.objects.all(), field_name="module_type", label=_("Module Type (ID)")
    )
    search_fields = ("device_type__model__icontains",)

    class Meta:
        model = WdmProfile
        fields = ("id", "node_type", "grid")


class WdmChannelPlanFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    profile_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmProfile.objects.all(), field_name="profile", label=_("Profile (ID)")
    )
    search_fields = ("label__icontains",)

    class Meta:
        model = WdmChannelPlan
        fields = ("id", "profile", "grid_position", "wavelength_nm", "label")


class WdmLinePortPlanFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    profile_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmProfile.objects.all(), field_name="profile", label=_("Profile (ID)")
    )
    search_fields = ("direction__icontains",)

    class Meta:
        model = WdmLinePortPlan
        fields = ("id", "profile", "direction", "role")


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


class WdmLinePortFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    module_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Module.objects.all(), field_name="module", label=_("Module (ID)")
    )
    search_fields = ("direction__icontains",)

    class Meta:
        model = WdmLinePort
        fields = ("id", "wdm_node", "direction", "role")


class WdmChannelFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    module_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Module.objects.all(), field_name="module", label=_("Module (ID)")
    )
    status = django_filters.MultipleChoiceFilter(choices=WdmChannelStatusChoices)
    search_fields = ("grid_position",)

    class Meta:
        model = WdmChannel
        fields = ("id", "wdm_node", "status", "grid_position")


class WdmWavelengthPathFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    is_complete = django_filters.BooleanFilter()
    is_active = django_filters.BooleanFilter()
    is_valid = django_filters.BooleanFilter()
    search_fields = ("wavelength_nm",)

    class Meta:
        model = WdmWavelengthPath
        fields = ("id", "grid_position", "wavelength_nm", "is_complete", "is_active", "is_valid")


class WdmCircuitFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    status = django_filters.MultipleChoiceFilter(choices=WdmCircuitStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(), field_name="tenant", label=_("Tenant (ID)")
    )
    search_fields = ("name__icontains", "description__icontains")

    class Meta:
        model = WdmCircuit
        fields = ("id", "name", "status")
