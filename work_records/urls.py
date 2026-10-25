from rest_framework.routers import DefaultRouter
from .views import DailyWorkRecordViewSet, PaymentViewSet

router = DefaultRouter()
router.register(r'work-records', DailyWorkRecordViewSet, basename='work-record')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = router.urls
