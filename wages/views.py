import datetime
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from config.permissions import IsAuthenticatedAdmin
from employees.models import Employee
from .models import EmployeeWageRate, GlobalWageSetting
from .serializers import EmployeeWageRateSerializer, GlobalWageSettingSerializer


class GlobalWageSettingView(APIView):
    """
    Manage global default wage settings.
    GET: Returns the currently active global wage setting (or latest if none explicitly active today).
    POST: Creates a new global wage setting with effective dates.
    """
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]

    @extend_schema(
        summary="Retrieve current active global wage setting",
        description="Returns the global wage setting applicable as of today, or the latest setting on record.",
        responses={200: GlobalWageSettingSerializer}
    )
    def get(self, request):
        today = datetime.date.today()
        # Find setting active today
        current_setting = GlobalWageSetting.objects.filter(
            effective_from__lte=today
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).order_by('-effective_from', '-created_at').first()

        if not current_setting:
            # Fall back to latest configured setting
            current_setting = GlobalWageSetting.objects.order_by('-effective_from', '-created_at').first()

        if not current_setting:
            return Response(
                {"detail": "No global wage setting has been configured yet."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = GlobalWageSettingSerializer(current_setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=GlobalWageSettingSerializer,
        responses={201: GlobalWageSettingSerializer},
        summary="Create a new global wage setting",
        description="Configure a new global wage rate with effective dates. Validates against overlapping periods."
    )
    def post(self, request):
        serializer = GlobalWageSettingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting = serializer.save()
        return Response(GlobalWageSettingSerializer(setting).data, status=status.HTTP_201_CREATED)


class GlobalWageHistoryView(APIView):
    """
    Retrieve full historical list of global wage settings.
    """
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]

    @extend_schema(
        summary="List global wage settings history",
        description="Returns all global wage settings ordered chronologically by effective date.",
        responses={200: GlobalWageSettingSerializer(many=True)}
    )
    def get(self, request):
        settings = GlobalWageSetting.objects.all().order_by('-effective_from', '-created_at')
        serializer = GlobalWageSettingSerializer(settings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="List employee wage rates",
        description="List employee-specific wage rates with optional filtering by employee ID.",
        parameters=[
            OpenApiParameter(
                name='employee',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by Employee ID'
            )
        ]
    ),
    retrieve=extend_schema(summary="Retrieve employee wage rate details"),
    create=extend_schema(summary="Create an employee wage rate"),
    update=extend_schema(summary="Update an employee wage rate"),
    partial_update=extend_schema(summary="Partially update an employee wage rate"),
    destroy=extend_schema(summary="Delete an employee wage rate"),
)
class EmployeeWageRateViewSet(viewsets.ModelViewSet):
    """
    CRUD API for individual employee wage overrides.
    """
    queryset = EmployeeWageRate.objects.select_related('employee').all().order_by('-effective_from', '-created_at')
    serializer_class = EmployeeWageRateSerializer
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()
        employee_id = self.request.query_params.get('employee')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        return queryset


class EmployeeWageRatesNestedView(APIView):
    """
    Manage wage rates for a specific employee: /api/employees/{id}/wage-rates/
    """
    permission_classes = [IsAuthenticated, IsAuthenticatedAdmin]

    @extend_schema(
        summary="List wage rates for employee",
        description="Returns all specific wage rates configured for the specified employee.",
        responses={200: EmployeeWageRateSerializer(many=True)}
    )
    def get(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id)
        rates = EmployeeWageRate.objects.filter(employee=employee).order_by('-effective_from', '-created_at')
        serializer = EmployeeWageRateSerializer(rates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=EmployeeWageRateSerializer,
        responses={201: EmployeeWageRateSerializer},
        summary="Create wage rate for employee",
        description="Add a specific wage override rate for this employee."
    )
    def post(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id)
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['employee'] = employee.id

        serializer = EmployeeWageRateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        wage_rate = serializer.save()
        return Response(EmployeeWageRateSerializer(wage_rate).data, status=status.HTTP_201_CREATED)
