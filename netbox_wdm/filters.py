import django_filters
from dcim.models import Device
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
    WdmNode,
    WdmProfile,
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
    search_fields = ("direction__icontains",)

    class Meta:
        model = WdmLinePort
        fields = ("id", "wdm_node", "direction", "role")


class WdmChannelFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    wdm_node_id = django_filters.ModelMultipleChoiceFilter(
        queryset=WdmNode.objects.all(), field_name="wdm_node", label=_("WDM Node (ID)")
    )
    status = django_filters.MultipleChoiceFilter(choices=WdmChannelStatusChoices)
    search_fields = ("label__icontains",)

    class Meta:
        model = WdmChannel
        fields = ("id", "wdm_node", "status", "grid_position", "wavelength_nm")


class WdmCircuitFilterSet(SearchFieldsMixin, NetBoxModelFilterSet):
    status = django_filters.MultipleChoiceFilter(choices=WdmCircuitStatusChoices)
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(), field_name="tenant", label=_("Tenant (ID)")
    )
    search_fields = ("name__icontains", "description__icontains")

    class Meta:
        model = WdmCircuit
        fields = ("id", "name", "status", "wavelength_nm")
