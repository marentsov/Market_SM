from django.urls import path
from .views import (
    DashboardView,
    PavilionListView,
    BuildingListView,
    TenantListView,
    ContractListView,
    MeterListView,
)

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardView.as_view(), name='index'),
    path('pavilions/', PavilionListView.as_view(), name='pavilions_list'),
    path('buildings/', BuildingListView.as_view(), name='buildings_list'),
    path('tenants/', TenantListView.as_view(), name='tenants_list'),
    path('contracts/', ContractListView.as_view(), name='contracts_list'),
    path('meters/', MeterListView.as_view(), name='meters_list'),
]
