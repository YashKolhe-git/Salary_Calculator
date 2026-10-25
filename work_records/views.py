from decimal import Decimal
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from config.permissions import IsAuthenticatedAdmin
from .models import DailyWorkRecord, Payment
from .serializers import DailyWorkRecordSerializer, PaymentSerializer


@extend_schema_view(
    list=extend_schema(
        summary="List daily work records",
        description=(
            "List work records with server-side earnings calculations, total paid, and balance due. "
            "Supports filtering by employee, specific work date, or date ranges."
        ),
        parameters=[
            OpenApiParameter(
                name='employee',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by Employee ID'
            ),
            OpenApiParameter(
                name='work_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter by exact work date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='start_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter work dates on or after start date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='end_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter work dates on or before end date (YYYY-MM-DD)'
            ),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve work record details"),
    create=extend_schema(summary="Create a new daily work record"),
    update=extend_schema(summary="Update a work record and recompute earnings"),
    partial_update=extend_schema(summary="Partially update a work record"),
)
class DailyWorkRecordViewSet(viewsets.ModelViewSet):
    """
    CRUD API for DailyWorkRecord entries.
    Automatically applies wage snapshot resolution and calculates earnings server-side.
    """
    serializer_class = DailyWorkRecordSerializer
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]

    def get_queryset(self):
        # Annotate total paid to eliminate N+1 queries during listing
        queryset = DailyWorkRecord.objects.select_related('employee').annotate(
            annotated_total_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0.00')))
        ).order_by('-work_date', '-created_at')

        params = self.request.query_params

        employee_id = params.get('employee')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)

        work_date = params.get('work_date')
        if work_date:
            queryset = queryset.filter(work_date=work_date)

        start_date = params.get('start_date')
        if start_date:
            queryset = queryset.filter(work_date__gte=start_date)

        end_date = params.get('end_date')
        if end_date:
            queryset = queryset.filter(work_date__lte=end_date)

        return queryset

    def destroy(self, request, *args, **kwargs):
        """
        Prevent deleting work records that already have payments associated.
        """
        record = self.get_object()
        if record.payments.exists():
            raise ValidationError({
                'detail': "Cannot delete a work record that has associated payment records."
            })
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        responses={200: PaymentSerializer(many=True)},
        summary="List payments for this work record",
        description="Retrieve all disbursement payments logged against this specific daily work record."
    )
    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        record = self.get_object()
        payments = record.payments.all().order_by('-payment_date', '-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="List payment records",
        description="List all disbursements with optional filtering by work record ID or payment date.",
        parameters=[
            OpenApiParameter(
                name='work_record',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by DailyWorkRecord ID'
            ),
            OpenApiParameter(
                name='payment_date',
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter by payment date (YYYY-MM-DD)'
            ),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve payment details"),
    create=extend_schema(summary="Record a payment disbursement"),
)
class PaymentViewSet(viewsets.ModelViewSet):
    """
    API for recording and viewing payments disbursed to employees for daily work records.
    Physical deletions and mutations of payment history are disallowed to protect audit integrity.
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]
    http_method_names = ['get', 'post', 'head', 'options']  # Read and create only

    def get_queryset(self):
        queryset = Payment.objects.select_related('work_record', 'work_record__employee').all().order_by(
            '-payment_date', '-created_at'
        )
        work_record_id = self.request.query_params.get('work_record')
        if work_record_id:
            queryset = queryset.filter(work_record_id=work_record_id)

        payment_date = self.request.query_params.get('payment_date')
        if payment_date:
            queryset = queryset.filter(payment_date=payment_date)

        return queryset

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(
            method='DELETE',
            detail="Physical deletion of payment records is not permitted. Payment history must be preserved."
        )
