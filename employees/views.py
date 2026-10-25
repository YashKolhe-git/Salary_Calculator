from decimal import Decimal
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from config.permissions import IsAuthenticatedAdmin
from work_records.models import DailyWorkRecord, Payment
from work_records.serializers import DailyWorkRecordSerializer
from work_records.services import quantize_currency
from .models import Employee
from .serializers import (
    DashboardFinancialSummarySerializer,
    EmployeeBalanceSummarySerializer,
    EmployeeSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List employees",
        description="List all registered employees with optional filtering by active status and search by name or phone number.",
        parameters=[
            OpenApiParameter(
                name='is_active',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description='Filter by active status (true or false)'
            ),
            OpenApiParameter(
                name='search',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Search by employee name or phone number'
            ),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve employee details"),
    create=extend_schema(summary="Register a new employee"),
    update=extend_schema(summary="Update an employee's profile"),
    partial_update=extend_schema(summary="Partially update an employee's profile"),
)
class EmployeeViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Employee management.
    Restricted to authenticated administrators.
    """
    queryset = Employee.objects.all().order_by('name', '-created_at')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param is not None:
            if is_active_param.lower() in ('true', '1'):
                queryset = queryset.filter(is_active=True)
            elif is_active_param.lower() in ('false', '0'):
                queryset = queryset.filter(is_active=False)

        search_query = self.request.query_params.get('search')
        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(name__icontains=search_query) | Q(phone_number__icontains=search_query)
            )

        return queryset

    def destroy(self, request, *args, **kwargs):
        """
        Disallow hard deletion of employees to safeguard historical work and payment records.
        """
        raise MethodNotAllowed(
            method='DELETE',
            detail="Physical deletion of employees is not permitted. Deactivate the employee instead using /api/employees/{id}/deactivate/."
        )

    @extend_schema(
        request=None,
        responses={200: EmployeeSerializer},
        summary="Deactivate employee",
        description="Mark an employee as inactive. Historical work records remain intact."
    )
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        employee = self.get_object()
        employee.is_active = False
        employee.save(update_fields=['is_active', 'updated_at'])
        serializer = self.get_serializer(employee)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses={200: EmployeeSerializer},
        summary="Reactivate employee",
        description="Re-enable an employee to permit new work record entries."
    )
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        employee = self.get_object()
        employee.is_active = True
        employee.save(update_fields=['is_active', 'updated_at'])
        serializer = self.get_serializer(employee)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get employee financial balance summary",
        description="Returns aggregate financial summary (earnings, payments, balance, record counts) across all historical work records.",
        responses={200: EmployeeBalanceSummarySerializer}
    )
    @action(detail=True, methods=['get'], url_path='balance_summary')
    def balance_summary(self, request, pk=None):
        employee = self.get_object()

        # Aggregate total earnings directly on DailyWorkRecord to prevent join duplication
        total_earnings = DailyWorkRecord.objects.filter(employee=employee).aggregate(
            total=Sum('total_earnings')
        )['total'] or Decimal('0.00')

        # Aggregate total payments directly on Payment to prevent join duplication
        total_paid = Payment.objects.filter(work_record__employee=employee).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        total_earnings = quantize_currency(total_earnings)
        total_paid = quantize_currency(total_paid)
        outstanding_balance = max(Decimal('0.00'), total_earnings - total_paid)

        # Work record status counts
        annotated_records = DailyWorkRecord.objects.filter(employee=employee).annotate(
            rec_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0.00')))
        )

        counts = annotated_records.aggregate(
            total_count=Count('id'),
            unpaid_count=Count('id', filter=Q(rec_paid=Decimal('0.00'), total_earnings__gt=Decimal('0.00'))),
            partial_count=Count('id', filter=Q(rec_paid__gt=Decimal('0.00'), rec_paid__lt=F('total_earnings'))),
            paid_count=Count('id', filter=Q(rec_paid__gte=F('total_earnings')) | Q(total_earnings=Decimal('0.00'))),
        )

        data = {
            'employee_id': employee.id,
            'employee_name': employee.name,
            'is_active': employee.is_active,
            'total_earnings': str(total_earnings),
            'total_paid': str(total_paid),
            'outstanding_balance': str(outstanding_balance),
            'work_record_count': counts['total_count'] or 0,
            'unpaid_record_count': counts['unpaid_count'] or 0,
            'partially_paid_record_count': counts['partial_count'] or 0,
            'paid_record_count': counts['paid_count'] or 0,
        }

        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get employee transaction history",
        description="Returns paginated list of work records and payment summaries for this employee.",
        responses={200: DailyWorkRecordSerializer(many=True)}
    )
    @action(detail=True, methods=['get'], url_path='transactions')
    def transactions(self, request, pk=None):
        employee = self.get_object()
        records = DailyWorkRecord.objects.filter(employee=employee).annotate(
            annotated_total_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0.00')))
        ).order_by('-work_date', '-created_at')

        page = self.paginate_queryset(records)
        if page is not None:
            serializer = DailyWorkRecordSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DailyWorkRecordSerializer(records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get overall dashboard financial summary",
        description="Returns aggregate financial summary (employee counts, earnings, payments, balance, record status counts) across all employees.",
        responses={200: DashboardFinancialSummarySerializer}
    )
    @action(detail=False, methods=['get'], url_path='financial_summary')
    def financial_summary(self, request):
        total_employees = Employee.objects.count()
        active_employees = Employee.objects.filter(is_active=True).count()
        inactive_employees = Employee.objects.filter(is_active=False).count()

        total_earnings = DailyWorkRecord.objects.aggregate(
            total=Sum('total_earnings')
        )['total'] or Decimal('0.00')

        total_paid = Payment.objects.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        total_earnings = quantize_currency(total_earnings)
        total_paid = quantize_currency(total_paid)
        outstanding_balance = max(Decimal('0.00'), total_earnings - total_paid)

        annotated_records = DailyWorkRecord.objects.annotate(
            rec_paid=Coalesce(Sum('payments__amount'), Value(Decimal('0.00')))
        )

        counts = annotated_records.aggregate(
            total_count=Count('id'),
            unpaid_count=Count('id', filter=Q(rec_paid=Decimal('0.00'), total_earnings__gt=Decimal('0.00'))),
            partial_count=Count('id', filter=Q(rec_paid__gt=Decimal('0.00'), rec_paid__lt=F('total_earnings'))),
            paid_count=Count('id', filter=Q(rec_paid__gte=F('total_earnings')) | Q(total_earnings=Decimal('0.00'))),
        )

        data = {
            'total_employees': total_employees,
            'active_employees': active_employees,
            'inactive_employees': inactive_employees,
            'total_earnings': str(total_earnings),
            'total_paid': str(total_paid),
            'outstanding_balance': str(outstanding_balance),
            'work_record_count': counts['total_count'] or 0,
            'unpaid_record_count': counts['unpaid_count'] or 0,
            'partially_paid_record_count': counts['partial_count'] or 0,
            'paid_record_count': counts['paid_count'] or 0,
        }

        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get overall dashboard financial summary (alias)",
        description="Alias endpoint for /api/employees/financial_summary/.",
        responses={200: DashboardFinancialSummarySerializer}
    )
    @action(detail=False, methods=['get'], url_path='dashboard_summary')
    def dashboard_summary(self, request):
        return self.financial_summary(request)


