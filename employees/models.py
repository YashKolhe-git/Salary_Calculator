from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Employee(models.Model):
    """
    Represents an employee in the Daily Wage Calculator system.
    """
    name = models.CharField(
        max_length=150,
        help_text="Full name of the employee."
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Optional contact phone number."
    )
    age = models.PositiveIntegerField(
        blank=True,
        null=True,
        validators=[
            MinValueValidator(1, message="Age must be at least 1 year."),
            MaxValueValidator(120, message="Age must not exceed 120 years.")
        ],
        help_text="Optional age of the employee."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this employee record is active."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the employee was registered."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the employee record was last updated."
    )

    class Meta:
        db_table = 'employees'
        ordering = ['name', '-created_at']
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        constraints = [
            models.CheckConstraint(
                check=models.Q(age__isnull=True) | (models.Q(age__gte=1) & models.Q(age__lte=120)),
                name='check_employee_age_range'
            )
        ]

    def __str__(self):
        return self.name
