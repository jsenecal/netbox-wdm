from django.urls import include, path
from netbox.urls import get_model_urls

from . import views

urlpatterns = [
    # WDM Device Type Profile
    path("wdm-profiles/", views.WdmDeviceTypeProfileListView.as_view(), name="wdmdevicetypeprofile_list"),
    path("wdm-profiles/add/", views.WdmDeviceTypeProfileEditView.as_view(), name="wdmdevicetypeprofile_add"),
    path(
        "wdm-profiles/import/",
        views.WdmDeviceTypeProfileBulkImportView.as_view(),
        name="wdmdevicetypeprofile_import",
    ),
    path(
        "wdm-profiles/delete/",
        views.WdmDeviceTypeProfileBulkDeleteView.as_view(),
        name="wdmdevicetypeprofile_bulk_delete",
    ),
    path("wdm-profiles/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmdevicetypeprofile"))),
    path("wdm-profiles/<int:pk>/", views.WdmDeviceTypeProfileView.as_view(), name="wdmdevicetypeprofile"),
    path("wdm-profiles/<int:pk>/edit/", views.WdmDeviceTypeProfileEditView.as_view(), name="wdmdevicetypeprofile_edit"),
    path(
        "wdm-profiles/<int:pk>/delete/",
        views.WdmDeviceTypeProfileDeleteView.as_view(),
        name="wdmdevicetypeprofile_delete",
    ),
    # WDM Channel Template
    path("wdm-channel-templates/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmchanneltemplate"))),
    path("wdm-channel-templates/<int:pk>/", views.WdmChannelTemplateView.as_view(), name="wdmchanneltemplate"),
    path(
        "wdm-channel-templates/<int:pk>/edit/",
        views.WdmChannelTemplateEditView.as_view(),
        name="wdmchanneltemplate_edit",
    ),
    path(
        "wdm-channel-templates/<int:pk>/delete/",
        views.WdmChannelTemplateDeleteView.as_view(),
        name="wdmchanneltemplate_delete",
    ),
    # WDM Node
    path("wdm-nodes/", views.WdmNodeListView.as_view(), name="wdmnode_list"),
    path("wdm-nodes/add/", views.WdmNodeEditView.as_view(), name="wdmnode_add"),
    path("wdm-nodes/import/", views.WdmNodeBulkImportView.as_view(), name="wdmnode_import"),
    path("wdm-nodes/delete/", views.WdmNodeBulkDeleteView.as_view(), name="wdmnode_bulk_delete"),
    path("wdm-nodes/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmnode"))),
    path("wdm-nodes/<int:pk>/", views.WdmNodeView.as_view(), name="wdmnode"),
    path("wdm-nodes/<int:pk>/edit/", views.WdmNodeEditView.as_view(), name="wdmnode_edit"),
    path("wdm-nodes/<int:pk>/delete/", views.WdmNodeDeleteView.as_view(), name="wdmnode_delete"),
    # WDM Trunk Port
    path("wdm-trunk-ports/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmtrunkport"))),
    path("wdm-trunk-ports/<int:pk>/", views.WdmTrunkPortView.as_view(), name="wdmtrunkport"),
    path("wdm-trunk-ports/<int:pk>/edit/", views.WdmTrunkPortEditView.as_view(), name="wdmtrunkport_edit"),
    path("wdm-trunk-ports/<int:pk>/delete/", views.WdmTrunkPortDeleteView.as_view(), name="wdmtrunkport_delete"),
    # Wavelength Channel
    path("wavelength-channels/", views.WavelengthChannelListView.as_view(), name="wavelengthchannel_list"),
    path("wavelength-channels/add/", views.WavelengthChannelEditView.as_view(), name="wavelengthchannel_add"),
    path(
        "wavelength-channels/edit/",
        views.WavelengthChannelBulkEditView.as_view(),
        name="wavelengthchannel_bulk_edit",
    ),
    path(
        "wavelength-channels/delete/",
        views.WavelengthChannelBulkDeleteView.as_view(),
        name="wavelengthchannel_bulk_delete",
    ),
    path("wavelength-channels/<int:pk>/", include(get_model_urls("netbox_wdm", "wavelengthchannel"))),
    path("wavelength-channels/<int:pk>/", views.WavelengthChannelView.as_view(), name="wavelengthchannel"),
    path(
        "wavelength-channels/<int:pk>/edit/",
        views.WavelengthChannelEditView.as_view(),
        name="wavelengthchannel_edit",
    ),
    path(
        "wavelength-channels/<int:pk>/delete/",
        views.WavelengthChannelDeleteView.as_view(),
        name="wavelengthchannel_delete",
    ),
    # Wavelength Service
    path("wavelength-services/", views.WavelengthServiceListView.as_view(), name="wavelengthservice_list"),
    path("wavelength-services/add/", views.WavelengthServiceEditView.as_view(), name="wavelengthservice_add"),
    path(
        "wavelength-services/import/",
        views.WavelengthServiceBulkImportView.as_view(),
        name="wavelengthservice_import",
    ),
    path(
        "wavelength-services/delete/",
        views.WavelengthServiceBulkDeleteView.as_view(),
        name="wavelengthservice_bulk_delete",
    ),
    path("wavelength-services/<int:pk>/", include(get_model_urls("netbox_wdm", "wavelengthservice"))),
    path("wavelength-services/<int:pk>/", views.WavelengthServiceView.as_view(), name="wavelengthservice"),
    path(
        "wavelength-services/<int:pk>/edit/",
        views.WavelengthServiceEditView.as_view(),
        name="wavelengthservice_edit",
    ),
    path(
        "wavelength-services/<int:pk>/delete/",
        views.WavelengthServiceDeleteView.as_view(),
        name="wavelengthservice_delete",
    ),
]
