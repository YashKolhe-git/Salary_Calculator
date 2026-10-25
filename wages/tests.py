import datetime
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from employees.models import Employee
from .models import EmployeeWageRate, GlobalWageSetting, WageBasis
from .services import check_date_range_overlap, resolve_effective_wage


class WageModelTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(name="Anita Sharma")

    def test_create_global_wage_setting(self):
        setting = GlobalWageSetting.objects.create(
            wage_amount=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1),
            effective_to=datetime.date(2026, 12, 31)
        )
        self.assertEqual(setting.wage_amount, Decimal('800.00'))
        self.assertEqual(setting.wage_basis, 'daily')
        self.assertEqual(str(setting), "Global Wage: 800.00 / daily (2026-01-01 to 2026-12-31)")

    def test_global_wage_setting_effective_dates_validation(self):
        setting = GlobalWageSetting(
            wage_amount=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 6, 1),
            effective_to=datetime.date(2026, 5, 1)
        )
        with self.assertRaises(ValidationError):
            setting.clean()

    def test_create_employee_wage_rate(self):
        rate = EmployeeWageRate.objects.create(
            employee=self.employee,
            wage_amount=Decimal('950.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1)
        )
        self.assertEqual(rate.employee, self.employee)
        self.assertEqual(rate.wage_amount, Decimal('950.00'))
        self.assertIsNone(rate.effective_to)
        self.assertIn("Anita Sharma", str(rate))
        self.assertIn("Present", str(rate))

    def test_employee_wage_rate_effective_dates_validation(self):
        rate = EmployeeWageRate(
            employee=self.employee,
            wage_amount=Decimal('950.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 6, 1),
            effective_to=datetime.date(2026, 5, 1)
        )
        with self.assertRaises(ValidationError):
            rate.clean()

    def test_negative_wage_amount_validation(self):
        setting = GlobalWageSetting(
            wage_amount=Decimal('-100.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1)
        )
        with self.assertRaises(ValidationError):
            setting.full_clean()


class WageServicesTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(name="Anita Sharma")

    def test_wage_resolution_hierarchy(self):
        # 1. Neither configured -> raises error
        with self.assertRaises(ValidationError):
            resolve_effective_wage(self.employee, datetime.date(2026, 5, 15))

        # 2. Global wage configured -> resolves global wage
        GlobalWageSetting.objects.create(
            wage_amount=Decimal('600.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1)
        )
        amount, basis, _ = resolve_effective_wage(self.employee, datetime.date(2026, 5, 15))
        self.assertEqual(amount, Decimal('600.00'))
        self.assertEqual(basis, WageBasis.DAILY)

        # 3. Employee wage configured -> overrides global wage
        EmployeeWageRate.objects.create(
            employee=self.employee,
            wage_amount=Decimal('750.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 5, 1)
        )
        amount, basis, _ = resolve_effective_wage(self.employee, datetime.date(2026, 5, 15))
        self.assertEqual(amount, Decimal('750.00'))

        # 4. Before employee wage effective date -> still resolves global wage
        amount, basis, _ = resolve_effective_wage(self.employee, datetime.date(2026, 4, 15))
        self.assertEqual(amount, Decimal('600.00'))

    def test_overlapping_date_ranges_detected(self):
        GlobalWageSetting.objects.create(
            wage_amount=Decimal('500.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1),
            effective_to=datetime.date(2026, 6, 30)
        )
        # Attempt overlap 2026-06-01 to 2026-12-31
        with self.assertRaises(ValidationError):
            check_date_range_overlap(
                model_class=GlobalWageSetting,
                effective_from=datetime.date(2026, 6, 1),
                effective_to=datetime.date(2026, 12, 31)
            )


class WageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username='admin',
            password='adminpassword123',
            is_staff=True,
            is_superuser=True
        )
        self.employee = Employee.objects.create(name="Anita Sharma")

    def test_unauthenticated_wages_access_denied(self):
        response = self.client.get('/api/wages/global/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_create_and_get_global_wage(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'wage_amount': '650.00',
            'wage_basis': 'daily',
            'effective_from': '2026-01-01',
            'effective_to': '2026-12-31'
        }
        create_resp = self.client.post('/api/wages/global/', payload)
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_resp.data['wage_amount'], '650.00')

        get_resp = self.client.get('/api/wages/global/')
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(get_resp.data['wage_amount'], '650.00')

    def test_global_wage_history(self):
        self.client.force_authenticate(user=self.admin_user)
        GlobalWageSetting.objects.create(
            wage_amount=Decimal('500.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2025, 1, 1),
            effective_to=datetime.date(2025, 12, 31)
        )
        GlobalWageSetting.objects.create(
            wage_amount=Decimal('600.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1),
            effective_to=datetime.date(2026, 12, 31)
        )
        response = self.client.get('/api/wages/global/history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_reject_overlapping_global_wage_api(self):
        self.client.force_authenticate(user=self.admin_user)
        GlobalWageSetting.objects.create(
            wage_amount=Decimal('500.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1),
            effective_to=datetime.date(2026, 6, 30)
        )
        # Attempt to create overlapping setting
        payload = {
            'wage_amount': '700.00',
            'wage_basis': 'daily',
            'effective_from': '2026-06-15',
            'effective_to': '2026-12-31'
        }
        response = self.client.post('/api/wages/global/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_employee_wage_rates_api(self):
        self.client.force_authenticate(user=self.admin_user)
        # Create rate via nested endpoint
        payload = {
            'wage_amount': '850.00',
            'wage_basis': 'daily',
            'effective_from': '2026-01-01'
        }
        response = self.client.post(f'/api/employees/{self.employee.id}/wage-rates/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['wage_amount'], '850.00')

        # List rates for employee
        list_resp = self.client.get(f'/api/employees/{self.employee.id}/wage-rates/')
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data), 1)

    def test_reject_overlapping_employee_wage_api(self):
        self.client.force_authenticate(user=self.admin_user)
        EmployeeWageRate.objects.create(
            employee=self.employee,
            wage_amount=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1),
            effective_to=datetime.date(2026, 6, 30)
        )
        # Attempt overlapping rate
        payload = {
            'wage_amount': '900.00',
            'wage_basis': 'daily',
            'effective_from': '2026-05-01',
            'effective_to': '2026-10-31'
        }
        response = self.client.post(f'/api/employees/{self.employee.id}/wage-rates/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_negative_or_zero_wage(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'wage_amount': '0.00',
            'wage_basis': 'daily',
            'effective_from': '2026-01-01'
        }
        response = self.client.post('/api/wages/global/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_and_resolve_monthly_wage_setting(self):
        self.client.force_authenticate(user=self.admin_user)
        # Create global monthly wage
        payload = {
            'wage_amount': '30000.00',
            'wage_basis': 'monthly',
            'effective_from': '2026-01-01'
        }
        response = self.client.post('/api/wages/global/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['wage_basis'], 'monthly')
        self.assertEqual(response.data['wage_amount'], '30000.00')

        # Check resolution for employee
        amount, basis, _ = resolve_effective_wage(self.employee, datetime.date(2026, 6, 1))
        self.assertEqual(amount, Decimal('30000.00'))
        self.assertEqual(basis, 'monthly')

    def test_create_employee_specific_monthly_wage_rate_api(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'wage_amount': '45000.00',
            'wage_basis': 'monthly',
            'effective_from': '2026-01-01'
        }
        response = self.client.post(f'/api/employees/{self.employee.id}/wage-rates/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['wage_basis'], 'monthly')
        self.assertEqual(response.data['wage_amount'], '45000.00')

        amount, basis, _ = resolve_effective_wage(self.employee, datetime.date(2026, 2, 1))
        self.assertEqual(amount, Decimal('45000.00'))
        self.assertEqual(basis, 'monthly')
