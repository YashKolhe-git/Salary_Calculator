"""
URL configuration for Daily Wage Calculator backend project.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from config.auth_views import CurrentUserView, LoginView, LogoutView
from employees.views import EmployeeViewSet
from wages.views import (
    EmployeeWageRatesNestedView,
    EmployeeWageRateViewSet,
    GlobalWageHistoryView,
    GlobalWageSettingView,
)
from work_records.views import DailyWorkRecordViewSet, PaymentViewSet

# Main API router
api_router = DefaultRouter()
api_router.register(r'employees', EmployeeViewSet, basename='employee')
api_router.register(r'wage-rates', EmployeeWageRateViewSet, basename='wage-rate')
api_router.register(r'work-records', DailyWorkRecordViewSet, basename='work-record')
api_router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),

    # Authentication endpoints
    path('api/auth/login/', LoginView.as_view(), name='auth-login'),
    path('api/auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('api/auth/me/', CurrentUserView.as_view(), name='auth-me'),

    # Global wage settings endpoints
    path('api/wages/global/', GlobalWageSettingView.as_view(), name='global-wage-setting'),
    path('api/wages/global/history/', GlobalWageHistoryView.as_view(), name='global-wage-history'),

    # Employee-specific nested wage rates
    path('api/employees/<int:employee_id>/wage-rates/', EmployeeWageRatesNestedView.as_view(), name='employee-wage-rates-nested'),

    # API Documentation schemas
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Router-managed endpoints (/api/employees/, /api/wage-rates/, /api/work-records/, /api/payments/)
    path('api/', include(api_router.urls)),
]
