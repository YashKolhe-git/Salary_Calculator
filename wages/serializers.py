from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import EmployeeWageRate, GlobalWageSetting, WageBasis
from .services import check_date_range_overlap


class GlobalWageSettingSerializer(serializers.ModelSerializer):
    """
    Serializer for GlobalWageSetting instances.
    Enforces positive wage amounts, valid date sequences, and prevents overlapping periods.
    """
    class Meta:
        model = GlobalWageSetting
        fields = [
            'id',
            'wage_amount',
            'wage_basis',
            'effective_from',
            'effective_to',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_wage_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Wage amount must be greater than zero.")
        return value

    def validate(self, attrs):
        instance = self.instance
        effective_from = attrs.get('effective_from', instance.effective_from if instance else None)
        effective_to = attrs.get('effective_to', instance.effective_to if instance else None)

        if effective_from and effective_to and effective_to < effective_from:
            raise serializers.ValidationError({
                'effective_to': 'Effective to date must be greater than or equal to effective from date.'
            })

        exclude_id = instance.id if instance else None
        try:
            check_date_range_overlap(
                model_class=GlobalWageSetting,
                effective_from=effective_from,
                effective_to=effective_to,
                employee=None,
                exclude_id=exclude_id
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'detail': exc.message if hasattr(exc, 'message') else str(exc)})

        return attrs


class EmployeeWageRateSerializer(serializers.ModelSerializer):
    """
    Serializer for EmployeeWageRate instances.
    Enforces positive wage amounts, valid date sequences, and prevents overlapping periods per employee.
    """
    employee_name = serializers.CharField(source='employee.name', read_only=True)

    class Meta:
        model = EmployeeWageRate
        fields = [
            'id',
            'employee',
            'employee_name',
            'wage_amount',
            'wage_basis',
            'effective_from',
            'effective_to',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'employee_name']

    def validate_wage_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Wage amount must be greater than zero.")
        return value

    def validate(self, attrs):
        instance = self.instance
        employee = attrs.get('employee', instance.employee if instance else None)
        effective_from = attrs.get('effective_from', instance.effective_from if instance else None)
        effective_to = attrs.get('effective_to', instance.effective_to if instance else None)

        if not employee:
            raise serializers.ValidationError({'employee': 'Employee is required.'})

        if effective_from and effective_to and effective_to < effective_from:
            raise serializers.ValidationError({
                'effective_to': 'Effective to date must be greater than or equal to effective from date.'
            })

        exclude_id = instance.id if instance else None
        try:
            check_date_range_overlap(
                model_class=EmployeeWageRate,
                effective_from=effective_from,
                effective_to=effective_to,
                employee=employee,
                exclude_id=exclude_id
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'detail': exc.message if hasattr(exc, 'message') else str(exc)})

        return attrs
