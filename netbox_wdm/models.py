from __future__ import annotations

from decimal import Decimal
from typing import Any

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
from .dataclasses import PathElement, path_element_from_channel


def _module_wdm_profile(module: Any) -> WdmProfile | None:
    """Return the WdmProfile attached to a module's ModuleType, or None."""
    if module is None:
        return None
    try:
        return module.module_type.wdm_profile
    except WdmProfile.DoesNotExist:
        return None


class WdmProfile(NetBoxModel):
    """WDM capability profile attached to a DeviceType or a ModuleType."""

    prerequisite_models = ("dcim.DeviceType", "dcim.ModuleType")

    device_type = models.OneToOneField(
        to="dcim.DeviceType",
        on_delete=models.CASCADE,
        related_name="wdm_profile",
        blank=True,
        null=True,
        verbose_name=_("device type"),
    )
    module_type = models.OneToOneField(
        to="dcim.ModuleType",
        on_delete=models.CASCADE,
        related_name="wdm_profile",
        blank=True,
        null=True,
        verbose_name=_("module type"),
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
        ordering = ("device_type", "module_type")
        verbose_name = _("WDM profile")
        verbose_name_plural = _("WDM profiles")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(device_type__isnull=False, module_type__isnull=True)
                    | models.Q(device_type__isnull=True, module_type__isnull=False)
                ),
                name="wdmprofile_exactly_one_anchor",
            ),
        ]

    def __str__(self) -> str:
        return f"WDM Profile: {self.anchor}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmprofile", args=[self.pk])

    @property
    def anchor(self):
        """The DeviceType or ModuleType this profile is attached to."""
        return self.device_type or self.module_type

    def clean(self) -> None:
        super().clean()
        if bool(self.device_type) == bool(self.module_type):
            raise ValidationError(_("A WDM profile must be attached to exactly one of device type or module type."))


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

    def __str__(self) -> str:
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmchannelplan", args=[self.pk])

    def clean(self) -> None:
        super().clean()
        if not self.profile_id:
            return
        for field in ("mux_front_port_template", "demux_front_port_template"):
            fpt = getattr(self, field)
            if fpt is None:
                continue
            if self.profile.device_type_id and fpt.device_type_id != self.profile.device_type_id:
                raise ValidationError({field: _("Template does not belong to the profile's device type.")})
            if self.profile.module_type_id and fpt.module_type_id != self.profile.module_type_id:
                raise ValidationError({field: _("Template does not belong to the profile's module type.")})


class WdmLinePortPlan(NetBoxModel):
    """Line port blueprint on a WdmProfile: which rear port template is a trunk, and its direction/role."""

    profile = models.ForeignKey(
        to="netbox_wdm.WdmProfile",
        on_delete=models.CASCADE,
        related_name="line_port_plans",
        verbose_name=_("profile"),
    )
    rear_port_template = models.ForeignKey(
        to="dcim.RearPortTemplate",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("rear port template"),
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
        ordering = ("profile", "direction", "role")
        verbose_name = _("WDM line port plan")
        verbose_name_plural = _("WDM line port plans")
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "rear_port_template"],
                name="unique_lineportplan_rear_port_template",
            ),
            models.UniqueConstraint(
                fields=["profile", "direction", "role"],
                name="unique_lineportplan_direction_role",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.direction}/{self.role}: {self.rear_port_template}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmlineportplan", args=[self.pk])

    def clean(self) -> None:
        super().clean()
        if not self.profile_id or not self.rear_port_template_id:
            return
        rpt = self.rear_port_template
        if self.profile.device_type_id and rpt.device_type_id != self.profile.device_type_id:
            raise ValidationError({"rear_port_template": _("Template does not belong to the profile's device type.")})
        if self.profile.module_type_id and rpt.module_type_id != self.profile.module_type_id:
            raise ValidationError({"rear_port_template": _("Template does not belong to the profile's module type.")})


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
        blank=True,
        default="",
        verbose_name=_("node type"),
    )
    grid = models.CharField(
        max_length=50,
        choices=WdmGridChoices,
        blank=True,
        default="",
        verbose_name=_("grid"),
    )
    description = models.TextField(blank=True, verbose_name=_("description"))
    expected_port_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("expected port hash"),
    )
    port_sync_valid = models.BooleanField(
        default=True,
        verbose_name=_("port sync valid"),
    )

    clone_fields = ("node_type", "grid")

    class Meta:
        ordering = ("device",)
        verbose_name = _("WDM node")
        verbose_name_plural = _("WDM nodes")

    def __str__(self) -> str:
        return f"WDM: {self.device.name}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmnode", args=[self.pk])

    @property
    def is_fixed(self) -> bool:
        """Fixed nodes have hardware-determined channel and port assignments.

        Only ROADM nodes allow runtime changes to channels and line ports.
        """
        return self.node_type != WdmNodeTypeChoices.ROADM

    def validate_channel_mapping(self, desired_mapping: dict[int, dict[str, int | None]]) -> list[str]:
        """Validate proposed channel-to-port mapping changes.

        desired_mapping format: { channel_pk: {"mux": port_id|None, "demux": port_id|None} }
        Returns list of error strings. Empty list means validation passed.
        """
        from dcim.models import FrontPort

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

            for fp_pk, kind in ((ports.get("mux"), "MUX"), (ports.get("demux"), "DEMUX")):
                if fp_pk is not None and ch is not None:
                    fp_module_id = FrontPort.objects.filter(pk=fp_pk).values_list("module_id", flat=True).first()
                    if fp_module_id != ch.module_id:
                        errors.append(f"{kind} FrontPort pk={fp_pk} does not belong to channel {label}'s module.")

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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and auto-populate channels and line ports from profiles on creation."""
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                self._auto_populate()

    def _auto_populate(self) -> None:
        """Create channels and line ports from the device type profile and installed module profiles.

        Idempotent: uses get_or_create throughout so repeated calls (module install
        signal, port sync repair) only fill gaps.
        """
        from dcim.models import Module

        self._populate_from_device_profile()
        for module in Module.objects.filter(device=self.device).select_related("module_type", "module_bay"):
            self.populate_module(module)

    def _populate_from_device_profile(self) -> None:
        from dcim.models import FrontPort, RearPort

        try:
            profile = self.device.device_type.wdm_profile
        except WdmProfile.DoesNotExist:
            return

        def resolve(template: Any) -> str:
            return template.name

        fp_by_name = {fp.name: fp for fp in FrontPort.objects.filter(device=self.device, module__isnull=True)}
        rp_by_name = {rp.name: rp for rp in RearPort.objects.filter(device=self.device, module__isnull=True)}
        self._create_channels(profile, None, resolve, fp_by_name)
        self._create_line_ports(profile, None, resolve, rp_by_name)

    def populate_module(self, module: Any) -> None:
        """Create channels and line ports for one installed module, if its ModuleType has a profile."""
        from dcim.models import FrontPort, RearPort

        profile = _module_wdm_profile(module)
        if profile is None:
            return

        def resolve(template: Any) -> str:
            return template.resolve_name(module=module)

        fp_by_name = {fp.name: fp for fp in FrontPort.objects.filter(module=module)}
        rp_by_name = {rp.name: rp for rp in RearPort.objects.filter(module=module)}
        self._create_channels(profile, module, resolve, fp_by_name)
        self._create_line_ports(profile, module, resolve, rp_by_name)

    def _create_channels(self, profile: WdmProfile, module: Any, resolve: Any, fp_by_name: dict) -> None:
        # Device-scoped: the node's own node_type is authoritative (matches historical
        # behavior and lets a WdmNode be marked AMPLIFIER regardless of its device
        # type's profile). Module-scoped: the module's own profile decides, since the
        # node-level node_type says nothing about what role an individual module plays.
        node_type = profile.node_type if module is not None else self.node_type
        if node_type == WdmNodeTypeChoices.AMPLIFIER:
            return
        plans = profile.channel_plans.select_related("mux_front_port_template", "demux_front_port_template")
        for cp in plans:
            mux_fp = fp_by_name.get(resolve(cp.mux_front_port_template)) if cp.mux_front_port_template else None
            demux_fp = fp_by_name.get(resolve(cp.demux_front_port_template)) if cp.demux_front_port_template else None
            WdmChannel.objects.get_or_create(
                wdm_node=self,
                module=module,
                grid_position=cp.grid_position,
                defaults={"mux_front_port": mux_fp, "demux_front_port": demux_fp},
            )

    def _create_line_ports(self, profile: WdmProfile, module: Any, resolve: Any, rp_by_name: dict) -> None:
        # Deliberately not gated on node_type == AMPLIFIER (unlike _create_channels above).
        # Amplifiers are pass-through devices: their trunk rear ports ARE line ports and
        # must still be created from the profile's line port plans. Amplifier-profile
        # modules get line ports but never channels, mirroring the node-level rule.
        for lpp in profile.line_port_plans.select_related("rear_port_template"):
            rp = rp_by_name.get(resolve(lpp.rear_port_template))
            if rp is None:
                continue
            WdmLinePort.objects.get_or_create(
                wdm_node=self,
                rear_port=rp,
                defaults={"direction": lpp.direction, "role": lpp.role, "module": module},
            )


class WdmLinePort(NetBoxModel):
    """Maps a RearPort on a WDM node to a directional line port."""

    wdm_node = models.ForeignKey(
        to="netbox_wdm.WdmNode",
        on_delete=models.CASCADE,
        related_name="line_ports",
        verbose_name=_("WDM node"),
    )
    module = models.ForeignKey(
        to="dcim.Module",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="wdm_line_ports",
        verbose_name=_("module"),
    )
    rear_port = models.ForeignKey(
        to="dcim.RearPort",
        # CASCADE, not PROTECT: this field is non-nullable and a line port has no
        # meaning without its rear port, so it mirrors the module FK above. PROTECT
        # also made module removal impossible: Django's delete collector checks
        # protected reverse relations while still walking the cascade, before any
        # pre_delete signal runs, so a module's own pre_delete handler never got a
        # chance to clear this relation first.
        on_delete=models.CASCADE,
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
                condition=models.Q(module__isnull=True),
                name="unique_lineport_direction_role",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "module", "direction", "role"],
                condition=models.Q(module__isnull=False),
                name="unique_lineport_module_direction_role",
            ),
        ]

    FIXED_FIELDS = ("rear_port", "direction", "role")

    def __str__(self) -> str:
        return f"{self.direction}: {self.rear_port}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmlineport", args=[self.pk])

    @property
    def is_fixed(self) -> bool:
        """Fixedness from the module's profile when module-scoped, else the node's."""
        profile = _module_wdm_profile(self.module)
        if profile is not None:
            return profile.node_type != WdmNodeTypeChoices.ROADM
        return self.wdm_node.is_fixed

    def _check_fixed_fields(self) -> None:
        """Check that fixed fields haven't changed on a fixed node."""
        if not self.pk or not self.is_fixed:
            return
        db_obj = WdmLinePort.objects.get(pk=self.pk)
        for field in self.FIXED_FIELDS:
            attr = f"{field}_id" if field == "rear_port" else field
            if getattr(self, attr) != getattr(db_obj, attr):
                raise ValidationError(_("Cannot modify %(field)s on a fixed WDM node.") % {"field": field})

    def clean(self) -> None:
        """On fixed nodes, line port configuration cannot be changed after creation."""
        super().clean()
        self._check_fixed_fields()
        if self.module_id and self.module.device_id != self.wdm_node.device_id:
            raise ValidationError({"module": _("Module belongs to a different device than the WDM node.")})
        if self.rear_port_id and self.rear_port.module_id != self.module_id:
            raise ValidationError({"rear_port": _("Rear port does not belong to the line port's module.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
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
    module = models.ForeignKey(
        to="dcim.Module",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="wdm_channels",
        verbose_name=_("module"),
    )
    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
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
                fields=["wdm_node", "grid_position"],
                condition=models.Q(module__isnull=True),
                name="unique_channel_grid_position",
            ),
            models.UniqueConstraint(
                fields=["wdm_node", "module", "grid_position"],
                condition=models.Q(module__isnull=False),
                name="unique_channel_module_grid_position",
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

    FIXED_FIELDS = ("mux_front_port", "demux_front_port")

    @property
    def effective_grid(self) -> str:
        """Grid from the module's profile when module-scoped, else the node's grid."""
        profile = _module_wdm_profile(self.module)
        if profile is not None:
            return profile.grid
        return self.wdm_node.grid

    @property
    def is_fixed(self) -> bool:
        """Fixedness from the module's profile when module-scoped, else the node's."""
        profile = _module_wdm_profile(self.module)
        if profile is not None:
            return profile.node_type != WdmNodeTypeChoices.ROADM
        return self.wdm_node.is_fixed

    @property
    def label(self) -> str:
        """ITU channel label derived from the effective grid and this channel's position."""
        from .wdm_constants import get_channel_info

        return get_channel_info(self.effective_grid, self.grid_position)[0]

    @property
    def wavelength_nm(self) -> Decimal:
        """Wavelength in nm derived from the effective grid and this channel's position."""
        from .wdm_constants import get_channel_info

        return get_channel_info(self.effective_grid, self.grid_position)[1]

    def __str__(self) -> str:
        return f"{self.label} ({self.wavelength_nm}nm)"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmchannel", args=[self.pk])

    def _check_fixed_fields(self) -> None:
        """Check that fixed fields haven't changed on a fixed node."""
        if not self.pk or not self.is_fixed:
            return
        db_obj = WdmChannel.objects.get(pk=self.pk)
        for field in self.FIXED_FIELDS:
            attr = f"{field}_id" if field.endswith("_port") else field
            if getattr(self, attr) != getattr(db_obj, attr):
                raise ValidationError(
                    _("Cannot modify %(field)s on a fixed WDM node. Only status can be changed.") % {"field": field}
                )

    def clean(self) -> None:
        """On fixed nodes, only status may be changed after creation."""
        super().clean()
        self._check_fixed_fields()
        if self.module_id and self.module.device_id != self.wdm_node.device_id:
            raise ValidationError({"module": _("Module belongs to a different device than the WDM node.")})
        if not self.module_id and not self.wdm_node.grid:
            raise ValidationError(_("Channels without a module require the node's grid to be set."))
        for field in ("mux_front_port", "demux_front_port"):
            fp = getattr(self, field)
            if fp is not None and fp.module_id != self.module_id:
                raise ValidationError({field: _("Front port does not belong to the channel's module.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Enforce fixed node constraints at save time."""
        self._check_fixed_fields()
        super().save(*args, **kwargs)


class WdmWavelengthPath(NetBoxModel):
    """An automatically discovered end-to-end wavelength path across connected WDM nodes."""

    grid_position = models.PositiveIntegerField(verbose_name=_("grid position"))
    wavelength_nm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("wavelength (nm)"),
    )
    is_complete = models.BooleanField(
        default=False,
        verbose_name=_("is complete"),
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name=_("is active"),
    )
    is_valid = models.BooleanField(
        default=True,
        verbose_name=_("is valid"),
        help_text=_("False if the path has directionality errors (e.g. TX-to-TX cabling)."),
    )

    class Meta:
        ordering = ("wavelength_nm",)
        verbose_name = _("WDM wavelength path")
        verbose_name_plural = _("WDM wavelength paths")

    def __str__(self) -> str:
        return f"WavelengthPath {self.pk} ({self.wavelength_nm}nm)"

    def get_display_label(self) -> str:
        """Rich label with node names for UI display. Queries the database."""
        node_names = list(
            self.path_channels.select_related("channel__wdm_node__device")
            .order_by("sequence")
            .values_list("channel__wdm_node__device__name", flat=True)
        )
        nodes_str = " \u2192 ".join(node_names) if node_names else "empty"
        return f"{self.wavelength_nm}nm: {nodes_str}"

    def get_channels(self) -> models.QuerySet[WdmChannel]:
        """Return channels in sequence order."""
        return WdmChannel.objects.filter(wavelength_path_entries__path=self).order_by(
            "wavelength_path_entries__sequence"
        )

    def get_stitched_path(self) -> list[PathElement]:
        """Return the stitched end-to-end path as an ordered list of PathElement dataclasses."""
        elements: list[PathElement] = []
        for entry in self.path_channels.select_related(
            "channel__wdm_node__device",
            "channel__mux_front_port",
            "channel__demux_front_port",
        ).order_by("sequence"):
            elements.append(path_element_from_channel(entry.channel, entry.sequence))
        return elements


class WdmWavelengthPathChannel(models.Model):
    """Through table linking a wavelength path to its channels in sequence."""

    path = models.ForeignKey(
        to="netbox_wdm.WdmWavelengthPath",
        on_delete=models.CASCADE,
        related_name="path_channels",
        verbose_name=_("path"),
    )
    channel = models.ForeignKey(
        to="netbox_wdm.WdmChannel",
        # CASCADE, not PROTECT: wavelength paths are derived data retraced from the
        # cable plant and channel plans, not a source of truth to protect a channel
        # deletion against. PROTECT here also made module removal impossible: a
        # module's channels cascade from dcim.Module (WdmChannel.module is CASCADE),
        # and Django's delete collector evaluates this reverse relation while still
        # walking that cascade, before any pre_delete signal runs -- so no signal
        # could ever clear it in time. The module pre_delete handler now prunes
        # left-over broken paths and retraces affected nodes after the cascade
        # completes instead.
        on_delete=models.CASCADE,
        related_name="wavelength_path_entries",
        verbose_name=_("channel"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("sequence"))

    class Meta:
        ordering = ("path", "sequence")
        verbose_name = _("wavelength path channel")
        verbose_name_plural = _("wavelength path channels")
        constraints = [
            models.UniqueConstraint(
                fields=["path", "channel"],
                name="unique_wavelength_path_channel",
            ),
            models.UniqueConstraint(
                fields=["path", "sequence"],
                name="unique_wavelength_path_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.path} #{self.sequence}: {self.channel}"


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
    wavelength_paths = models.ManyToManyField(
        to="netbox_wdm.WdmWavelengthPath",
        blank=True,
        related_name="circuits",
        verbose_name=_("wavelength paths"),
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

    clone_fields = ("status", "tenant")

    class Meta:
        ordering = ("name",)
        verbose_name = _("WDM circuit")
        verbose_name_plural = _("WDM circuits")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_wdm:wdmcircuit", args=[self.pk])

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._original_status = self.status if self.pk else None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and handle lifecycle transitions."""
        is_new = self._state.adding
        old_status = self._original_status

        super().save(*args, **kwargs)
        self._original_status = self.status

        if not is_new and old_status != self.status:
            if self.status == WdmCircuitStatusChoices.DECOMMISSIONED:
                paths = list(self.wavelength_paths.all())
                if paths:
                    channel_ids = WdmWavelengthPathChannel.objects.filter(path__in=paths).values_list(
                        "channel_id", flat=True
                    )
                    WdmChannel.objects.filter(pk__in=channel_ids).update(status=WdmChannelStatusChoices.AVAILABLE)
                    self.wavelength_paths.clear()

    def get_stitched_paths(self) -> list[tuple[WdmWavelengthPath, list[PathElement]]]:
        """Return the stitched paths as a list of (path, elements) tuples."""
        result = []
        for path in self.wavelength_paths.all():
            result.append((path, path.get_stitched_path()))
        return result
