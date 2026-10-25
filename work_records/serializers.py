from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum
from rest_framework import serializers

from employees.models import Employee
from wages.models import WageBasis
from wages.services import resolve_effective_wage
from .models import DailyWorkRecord, Payment
from .services import (
    calculate_work_record_earnings,
    compute_payment_summary,
    process_work_record_payment,
    quantize_currency,
)


class PaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for Payment instances.
    Enforces positive payment amounts, balance checks, and row-level concurrency protection.
    """
    employee_name = serializers.CharField(source='work_record.employee.name', read_only=True)
    work_date = serializers.DateField(source='work_record.work_date', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id',
            'work_record',
            'employee_name',
            'work_date',
            'amount',
            'payment_date',
            'payment_method',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'employee_name', 'work_date']

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return quantize_currency(value)

    def validate(self, attrs):
        work_record = attrs.get('work_record', self.instance.work_record if self.instance else None)
        amount = attrs.get('amount', self.instance.amount if self.instance else None)

        if not work_record:
            raise serializers.ValidationError({'work_record': 'Work record is required.'})

        # Pre-validation check on balance (final lock-guarded check is in process_work_record_payment)
        current_paid = work_record.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        remaining_balance = max(Decimal('0.00'), work_record.total_earnings - current_paid)
        if amount and amount > remaining_balance:
            raise serializers.ValidationError({
                'amount': f"Payment amount ({amount}) exceeds remaining balance due ({remaining_balance})."
            })

        return attrs

    def create(self, validated_data):
        try:
            return process_work_record_payment(
                work_record_id=validated_data['work_record'].id,
                amount=validated_data['amount'],
                payment_date=validated_data['payment_date'],
                payment_method=validated_data.get('payment_method'),
                notes=validated_data.get('notes'),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.message if hasattr(exc, 'message') else str(exc)}
            )


class DailyWorkRecordSerializer(serializers.ModelSerializer):
    """
    Serializer for DailyWorkRecord instances.
    Enforces server-side earnings calculations, wage snapshot preservation, and derived payment summary.
    """
    base_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.00'),
        help_text="Actual regular earnings for daily-paid and monthly-paid workers. For hourly-paid workers, calculated as hours_worked * wage_rate."
    )
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    total_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = DailyWorkRecord
        fields = [
            'id',
            'employee',
            'employee_name',
            'work_date',
            'hours_worked',
            'minutes_worked',
            'wage_rate',
            'wage_basis',
            'base_amount',
            'overtime_minutes',
            'overtime_amount',
            'extra_pay',
            'total_earnings',
            'total_paid',
            'balance_due',
            'payment_status',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'wage_rate',
            'wage_basis',
            'overtime_amount',
            'total_earnings',
            'total_paid',
            'balance_due',
            'payment_status',
            'employee_name',
            'created_at',
            'updated_at',
        ]

    def _get_summary(self, obj):
        # Cache summary on object instance to avoid duplicate queries
        if not hasattr(obj, '_cached_payment_summary'):
            # If annotated_total_paid is present from queryset optimization, use it
            if hasattr(obj, 'annotated_total_paid') and obj.annotated_total_paid is not None:
                paid = obj.annotated_total_paid
            else:
                paid = obj.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            obj._cached_payment_summary = compute_payment_summary(obj.total_earnings, paid)
        return obj._cached_payment_summary

    def get_total_paid(self, obj) -> str:
        return str(self._get_summary(obj)['total_paid'])

    def get_balance_due(self, obj) -> str:
        return str(self._get_summary(obj)['balance_due'])

    def get_payment_status(self, obj) -> str:
        return self._get_summary(obj)['payment_status']

    def validate_hours_worked(self, value):
        if value is None or value < 0 or value > 24:
            raise serializers.ValidationError("Hours worked must be between 0 and 24.")
        return value

    def validate_minutes_worked(self, value):
        if value is not None and (value < 0 or value > 59):
            raise serializers.ValidationError("Minutes worked must be between 0 and 59.")
        return value or 0

    def validate_overtime_minutes(self, value):
        if value < 0:
            raise serializers.ValidationError("Overtime minutes cannot be negative.")
        return value

    def validate_extra_pay(self, value):
        if value < Decimal('0.00'):
            raise serializers.ValidationError("Extra pay cannot be negative.")
        return quantize_currency(value)

    def validate(self, attrs):
        instance = self.instance
        employee = attrs.get('employee', instance.employee if instance else None)
        work_date = attrs.get('work_date', instance.work_date if instance else None)

        if not employee:
            raise serializers.ValidationError({'employee': 'Employee is required.'})
        if not work_date:
            raise serializers.ValidationError({'work_date': 'Work date is required.'})

        # Inactive employees cannot receive new work records, but corrections to historical records are allowed
        if instance is None:
            if not employee.is_active:
                raise serializers.ValidationError({
                    'employee': f"Employee '{employee.name}' is inactive. Cannot create new work records."
                })
        else:
            if employee != instance.employee and not employee.is_active:
                raise serializers.ValidationError({
                    'employee': f"Cannot reassign work record to inactive employee '{employee.name}'."
                })

        # Check unique constraint (one record per employee per work_date)
        qs = DailyWorkRecord.objects.filter(employee=employee, work_date=work_date)
        if instance:
            qs = qs.exclude(id=instance.id)
        if qs.exists():
            raise serializers.ValidationError({
                'detail': f"A work record already exists for employee '{employee.name}' on {work_date}."
            })

        # If updating and changing employee or work_date, ensure payments do not exist
        if instance:
            if (employee != instance.employee or work_date != instance.work_date):
                if instance.payments.exists():
                    raise serializers.ValidationError({
                        'detail': "Cannot change employee or work date of a work record that already has payment history."
                    })
        else:
            # For monthly-paid workers, require manual entry of actual regular earnings (base_amount)
            if attrs.get('base_amount') is None:
                try:
                    _, wage_basis, _ = resolve_effective_wage(employee, work_date)
                    if wage_basis == WageBasis.MONTHLY:
                        raise serializers.ValidationError({
                            'base_amount': 'Actual regular earnings (base amount) must be entered manually for monthly-paid work records.'
                        })
                except DjangoValidationError:
                    pass

        return attrs

    def create(self, validated_data):
        employee = validated_data['employee']
        work_date = validated_data['work_date']
        hours_worked = validated_data.get('hours_worked', 0)
        minutes_worked = validated_data.get('minutes_worked', 0)
        overtime_minutes = validated_data.get('overtime_minutes', 0)
        extra_pay = validated_data.get('extra_pay', Decimal('0.00'))
        manual_base = validated_data.get('base_amount')
        notes = validated_data.get('notes', '')

        # Resolve wage rate effective on work_date
        try:
            wage_rate, wage_basis, _ = resolve_effective_wage(employee, work_date)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.message if hasattr(exc, 'message') else str(exc)}
            )

        # Server-side earnings calculation
        calc = calculate_work_record_earnings(
            wage_rate=wage_rate,
            wage_basis=wage_basis,
            hours_worked=hours_worked,
            manual_base_amount=manual_base,
            extra_pay=extra_pay,
            minutes_worked=minutes_worked,
            overtime_minutes=overtime_minutes,
        )

        return DailyWorkRecord.objects.create(
            employee=employee,
            work_date=work_date,
            hours_worked=hours_worked,
            minutes_worked=minutes_worked,
            wage_rate=wage_rate,
            wage_basis=wage_basis,
            base_amount=calc['base_amount'],
            overtime_minutes=overtime_minutes,
            overtime_amount=calc['overtime_amount'],
            extra_pay=calc['extra_pay'],
            total_earnings=calc['total_earnings'],
            notes=notes,
        )

    def update(self, instance, validated_data):
        """
        Updates an existing work record.
        Preserves the historical wage snapshot (wage_rate and wage_basis) unless employee/date
        were modified (when no payments exist).
        Allows correcting historical work records with financial safeguards.
        """
        employee = validated_data.get('employee', instance.employee)
        work_date = validated_data.get('work_date', instance.work_date)
        hours_worked = validated_data.get('hours_worked', instance.hours_worked)
        minutes_worked = validated_data.get('minutes_worked', instance.minutes_worked)
        overtime_minutes = validated_data.get('overtime_minutes', instance.overtime_minutes)
        extra_pay = validated_data.get('extra_pay', instance.extra_pay)
        notes = validated_data.get('notes', instance.notes)

        # If employee or date was changed (safe only when no payments exist):
        if employee != instance.employee or work_date != instance.work_date:
            try:
                wage_rate, wage_basis, _ = resolve_effective_wage(employee, work_date)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(
                    exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.message if hasattr(exc, 'message') else str(exc)}
                )
        else:
            # PRESERVE HISTORICAL WAGE SNAPSHOT
            wage_rate = instance.wage_rate
            wage_basis = instance.wage_basis

        # Determine manual base amount for daily and monthly wage basis
        if wage_basis in (WageBasis.DAILY, WageBasis.MONTHLY):
            manual_base = validated_data.get('base_amount', instance.base_amount)
        else:
            manual_base = None

        # Recalculate earnings with current inputs and preserved/resolved rate
        calc = calculate_work_record_earnings(
            wage_rate=wage_rate,
            wage_basis=wage_basis,
            hours_worked=hours_worked,
            manual_base_amount=manual_base,
            extra_pay=extra_pay,
            minutes_worked=minutes_worked,
            overtime_minutes=overtime_minutes,
        )

        # Ensure that new total_earnings does not drop below existing total_paid
        current_paid = instance.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if calc['total_earnings'] < current_paid:
            raise serializers.ValidationError({
                'detail': (
                    f"Recalculated total earnings ({calc['total_earnings']}) cannot be lower than the amount "
                    f"already paid ({current_paid}) for this work record."
                )
            })

        instance.employee = employee
        instance.work_date = work_date
        instance.hours_worked = hours_worked
        instance.minutes_worked = minutes_worked
        instance.wage_rate = wage_rate
        instance.wage_basis = wage_basis
        instance.base_amount = calc['base_amount']
        instance.overtime_minutes = overtime_minutes
        instance.overtime_amount = calc['overtime_amount']
        instance.extra_pay = calc['extra_pay']
        instance.total_earnings = calc['total_earnings']
        instance.notes = notes
        instance.save()

        return instance
