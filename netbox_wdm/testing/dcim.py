"""DCIM foundation factories: sites, manufacturers, device roles."""

from dcim.models import DeviceRole, Manufacturer, Site


def create_site(name, slug=None):
    slug = slug or name.lower().replace(" ", "-")
    return Site.objects.create(name=name, slug=slug)


def create_manufacturer(name="WDM Vendor", slug=None):
    slug = slug or name.lower().replace(" ", "-")
    return Manufacturer.objects.create(name=name, slug=slug)


def create_device_roles():
    """Create standard WDM device roles. Returns dict keyed by slug."""
    roles = {}
    for name, slug in [
        ("WDM MUX", "wdm-mux"),
        ("WDM ROADM", "wdm-roadm"),
        ("WDM Amplifier", "wdm-amplifier"),
        ("Fiber Patch Panel", "fiber-pp"),
        ("Router", "router"),
    ]:
        role, _ = DeviceRole.objects.get_or_create(slug=slug, defaults={"name": name})
        roles[slug] = role
    return roles
