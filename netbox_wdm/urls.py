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
    # WDM Channel Template
    path("wdm-channel-templates/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmchanneltemplate"))),
    # WDM Node
    path("wdm-nodes/", views.WdmNodeListView.as_view(), name="wdmnode_list"),
    path("wdm-nodes/add/", views.WdmNodeEditView.as_view(), name="wdmnode_add"),
    path("wdm-nodes/import/", views.WdmNodeBulkImportView.as_view(), name="wdmnode_import"),
    path("wdm-nodes/delete/", views.WdmNodeBulkDeleteView.as_view(), name="wdmnode_bulk_delete"),
    path("wdm-nodes/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmnode"))),
    # WDM Trunk Port
    path("wdm-trunk-ports/<int:pk>/", include(get_model_urls("netbox_wdm", "wdmtrunkport"))),
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
]
