from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()

router.register("wdm-profiles", views.WdmProfileViewSet)
router.register("wdm-channel-plans", views.WdmChannelPlanViewSet)
router.register("wdm-nodes", views.WdmNodeViewSet)
router.register("wdm-line-ports", views.WdmLinePortViewSet)
router.register("wdm-channels", views.WdmChannelViewSet)
router.register("wdm-circuits", views.WdmCircuitViewSet)

urlpatterns = router.urls
