from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from wages.models import WageBasis
from .models import DailyWorkRecord, Payment


def quantize_currency(value: Decimal) -> Decimal:
    """
    Quantize monetary values to 2 decimal places using standard ROUND_HALF_UP.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_work_record_earnings(
    wage_rate: Decimal,
    wage_basis: str,
    hours_worked: int,
    manual_base_amount: Decimal = None,
    extra_pay: Decimal = Decimal('0.00'),
    minutes_worked: int = 0,
    overtime_minutes: int = 0,
) -> dict:
    """
    Calculates base_amount, overtime_amount, and total_earnings server-side.
    
    Rules:
    - No fixed working schedule or mandatory standard workday.
    - Whole hours worked are entered by admin.
    - For daily-paid workers (wage_basis == 'daily'):
        - wage_rate is the agreed daily reference rate snapshot.
        - base_amount is entered manually by the admin (or defaults to agreed wage_rate if not specified).
        - Earnings are NOT automatically prorated by hours worked.
        - overtime_amount is Decimal('0.00').
    - For monthly-paid workers (wage_basis == 'monthly'):
        - wage_rate is the agreed monthly salary reference snapshot.
        - base_amount is entered manually by the admin as actual regular earnings for the work record.
        - Never automatically divided by 30 or calculated from hours worked.
        - overtime_amount is Decimal('0.00').
    - For hourly-paid workers (wage_basis == 'hourly'):
        - Regular earnings = whole hours worked * applicable hourly rate.
        - If historical minutes_worked exists, it is handled without fixed schedule assumptions.
        - base_amount = regular earnings.
        - overtime_amount is Decimal('0.00').
    - Total earnings = base_amount + extra_pay.
    """
    if hours_worked < 0 or hours_worked > 24:
        raise ValidationError({'hours_worked': 'Hours worked must be between 0 and 24.'})

    if minutes_worked < 0 or minutes_worked > 59:
        raise ValidationError({'minutes_worked': 'Minutes worked must be between 0 and 59.'})

    if overtime_minutes < 0:
        raise ValidationError({'overtime_minutes': 'Overtime minutes cannot be negative.'})

    if extra_pay < Decimal('0.00'):
        raise ValidationError({'extra_pay': 'Extra pay cannot be negative.'})

    if wage_rate < Decimal('0.00'):
        raise ValidationError({'wage_rate': 'Wage rate cannot be negative.'})

    if not isinstance(wage_rate, Decimal):
        wage_rate = Decimal(str(wage_rate))

    if wage_basis == WageBasis.HOURLY:
        if minutes_worked:
            duration_hours = Decimal(hours_worked) + (Decimal(minutes_worked) / Decimal('60'))
        else:
            duration_hours = Decimal(hours_worked)
        base_amount = quantize_currency(duration_hours * wage_rate)
        overtime_amount = Decimal('0.00')

    elif wage_basis == WageBasis.DAILY:
        if manual_base_amount is not None:
            if not isinstance(manual_base_amount, Decimal):
                manual_base_amount = Decimal(str(manual_base_amount))
            if manual_base_amount < Decimal('0.00'):
                raise ValidationError({'base_amount': 'Base earnings cannot be negative.'})
            base_amount = quantize_currency(manual_base_amount)
        else:
            base_amount = quantize_currency(wage_rate)
        overtime_amount = Decimal('0.00')

    elif wage_basis == WageBasis.MONTHLY:
        if manual_base_amount is not None:
            if not isinstance(manual_base_amount, Decimal):
                manual_base_amount = Decimal(str(manual_base_amount))
            if manual_base_amount < Decimal('0.00'):
                raise ValidationError({'base_amount': 'Base earnings cannot be negative.'})
            base_amount = quantize_currency(manual_base_amount)
        else:
            raise ValidationError({
                'base_amount': 'Actual regular earnings (base amount) must be entered manually for monthly-paid work records.'
            })
        overtime_amount = Decimal('0.00')

    else:
        raise ValidationError({'wage_basis': f"Unsupported wage basis: '{wage_basis}'. Only hourly, daily, and monthly are supported."})

    extra_pay_quantized = quantize_currency(extra_pay)
    total_earnings = quantize_currency(base_amount + extra_pay_quantized)

    return {
        'base_amount': base_amount,
        'overtime_amount': overtime_amount,
        'extra_pay': extra_pay_quantized,
        'total_earnings': total_earnings,
    }


def compute_payment_summary(total_earnings: Decimal, total_paid: Decimal) -> dict:
    """
    Derives balance_due and payment_status from total_earnings and total_paid.
    Consistent payment statuses:
      - 'not_paid': total_paid == 0 and total_earnings > 0
      - 'partially_paid': 0 < total_paid < total_earnings
      - 'paid': total_paid >= total_earnings (including 0 earnings when 0 balance is due)
    """
    total_earnings = quantize_currency(total_earnings)
    total_paid = quantize_currency(total_paid)

    balance_due = max(Decimal('0.00'), total_earnings - total_paid)

    if total_earnings == Decimal('0.00'):
        status = 'paid'
    elif total_paid == Decimal('0.00'):
        status = 'not_paid'
    elif total_paid < total_earnings:
        status = 'partially_paid'
    else:
        status = 'paid'

    return {
        'total_paid': total_paid,
        'balance_due': balance_due,
        'payment_status': status,
    }


@transaction.atomic
def process_work_record_payment(work_record_id: int, amount: Decimal, payment_date, payment_method=None, notes=None) -> Payment:
    """
    Atomically records a payment against a DailyWorkRecord.
    Uses select_for_update() row locking to strictly prevent concurrent overpayments.
    """
    try:
        work_record = DailyWorkRecord.objects.select_for_update().get(id=work_record_id)
    except DailyWorkRecord.DoesNotExist:
        raise ValidationError({'work_record': f"Work record with ID {work_record_id} does not exist."})

    amount = quantize_currency(amount)
    if amount <= Decimal('0.00'):
        raise ValidationError({'amount': 'Payment amount must be greater than zero.'})

    current_paid = work_record.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    current_paid = quantize_currency(current_paid)
    remaining_balance = max(Decimal('0.00'), work_record.total_earnings - current_paid)

    if amount > remaining_balance:
        raise ValidationError({
            'amount': (
                f"Payment amount of {amount} exceeds the remaining balance due ({remaining_balance}). "
                f"Total earnings: {work_record.total_earnings}, Total already paid: {current_paid}."
            )
        })

    payment = Payment.objects.create(
        work_record=work_record,
        amount=amount,
        payment_date=payment_date,
        payment_method=payment_method,
        notes=notes
    )
    return payment
