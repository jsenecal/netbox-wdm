from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

urlpatterns = [
    # WDM Profile
    path("wdm-profiles/", views.WdmProfileListView.as_view(), name="wdmprofile_list"),
    path("wdm-profiles/add/", views.WdmProfileEditView.as_view(), name="wdmprofile_add"),
    path(
        "wdm-profiles/import/",
        views.WdmProfileBulkImportView.as_view(),
        name="wdmprofile_import",
    ),
    path(
        "wdm-profiles/delete/",
        views.WdmProfileBulkDeleteView.as_view(),
        name="wdmprofile_bulk_delete",
    ),
    path("wdm-profiles/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmprofile"))),
    # WDM Channel Plan
    path("wdm-channel-plans/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmchannelplan"))),
    # WDM Node
    path("wdm-nodes/", views.WdmNodeListView.as_view(), name="wdmnode_list"),
    path("wdm-nodes/add/", views.WdmNodeEditView.as_view(), name="wdmnode_add"),
    path("wdm-nodes/import/", views.WdmNodeBulkImportView.as_view(), name="wdmnode_import"),
    path("wdm-nodes/delete/", views.WdmNodeBulkDeleteView.as_view(), name="wdmnode_bulk_delete"),
    path("wdm-nodes/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmnode"))),
    # WDM Line Port
    path("wdm-line-ports/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmlineport"))),
    # WDM Channel
    path("wdm-channels/", views.WdmChannelListView.as_view(), name="wdmchannel_list"),
    path("wdm-channels/add/", views.WdmChannelEditView.as_view(), name="wdmchannel_add"),
    path(
        "wdm-channels/edit/",
        views.WdmChannelBulkEditView.as_view(),
        name="wdmchannel_bulk_edit",
    ),
    path(
        "wdm-channels/delete/",
        views.WdmChannelBulkDeleteView.as_view(),
        name="wdmchannel_bulk_delete",
    ),
    path("wdm-channels/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmchannel"))),
    # WDM Circuit
    path("wdm-circuits/", views.WdmCircuitListView.as_view(), name="wdmcircuit_list"),
    path("wdm-circuits/add/", views.WdmCircuitEditView.as_view(), name="wdmcircuit_add"),
    path(
        "wdm-circuits/import/",
        views.WdmCircuitBulkImportView.as_view(),
        name="wdmcircuit_import",
    ),
    path(
        "wdm-circuits/delete/",
        views.WdmCircuitBulkDeleteView.as_view(),
        name="wdmcircuit_bulk_delete",
    ),
    path("wdm-circuits/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmcircuit"))),
]
