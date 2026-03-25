from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from .choices import (
    WavelengthChannelStatusChoices,
    WavelengthServiceStatusChoices,
    WdmGridChoices,
    WdmNodeTypeChoices,
    WdmTrunkDirectionChoices,
)


class WdmDeviceTypeProfile(NetBoxModel):
    """WDM capability profile attached to a DeviceType."""

    device_type = models.OneToOneField(
        to="dcim.DeviceType",
        on_delete=models.CASCADE,
        related_name="wdm_profile",
        verbose_name=_("device type"),
    )
    node_type = models.CharField(
        max_length=50,
        choices=WdmNodeTypeChoices,
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    clone_fields = ("node_type", "grid")

    class Meta:
        ordering = ("device_type",)
        verbose_name = _("WDM device type profile")
        verbose_name_plural = _("WDM device type profiles")

    def __str__(self):
        return f"WDM Profile: {self.device_type}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmdevicetypeprofile", args=[self.pk])


class WdmChannelTemplate(NetBoxModel):
    """Channel slot template on a WdmDeviceTypeProfile."""

    profile = models.ForeignKey(
        to="netbox_wdm.WdmDeviceTypeProfile",
        on_delete=models.CASCADE,
        related_name="channel_templates",
        verbose_name=_("profile"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    front_port_template = models.ForeignKey(
        to="dcim.FrontPortTemplate",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("front port template"),
    )

    class Meta:
        ordering = ("profile", "grid_position")
        verbose_name = _("WDM channel template")
        verbose_name_plural = _("WDM channel templates")
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "wavelength_nm"],
                name="unique_profile_wavelength",
            ),
            models.UniqueConstraint(
                fields=["profile", "grid_position"],
                name="unique_profile_grid_position",
            ),
            models.UniqueConstraint(
                fields=["profile", "front_port_template"],
                condition=models.Q(front_port_template__isnull=False),
                name="unique_profile_fpt",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmchanneltemplate", args=[self.pk])


class WdmNode(NetBoxModel):
    """WDM node instance attached to a Device."""

    device = models.OneToOneField(
        to="dcim.Device",
        on_delete=models.CASCADE,
        related_name="wdm_node",
        verbose_name=_("device"),
    )
    node_type = models.CharField(
        max_length=50,
        choices=WdmNodeTypeChoices,
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    clone_fields = ("node_type", "grid")

    class Meta:
        ordering = ("device",)
        verbose_name = _("WDM node")
        verbose_name_plural = _("WDM nodes")

    def __str__(self):
        return f"WDM: {self.device.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmnode", args=[self.pk])

    def validate_channel_mapping(self, desired_mapping: dict[int, int | None]) -> list[str]:
        """Validate proposed channel-to-port mapping changes.

        Returns list of error strings. Empty list means validation passed.
        """
        errors = []
        channels = {ch.pk: ch for ch in self.channels.all()}

        protected_statuses = {WavelengthChannelStatusChoices.LIT, WavelengthChannelStatusChoices.RESERVED}
        for ch_pk, desired_fp_pk in desired_mapping.items():
            ch = channels.get(ch_pk)
            if ch is None:
                continue
            if ch.status in protected_statuses and ch.front_port_id != desired_fp_pk:
                errors.append(f"Channel {ch.label} (pk={ch.pk}) is {ch.get_status_display()} and cannot be remapped.")

        port_usage = {}
        for ch_pk, desired_fp_pk in desired_mapping.items():
            if desired_fp_pk is None:
                continue
            ch = channels.get(ch_pk)
            label = ch.label if ch else f"pk={ch_pk}"
            if desired_fp_pk in port_usage:
                errors.append(
                    f"Port conflict: channels {port_usage[desired_fp_pk]} and {label} "
                    f"both map to FrontPort pk={desired_fp_pk}."
                )
            else:
                port_usage[desired_fp_pk] = label

        return errors

    def save(self, *args, **kwargs):
        """Save and auto-populate channels from device type profile on creation."""
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new and self.node_type != WdmNodeTypeChoices.AMPLIFIER:
                self._auto_populate_channels()

    def _auto_populate_channels(self):
        """Create WavelengthChannel rows from the device type's WDM profile templates."""
        from dcim.models import FrontPort

        try:
            profile = self.device.device_type.wdm_profile
        except WdmDeviceTypeProfile.DoesNotExist:
            return

        templates = list(profile.channel_templates.select_related("front_port_template").all())
        if not templates:
            return

        fp_by_name = {fp.name: fp for fp in FrontPort.objects.filter(device=self.device)}

        channels = []
        for ct in templates:
            front_port = None
            if ct.front_port_template:
                front_port = fp_by_name.get(ct.front_port_template.name)
            channels.append(
                WavelengthChannel(
                    wdm_node=self,
                    grid_position=ct.grid_position,
                    wavelength_nm=ct.wavelength_nm,
                    label=ct.label,
                    front_port=front_port,
                )
            )
        WavelengthChannel.objects.bulk_create(channels)


class WdmTrunkPort(NetBoxModel):
    """Maps a RearPort on a WDM node to a directional trunk."""

    wdm_node = models.ForeignKey(
        to="netbox_wdm.WdmNode",
        on_delete=models.CASCADE,
        related_name="trunk_ports",
        verbose_name=_("WDM node"),
    )
    rear_port = models.ForeignKey(
        to="dcim.RearPort",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("rear port"),
    )
    direction = models.CharField(
        max_length=50,
        choices=WdmTrunkDirectionChoices,
        verbose_name=_("direction"),
    )
    position = models.PositiveIntegerField(verbose_name=_("position"))

    class Meta:
        ordering = ("wdm_node", "position")
        verbose_name = _("WDM trunk port")
        verbose_name_plural = _("WDM trunk ports")
        constraints = [
            models.UniqueConstraint(
                fields=["wdm_node", "rear_port"],
                name="unique_trunkport_rear_port",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "direction"],
                name="unique_trunkport_direction",
            ),
        ]

    def __str__(self):
        return f"{self.direction}: {self.rear_port}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmtrunkport", args=[self.pk])


class WavelengthChannel(NetBoxModel):
    """A wavelength channel instance on a WDM node."""

    wdm_node = models.ForeignKey(
        to="netbox_wdm.WdmNode",
        on_delete=models.CASCADE,
        related_name="channels",
        verbose_name=_("WDM node"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("front port"),
    )
    status = models.CharField(
        max_length=50,
        choices=WavelengthChannelStatusChoices,
        default=WavelengthChannelStatusChoices.AVAILABLE,
        db_index=True,
        verbose_name=_("status"),
    )

    class Meta:
        ordering = ("wdm_node", "grid_position")
        verbose_name = _("wavelength channel")
        verbose_name_plural = _("wavelength channels")
        constraints = [
            models.UniqueConstraint(
                fields=["wdm_node", "wavelength_nm"],
                name="unique_channel_wavelength",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "grid_position"],
                name="unique_channel_grid_position",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "front_port"],
                condition=models.Q(front_port__isnull=False),
                name="unique_node_fp",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wavelengthchannel", args=[self.pk])


class WavelengthService(NetBoxModel):
    """An end-to-end wavelength service spanning WDM channels."""

    name = models.CharField(max_length=200, verbose_name=_("name"))
    status = models.CharField(
        max_length=50,
        choices=WavelengthServiceStatusChoices,
        default=WavelengthServiceStatusChoices.PLANNED,
        db_index=True,
        verbose_name=_("status"),
    )
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="wavelength_services",
        verbose_name=_("tenant"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    comments = models.TextField(blank=True, verbose_name=_("comments"))

    clone_fields = ("status", "wavelength_nm", "tenant")

    class Meta:
        ordering = ("name",)
        verbose_name = _("wavelength service")
        verbose_name_plural = _("wavelength services")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wavelengthservice", args=[self.pk])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status if self.pk else None

    def clean(self):
        """Validate channel consistency: same grid, matching wavelength."""
        super().clean()

        if not self.pk:
            return

        cas = list(self.channel_assignments.select_related("channel__wdm_node"))
        if not cas:
            return

        grids = set()
        svc_wl = Decimal(str(self.wavelength_nm))
        for ca in cas:
            if ca.channel:
                grids.add(ca.channel.wdm_node.grid)

        if len(grids) > 1:
            raise ValidationError(
                _("All WDM nodes in a wavelength service must use the same grid. Found: %(grids)s")
                % {"grids": ", ".join(sorted(grids))}
            )

        for ca in cas:
            if ca.channel:
                ch_wl = Decimal(str(ca.channel.wavelength_nm))
                if abs(ch_wl - svc_wl) > Decimal("0.01"):
                    raise ValidationError(
                        _("Channel %(label)s has wavelength %(ch_wl)s nm but service wavelength is %(svc_wl)s nm.")
                        % {
                            "label": ca.channel.label,
                            "ch_wl": ca.channel.wavelength_nm,
                            "svc_wl": self.wavelength_nm,
                        }
                    )

    def save(self, *args, **kwargs):
        """Save and handle lifecycle transitions."""
        is_new = self._state.adding
        old_status = self._original_status

        super().save(*args, **kwargs)
        self._original_status = self.status

        if not is_new and old_status != self.status:
            if self.status == WavelengthServiceStatusChoices.DECOMMISSIONED:
                self.nodes.all().delete()
                channel_ids = self.channel_assignments.values_list("channel_id", flat=True)
                WavelengthChannel.objects.filter(pk__in=channel_ids).update(
                    status=WavelengthChannelStatusChoices.AVAILABLE
                )
            elif old_status == WavelengthServiceStatusChoices.DECOMMISSIONED:
                self.rebuild_nodes()

    def get_stitched_path(self):
        """Return the stitched end-to-end path as an ordered list of hop dicts."""
        hops = []
        for ca in self.channel_assignments.select_related("channel__wdm_node__device").order_by("sequence"):
            if ca.channel:
                hops.append(
                    {
                        "type": "wdm_node",
                        "node_id": ca.channel.wdm_node_id,
                        "node_name": ca.channel.wdm_node.device.name,
                        "channel_id": ca.channel_id,
                        "channel_label": ca.channel.label,
                        "wavelength_nm": float(ca.channel.wavelength_nm),
                    }
                )
        return hops

    def rebuild_nodes(self):
        """Delete existing service nodes and recreate from channel assignments."""
        self.nodes.all().delete()
        nodes = []
        for ca in self.channel_assignments.all():
            if ca.channel_id:
                nodes.append(WavelengthServiceNode(service=self, channel=ca.channel))
        if nodes:
            WavelengthServiceNode.objects.bulk_create(nodes)


class WavelengthServiceChannelAssignment(models.Model):
    """Through-model linking a WavelengthService to WavelengthChannels in sequence."""

    service = models.ForeignKey(
        to="netbox_wdm.WavelengthService",
        on_delete=models.CASCADE,
        related_name="channel_assignments",
        verbose_name=_("service"),
    )
    channel = models.ForeignKey(
        to="netbox_wdm.WavelengthChannel",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("channel"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("sequence"))

    class Meta:
        ordering = ("service", "sequence")
        verbose_name = _("wavelength service channel assignment")
        verbose_name_plural = _("wavelength service channel assignments")
        constraints = [
            models.UniqueConstraint(
                fields=["service", "channel"],
                name="unique_wsca_service_channel",
            ),
            models.UniqueConstraint(
                fields=["service", "sequence"],
                name="unique_wsca_service_sequence",
            ),
        ]

    def __str__(self):
        return f"{self.service} #{self.sequence}: {self.channel}"


class WavelengthServiceNode(models.Model):
    """PROTECT guard preventing deletion of WavelengthChannels in active services."""

    service = models.ForeignKey(
        to="netbox_wdm.WavelengthService",
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name=_("service"),
    )
    channel = models.ForeignKey(
        to="netbox_wdm.WavelengthChannel",
        on_delete=models.PROTECT,
        verbose_name=_("channel"),
    )

    class Meta:
        verbose_name = _("wavelength service node")
        verbose_name_plural = _("wavelength service nodes")
        constraints = [
            models.UniqueConstraint(
                fields=["service", "channel"],
                name="unique_wsn_channel",
            ),
        ]

    def __str__(self):
        return f"channel: {self.channel}"
