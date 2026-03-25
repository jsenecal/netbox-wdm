from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()

router.register("wdm-profiles", views.WdmDeviceTypeProfileViewSet)
router.register("wdm-channel-templates", views.WdmChannelTemplateViewSet)
router.register("wdm-nodes", views.WdmNodeViewSet)
router.register("wdm-line-ports", views.WdmLinePortViewSet)
router.register("wavelength-channels", views.WavelengthChannelViewSet)
router.register("wavelength-services", views.WavelengthServiceViewSet)

urlpatterns = router.urls
