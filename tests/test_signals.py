"""Tests for signal handlers."""

import pytest
from dcim.models import PortMapping
from dcim.models.device_component_templates import PortTemplateMapping
from django.db.models.signals import post_save


@pytest.mark.django_db
def test_portmapping_signal_ignores_template_mapping_instance(dt_cwdm_dx):
    """Regression test for issue #22.

    NetBox's FrontPortFormMixin._save_m2m calls post_save.send with a hardcoded
    sender=PortMapping even when the instance is a PortTemplateMapping (created
    from a FrontPortTemplateForm on a DeviceType). PortTemplateMapping has no
    `device` attribute, so the signal handler must short-circuit instead of
    raising AttributeError.
    """
    template_mapping = PortTemplateMapping.objects.filter(device_type=dt_cwdm_dx).first()
    assert template_mapping is not None, "fixture should create at least one PortTemplateMapping"

    post_save.send(
        sender=PortMapping,
        instance=template_mapping,
        created=True,
        raw=False,
        update_fields=None,
    )
