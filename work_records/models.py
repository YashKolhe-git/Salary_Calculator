from decimal import Decimal
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from wages.models import WageBasis


class DailyWorkRecord(models.Model):
    """
    Historical snapshot of an employee's daily work entry and earnings.
    Snapshot values (wage_rate, wage_basis, base_amount, overtime_amount, extra_pay, total_earnings)
    are permanently recorded and are not affected by subsequent wage setting changes.
    """
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='work_records',
        db_column='employee_id',
        help_text="Employee associated with this work record."
    )
    work_date = models.DateField(
        db_index=True,
        help_text="Date on which the work was performed."
    )
    hours_worked = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0, message="Hours worked cannot be negative."),
            MaxValueValidator(24, message="Hours worked cannot exceed 24 hours.")
        ],
        help_text="Regular hours worked (0-24)."
    )
    minutes_worked = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0, message="Minutes worked cannot be negative."),
            MaxValueValidator(59, message="Minutes worked cannot exceed 59 minutes.")
        ],
        help_text="Regular minutes worked (0-59)."
    )
    wage_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'), message="Wage rate cannot be negative.")],
        help_text="Snapshot of the wage rate applied for this work record."
    )
    wage_basis = models.CharField(
        max_length=20,
        choices=WageBasis.choices,
        help_text="Snapshot of the wage basis (hourly, daily, monthly) applied."
    )
    base_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'), message="Base amount cannot be negative.")],
        help_text="Base earnings calculated for regular hours/work."
    )
    overtime_minutes = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0, message="Overtime minutes cannot be negative.")],
        help_text="Overtime duration in minutes."
    )
    overtime_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'), message="Overtime amount cannot be negative.")],
        help_text="Overtime pay calculated for this record."
    )
    extra_pay = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'), message="Extra pay cannot be negative.")],
        help_text="Additional bonuses, allowances or incentives for the day."
    )
    total_earnings = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'), message="Total earnings cannot be negative.")],
        help_text="Total calculated earnings for the day (base + overtime + extra pay)."
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Optional remarks or notes about the day's work."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the work record was created."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the work record was last modified."
    )

    class Meta:
        db_table = 'daily_work_records'
        ordering = ['-work_date', '-created_at']
        verbose_name = 'Daily Work Record'
        verbose_name_plural = 'Daily Work Records'
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'work_date'],
                name='unique_employee_work_date'
            ),
            models.CheckConstraint(
                check=models.Q(hours_worked__gte=0) & models.Q(hours_worked__lte=24),
                name='check_hours_worked_range'
            ),
            models.CheckConstraint(
                check=models.Q(minutes_worked__gte=0) & models.Q(minutes_worked__lte=59),
                name='check_minutes_worked_range'
            ),
            models.CheckConstraint(
                check=models.Q(wage_rate__gte=0),
                name='check_work_wage_rate_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(base_amount__gte=0),
                name='check_base_amount_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(overtime_minutes__gte=0),
                name='check_overtime_minutes_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(overtime_amount__gte=0),
                name='check_overtime_amount_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(extra_pay__gte=0),
                name='check_extra_pay_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(total_earnings__gte=0),
                name='check_total_earnings_non_negative'
            ),
        ]
        indexes = [
            models.Index(fields=['work_date'], name='idx_work_records_work_date'),
        ]

    def __str__(self):
        return f"{self.employee.name} | {self.work_date} | Earnings: {self.total_earnings}"


class Payment(models.Model):
    """
    Supports full and partial payments against a daily work record.
    Multiple payment entries may be linked to one work record.
    """
    work_record = models.ForeignKey(
        DailyWorkRecord,
        on_delete=models.PROTECT,
        related_name='payments',
        db_column='work_record_id',
        help_text="Associated daily work record for which this payment was made."
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message="Payment amount must be greater than zero.")],
        help_text="Amount paid."
    )
    payment_date = models.DateField(
        help_text="Date on which the payment was disbursed."
    )
    payment_method = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Payment method (e.g. Cash, Bank Transfer, UPI, Cheque)."
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Optional payment reference or notes."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this payment record was logged."
    )

    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date', '-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='check_payment_amount_positive'
            ),
        ]

    def __str__(self):
        return f"Payment #{self.id}: {self.amount} on {self.payment_date} (Record #{self.work_record_id})"
