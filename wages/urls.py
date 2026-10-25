from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    EmployeeWageRateViewSet,
    GlobalWageHistoryView,
    GlobalWageSettingView,
)

router = DefaultRouter()
router.register(r'rates', EmployeeWageRateViewSet, basename='wage-rate')

urlpatterns = [
    path('global/', GlobalWageSettingView.as_view(), name='global-wage-setting'),
    path('global/history/', GlobalWageHistoryView.as_view(), name='global-wage-history'),
] + router.urls
