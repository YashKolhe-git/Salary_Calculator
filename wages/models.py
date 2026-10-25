from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class WageBasis(models.TextChoices):
    HOURLY = 'hourly', 'Hourly'
    DAILY = 'daily', 'Daily'
    MONTHLY = 'monthly', 'Monthly'


class GlobalWageSetting(models.Model):
    """
    Stores global default wage rates with effective date ranges.
    """
    wage_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'), message="Wage amount cannot be negative.")],
        help_text="Standard wage amount for this global rate."
    )
    wage_basis = models.CharField(
        max_length=20,
        choices=WageBasis.choices,
        default=WageBasis.DAILY,
        help_text="Wage basis (hourly, daily, or monthly)."
    )
    effective_from = models.DateField(
        help_text="Date from which this global wage setting takes effect."
    )
    effective_to = models.DateField(
        blank=True,
        null=True,
        help_text="Optional end date for this global wage setting."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this setting record was created."
    )

    class Meta:
        db_table = 'global_wage_settings'
        ordering = ['-effective_from', '-created_at']
        verbose_name = 'Global Wage Setting'
        verbose_name_plural = 'Global Wage Settings'
        constraints = [
            models.CheckConstraint(
                check=models.Q(wage_amount__gte=0),
                name='check_global_wage_amount_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F('effective_from')),
                name='check_global_wage_effective_dates'
            ),
        ]

    def clean(self):
        super().clean()
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({
                'effective_to': 'Effective to date must be greater than or equal to effective from date.'
            })

    def __str__(self):
        to_str = self.effective_to.strftime('%Y-%m-%d') if self.effective_to else 'Present'
        return f"Global Wage: {self.wage_amount} / {self.wage_basis} ({self.effective_from} to {to_str})"


class EmployeeWageRate(models.Model):
    """
    Stores employee-specific wage rates that override the applicable global wage setting.
    """
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='wage_rates',
        db_column='employee_id',
        help_text="Employee this specific wage rate applies to."
    )
    wage_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'), message="Wage amount cannot be negative.")],
        help_text="Specific wage amount for this employee."
    )
    wage_basis = models.CharField(
        max_length=20,
        choices=WageBasis.choices,
        default=WageBasis.DAILY,
        help_text="Wage basis (hourly, daily, or monthly)."
    )
    effective_from = models.DateField(
        help_text="Date from which this wage rate takes effect."
    )
    effective_to = models.DateField(
        blank=True,
        null=True,
        help_text="Optional end date for this wage rate."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this employee wage rate was recorded."
    )

    class Meta:
        db_table = 'employee_wage_rates'
        ordering = ['-effective_from', '-created_at']
        verbose_name = 'Employee Wage Rate'
        verbose_name_plural = 'Employee Wage Rates'
        constraints = [
            models.CheckConstraint(
                check=models.Q(wage_amount__gte=0),
                name='check_emp_wage_amount_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F('effective_from')),
                name='check_emp_wage_effective_dates'
            ),
        ]

    def clean(self):
        super().clean()
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({
                'effective_to': 'Effective to date must be greater than or equal to effective from date.'
            })

    def __str__(self):
        to_str = self.effective_to.strftime('%Y-%m-%d') if self.effective_to else 'Present'
        return f"{self.employee.name}: {self.wage_amount} / {self.wage_basis} ({self.effective_from} to {to_str})"
