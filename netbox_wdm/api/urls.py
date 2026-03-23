from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()

router.register("wdm-profiles", views.WdmDeviceTypeProfileViewSet)
router.register("wdm-channel-templates", views.WdmChannelTemplateViewSet)
router.register("wdm-nodes", views.WdmNodeViewSet)
router.register("wdm-trunk-ports", views.WdmTrunkPortViewSet)
router.register("wavelength-channels", views.WavelengthChannelViewSet)
router.register("wavelength-services", views.WavelengthServiceViewSet)

urlpatterns = router.urls
