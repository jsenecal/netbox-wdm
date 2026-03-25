from django.db import transaction
from django.db.models.signals import post_save


def _device_post_save(sender, instance, created, **kwargs):
    """Auto-create WdmNode when a Device is created from a DeviceType with a WDM profile."""
    if not created:
        return

    from .models import WdmDeviceTypeProfile, WdmNode

    try:
        profile = WdmDeviceTypeProfile.objects.get(device_type=instance.device_type)
    except WdmDeviceTypeProfile.DoesNotExist:
        return

    def _create_node():
        if WdmNode.objects.filter(device=instance).exists():
            return
        WdmNode.objects.create(
            device=instance,
            node_type=profile.node_type,
            grid=profile.grid,
        )

    transaction.on_commit(_create_node)


def connect_signals():
    """Connect device signals. Called from AppConfig.ready()."""
    from dcim.models import Device

    post_save.connect(_device_post_save, sender=Device, dispatch_uid="wdm_device_post_save")
