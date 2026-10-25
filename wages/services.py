from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import EmployeeWageRate, GlobalWageSetting


def check_date_range_overlap(model_class, effective_from, effective_to, employee=None, exclude_id=None):
    """
    Checks if the proposed [effective_from, effective_to] range overlaps with any existing records.
    Two date ranges [A_start, A_end] and [B_start, B_end] overlap if:
      A_start <= B_end (if B_end is not None) AND
      (A_end is None OR A_end >= B_start)
    """
    if effective_to and effective_to < effective_from:
        raise ValidationError({'effective_to': 'Effective to date must be greater than or equal to effective from date.'})

    qs = model_class.objects.all()
    if employee is not None:
        qs = qs.filter(employee=employee)
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)

    # Condition 1: existing.effective_from <= effective_to (if effective_to is defined)
    if effective_to is not None:
        qs = qs.filter(effective_from__lte=effective_to)

    # Condition 2: existing.effective_to is None or existing.effective_to >= effective_from
    qs = qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=effective_from))

    overlapping = qs.first()
    if overlapping:
        to_str = overlapping.effective_to.strftime('%Y-%m-%d') if overlapping.effective_to else 'indefinite'
        raise ValidationError(
            f"The effective date range ({effective_from} to {effective_to or 'indefinite'}) "
            f"overlaps with an existing record ({overlapping.effective_from} to {to_str})."
        )


def resolve_effective_wage(employee, work_date):
    """
    Resolves the wage rate applicable for a given employee on a specific work date.
    
    Resolution order:
    1. Employee-specific rate effective on work_date.
    2. Global wage setting effective on work_date.
    3. If neither is found, raises a ValidationError.
    
    Returns tuple: (wage_amount, wage_basis, source_record)
    """
    # 1. Check employee-specific override
    emp_rate = EmployeeWageRate.objects.filter(
        employee=employee,
        effective_from__lte=work_date
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=work_date)
    ).order_by('-effective_from', '-created_at', '-id').first()

    if emp_rate:
        return emp_rate.wage_amount, emp_rate.wage_basis, emp_rate

    # 2. Check global wage setting
    global_rate = GlobalWageSetting.objects.filter(
        effective_from__lte=work_date
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=work_date)
    ).order_by('-effective_from', '-created_at', '-id').first()

    if global_rate:
        return global_rate.wage_amount, global_rate.wage_basis, global_rate

    # 3. Not found
    raise ValidationError(
        f"No applicable wage setting found for employee '{employee.name}' on {work_date}. "
        f"Please configure an employee-specific wage rate or a global wage setting."
    )
