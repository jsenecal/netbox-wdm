"""Rename the C-band grid keys to carry an explicit band segment.

The grid column stores the choice key verbatim, so renaming the keys in
WdmGridChoices leaves existing rows pointing at keys that no longer resolve.
A row left behind would not raise: WdmChannel.label and .wavelength_nm
swallow the resulting KeyError and render blank, so the damage would show up
as unlabelled channels rather than as an error. Rewrite the stored values in
step with the choice keys.
"""

from django.db import migrations

GRID_RENAMES = (
    ("dwdm_100ghz", "dwdm_c_100ghz"),
    ("dwdm_50ghz", "dwdm_c_50ghz"),
)

# Both models carry an independent grid column.
GRID_MODELS = ("WdmProfile", "WdmNode")


def _rewrite(apps, renames):
    for model_name in GRID_MODELS:
        model = apps.get_model("netbox_wdm", model_name)
        for old, new in renames:
            model.objects.filter(grid=old).update(grid=new)


def rename_forward(apps, schema_editor):
    _rewrite(apps, GRID_RENAMES)


def rename_backward(apps, schema_editor):
    _rewrite(apps, tuple((new, old) for old, new in GRID_RENAMES))


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_wdm", "0011_alter_pathchannel_channel"),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_backward),
    ]
