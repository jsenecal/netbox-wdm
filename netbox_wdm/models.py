from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from .choices import (
    WdmChannelStatusChoices,
    WdmCircuitStatusChoices,
    WdmFiberTypeChoices,
    WdmGridChoices,
    WdmLineDirectionChoices,
    WdmLineRoleChoices,
    WdmNodeTypeChoices,
)


class WdmProfile(NetBoxModel):
    """WDM capability profile attached to a DeviceType."""

    prerequisite_models = ("dcim.DeviceType",)

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
    fiber_type = models.CharField(
        max_length=50,
        choices=WdmFiberTypeChoices,
        default=WdmFiberTypeChoices.DUPLEX,
        verbose_name=_("fiber type"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))

    clone_fields = ("node_type", "grid", "fiber_type")

    class Meta:
        ordering = ("device_type",)
        verbose_name = _("WDM profile")
        verbose_name_plural = _("WDM profiles")

    def __str__(self):
        return f"WDM Profile: {self.device_type}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmprofile", args=[self.pk])


class WdmChannelPlan(NetBoxModel):
    """Channel slot template on a WdmProfile."""

    profile = models.ForeignKey(
        to="netbox_wdm.WdmProfile",
        on_delete=models.CASCADE,
        related_name="channel_plans",
        verbose_name=_("profile"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    label = models.CharField(max_length=20, verbose_name=_("label"))
    mux_front_port_template = models.ForeignKey(
        to="dcim.FrontPortTemplate",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("MUX front port template"),
    )
    demux_front_port_template = models.ForeignKey(
        to="dcim.FrontPortTemplate",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("DEMUX front port template"),
    )

    class Meta:
        ordering = ("profile", "grid_position")
        verbose_name = _("WDM channel plan")
        verbose_name_plural = _("WDM channel plans")
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
                fields=["profile", "mux_front_port_template"],
                condition=models.Q(mux_front_port_template__isnull=False),
                name="unique_profile_fpt",
            ),
            models.UniqueConstraint(
                fields=["profile", "demux_front_port_template"],
                condition=models.Q(demux_front_port_template__isnull=False),
                name="unique_profile_demux_fpt",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmchannelplan", args=[self.pk])


class WdmNode(NetBoxModel):
    """WDM node instance attached to a Device."""

    prerequisite_models = ("dcim.Device",)

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

    @property
    def is_fixed(self):
        """Fixed nodes have hardware-determined channel and port assignments.

        Only ROADM nodes allow runtime changes to channels and line ports.
        """
        return self.node_type != WdmNodeTypeChoices.ROADM

    def validate_channel_mapping(self, desired_mapping: dict[int, dict[str, int | None]]) -> list[str]:
        """Validate proposed channel-to-port mapping changes.

        desired_mapping format: { channel_pk: {"mux": port_id|None, "demux": port_id|None} }
        Returns list of error strings. Empty list means validation passed.
        """
        errors = []
        channels = {ch.pk: ch for ch in self.channels.all()}

        protected_statuses = {WdmChannelStatusChoices.ACTIVE, WdmChannelStatusChoices.RESERVED}
        for ch_pk, ports in desired_mapping.items():
            ch = channels.get(ch_pk)
            if ch is None:
                continue
            mux_changed = ch.mux_front_port_id != ports.get("mux")
            demux_changed = ch.demux_front_port_id != ports.get("demux")
            if ch.status in protected_statuses and (mux_changed or demux_changed):
                errors.append(f"Channel {ch.label} (pk={ch.pk}) is {ch.get_status_display()} and cannot be remapped.")

        mux_port_usage: dict[int, str] = {}
        demux_port_usage: dict[int, str] = {}
        for ch_pk, ports in desired_mapping.items():
            ch = channels.get(ch_pk)
            label = ch.label if ch else f"pk={ch_pk}"

            mux_fp_pk = ports.get("mux")
            if mux_fp_pk is not None:
                if mux_fp_pk in mux_port_usage:
                    errors.append(
                        f"Port conflict: channels {mux_port_usage[mux_fp_pk]} and {label} "
                        f"both map to MUX FrontPort pk={mux_fp_pk}."
                    )
                else:
                    mux_port_usage[mux_fp_pk] = label

            demux_fp_pk = ports.get("demux")
            if demux_fp_pk is not None:
                if demux_fp_pk in demux_port_usage:
                    errors.append(
                        f"Port conflict: channels {demux_port_usage[demux_fp_pk]} and {label} "
                        f"both map to DEMUX FrontPort pk={demux_fp_pk}."
                    )
                else:
                    demux_port_usage[demux_fp_pk] = label

        return errors

    def save(self, *args, **kwargs):
        """Save and auto-populate channels from device type profile on creation."""
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new and self.node_type != WdmNodeTypeChoices.AMPLIFIER:
                self._auto_populate_channels()

    def _auto_populate_channels(self):
        """Create WdmChannel rows from the device type's WDM profile channel plans."""
        from dcim.models import FrontPort

        try:
            profile = self.device.device_type.wdm_profile
        except WdmProfile.DoesNotExist:
            return

        plans = list(profile.channel_plans.select_related("mux_front_port_template", "demux_front_port_template").all())
        if not plans:
            return

        fp_by_name = {fp.name: fp for fp in FrontPort.objects.filter(device=self.device)}

        channels = []
        for cp in plans:
            mux_front_port = None
            if cp.mux_front_port_template:
                mux_front_port = fp_by_name.get(cp.mux_front_port_template.name)
            demux_front_port = None
            if cp.demux_front_port_template:
                demux_front_port = fp_by_name.get(cp.demux_front_port_template.name)
            channels.append(
                WdmChannel(
                    wdm_node=self,
                    grid_position=cp.grid_position,
                    wavelength_nm=cp.wavelength_nm,
                    label=cp.label,
                    mux_front_port=mux_front_port,
                    demux_front_port=demux_front_port,
                )
            )
        WdmChannel.objects.bulk_create(channels)


class WdmLinePort(NetBoxModel):
    """Maps a RearPort on a WDM node to a directional line port."""

    wdm_node = models.ForeignKey(
        to="netbox_wdm.WdmNode",
        on_delete=models.CASCADE,
        related_name="line_ports",
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
        choices=WdmLineDirectionChoices,
        verbose_name=_("direction"),
    )
    role = models.CharField(
        max_length=50,
        choices=WdmLineRoleChoices,
        default=WdmLineRoleChoices.BIDI,
        verbose_name=_("role"),
    )

    class Meta:
        ordering = ("wdm_node", "direction", "role")
        verbose_name = _("WDM line port")
        verbose_name_plural = _("WDM line ports")
        constraints = [
            models.UniqueConstraint(
                fields=["wdm_node", "rear_port"],
                name="unique_lineport_rear_port",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "direction", "role"],
                name="unique_lineport_direction_role",
            ),
        ]

    FIXED_FIELDS = ("rear_port", "direction", "role")

    def __str__(self):
        return f"{self.direction}: {self.rear_port}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmlineport", args=[self.pk])

    def _check_fixed_fields(self):
        """Check that fixed fields haven't changed on a fixed node."""
        if not self.pk or not self.wdm_node.is_fixed:
            return
        db_obj = WdmLinePort.objects.get(pk=self.pk)
        for field in self.FIXED_FIELDS:
            attr = f"{field}_id" if field == "rear_port" else field
            if getattr(self, attr) != getattr(db_obj, attr):
                raise ValidationError(_("Cannot modify %(field)s on a fixed WDM node.") % {"field": field})

    def clean(self):
        """On fixed nodes, line port configuration cannot be changed after creation."""
        super().clean()
        self._check_fixed_fields()

    def save(self, *args, **kwargs):
        """Enforce fixed node constraints at save time.

        Allows initial creation (from auto-populate) but blocks modifications
        to fixed fields on existing line ports of fixed nodes.
        """
        self._check_fixed_fields()
        super().save(*args, **kwargs)


class WdmChannel(NetBoxModel):
    """A wavelength channel instance on a WDM node."""

    prerequisite_models = ("netbox_wdm.WdmNode",)

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
    mux_front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("MUX front port"),
    )
    demux_front_port = models.ForeignKey(
        to="dcim.FrontPort",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("DEMUX front port"),
    )
    status = models.CharField(
        max_length=50,
        choices=WdmChannelStatusChoices,
        default=WdmChannelStatusChoices.AVAILABLE,
        db_index=True,
        verbose_name=_("status"),
    )

    class Meta:
        ordering = ("wdm_node", "grid_position")
        verbose_name = _("WDM channel")
        verbose_name_plural = _("WDM channels")
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
                fields=["wdm_node", "mux_front_port"],
                condition=models.Q(mux_front_port__isnull=False),
                name="unique_node_mux_fp",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "demux_front_port"],
                condition=models.Q(demux_front_port__isnull=False),
                name="unique_node_demux_fp",
            ),
        ]

    FIXED_FIELDS = ("mux_front_port", "demux_front_port", "grid_position", "wavelength_nm", "label")

    def __str__(self):
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmchannel", args=[self.pk])

    def _check_fixed_fields(self):
        """Check that fixed fields haven't changed on a fixed node."""
        if not self.pk or not self.wdm_node.is_fixed:
            return
        db_obj = WdmChannel.objects.get(pk=self.pk)
        for field in self.FIXED_FIELDS:
            attr = f"{field}_id" if field.endswith("_port") else field
            if getattr(self, attr) != getattr(db_obj, attr):
                raise ValidationError(
                    _("Cannot modify %(field)s on a fixed WDM node. Only status can be changed.") % {"field": field}
                )

    def clean(self):
        """On fixed nodes, only status may be changed after creation."""
        super().clean()
        self._check_fixed_fields()

    def save(self, *args, **kwargs):
        """Enforce fixed node constraints at save time."""
        self._check_fixed_fields()
        super().save(*args, **kwargs)


class WdmCircuit(NetBoxModel):
    """An end-to-end WDM circuit spanning WDM channels."""

    prerequisite_models = ("netbox_wdm.WdmNode",)

    name = models.CharField(max_length=200, verbose_name=_("name"))
    status = models.CharField(
        max_length=50,
        choices=WdmCircuitStatusChoices,
        default=WdmCircuitStatusChoices.PLANNED,
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
        related_name="wdm_circuits",
        verbose_name=_("tenant"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    comments = models.TextField(blank=True, verbose_name=_("comments"))

    clone_fields = ("status", "wavelength_nm", "tenant")

    class Meta:
        ordering = ("name",)
        verbose_name = _("WDM circuit")
        verbose_name_plural = _("WDM circuits")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_wdm:wdmcircuit", args=[self.pk])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status if self.pk else None

    def clean(self):
        """Validate channel consistency: same grid, matching wavelength."""
        super().clean()

        if not self.pk:
            return

        segments = list(self.path_segments.select_related("channel__wdm_node"))
        if not segments:
            return

        grids = set()
        svc_wl = Decimal(str(self.wavelength_nm))
        for seg in segments:
            grids.add(seg.channel.wdm_node.grid)

        if len(grids) > 1:
            raise ValidationError(
                _("All WDM nodes in a circuit must use the same grid. Found: %(grids)s")
                % {"grids": ", ".join(sorted(grids))}
            )

        for seg in segments:
            ch_wl = Decimal(str(seg.channel.wavelength_nm))
            if abs(ch_wl - svc_wl) > Decimal("0.01"):
                raise ValidationError(
                    _("Channel %(label)s has wavelength %(ch_wl)s nm but circuit wavelength is %(svc_wl)s nm.")
                    % {
                        "label": seg.channel.label,
                        "ch_wl": seg.channel.wavelength_nm,
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
            if self.status == WdmCircuitStatusChoices.DECOMMISSIONED:
                channel_ids = self.path_segments.values_list("channel_id", flat=True)
                self.path_segments.all().delete()
                WdmChannel.objects.filter(pk__in=channel_ids).update(status=WdmChannelStatusChoices.AVAILABLE)

    def get_stitched_path(self):
        """Return the stitched end-to-end path as an ordered list of hop dicts."""
        hops = []
        for seg in self.path_segments.select_related(
            "channel__wdm_node__device",
            "channel__mux_front_port",
            "channel__demux_front_port",
        ).order_by("sequence"):
            ch = seg.channel
            hops.append(
                {
                    "type": "wdm_node",
                    "node_id": ch.wdm_node_id,
                    "node_name": ch.wdm_node.device.name,
                    "channel_id": ch.pk,
                    "channel_label": ch.label,
                    "wavelength_nm": float(ch.wavelength_nm),
                    "mux_front_port_id": ch.mux_front_port_id,
                    "mux_connected": bool(ch.mux_front_port and ch.mux_front_port.cable_id),
                    "demux_front_port_id": ch.demux_front_port_id,
                    "demux_connected": bool(ch.demux_front_port and ch.demux_front_port.cable_id),
                }
            )
        return hops


class WdmCircuitPath(models.Model):
    """Links a WDM circuit to channels in sequence. PROTECT prevents channel deletion."""

    circuit = models.ForeignKey(
        to="netbox_wdm.WdmCircuit",
        on_delete=models.CASCADE,
        related_name="path_segments",
        verbose_name=_("circuit"),
    )
    channel = models.ForeignKey(
        to="netbox_wdm.WdmChannel",
        on_delete=models.PROTECT,
        verbose_name=_("channel"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("sequence"))

    class Meta:
        ordering = ("circuit", "sequence")
        verbose_name = _("WDM circuit path")
        verbose_name_plural = _("WDM circuit paths")
        constraints = [
            models.UniqueConstraint(
                fields=["circuit", "channel"],
                name="unique_circuit_channel",
            ),
            models.UniqueConstraint(
                fields=["circuit", "sequence"],
                name="unique_circuit_sequence",
            ),
        ]

    def __str__(self):
        return f"{self.circuit} #{self.sequence}: {self.channel}"
