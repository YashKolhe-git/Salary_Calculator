from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    """
    Serializer for Employee instances.
    Enforces age limits and exposes applicable wage rate and basis.
    """
    applicable_wage_rate = serializers.SerializerMethodField()
    applicable_wage_basis = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id',
            'name',
            'phone_number',
            'age',
            'is_active',
            'applicable_wage_rate',
            'applicable_wage_basis',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'applicable_wage_rate', 'applicable_wage_basis', 'created_at', 'updated_at']

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_applicable_wage_rate(self, obj):
        import datetime
        from wages.services import resolve_effective_wage
        try:
            rate, _, _ = resolve_effective_wage(obj, datetime.date.today())
            return str(rate)
        except Exception:
            return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_applicable_wage_basis(self, obj):
        import datetime
        from wages.services import resolve_effective_wage
        try:
            _, basis, _ = resolve_effective_wage(obj, datetime.date.today())
            return str(basis)
        except Exception:
            return None

    def validate_age(self, value):
        if value is not None and (value < 1 or value > 120):
            raise serializers.ValidationError("Age must be between 1 and 120 years.")
        return value

    def validate_name(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Employee name cannot be blank.")
        return stripped

    def validate_phone_number(self, value):
        if value:
            stripped = value.strip()
            if stripped:
                qs = Employee.objects.filter(phone_number__iexact=stripped)
                if self.instance:
                    qs = qs.exclude(id=self.instance.id)
                if qs.exists():
                    existing = qs.first()
                    raise serializers.ValidationError(
                        f"An employee with phone number '{stripped}' already exists ({existing.name}). "
                        "Please update their existing profile instead of creating a duplicate."
                    )
                return stripped
        return None


class EmployeeBalanceSummarySerializer(serializers.Serializer):
    """
    Serializer for aggregated employee financial summary.
    """
    employee_id = serializers.IntegerField(read_only=True)
    employee_name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    total_earnings = serializers.CharField(read_only=True)
    total_paid = serializers.CharField(read_only=True)
    outstanding_balance = serializers.CharField(read_only=True)
    work_record_count = serializers.IntegerField(read_only=True)
    unpaid_record_count = serializers.IntegerField(read_only=True)
    partially_paid_record_count = serializers.IntegerField(read_only=True)
    paid_record_count = serializers.IntegerField(read_only=True)


class DashboardFinancialSummarySerializer(serializers.Serializer):
    """
    Serializer for aggregate dashboard financial summary across the entire organization.
    """
    total_employees = serializers.IntegerField(read_only=True)
    active_employees = serializers.IntegerField(read_only=True)
    inactive_employees = serializers.IntegerField(read_only=True)
    total_earnings = serializers.CharField(read_only=True)
    total_paid = serializers.CharField(read_only=True)
    outstanding_balance = serializers.CharField(read_only=True)
    work_record_count = serializers.IntegerField(read_only=True)
    unpaid_record_count = serializers.IntegerField(read_only=True)
    partially_paid_record_count = serializers.IntegerField(read_only=True)
    paid_record_count = serializers.IntegerField(read_only=True)


