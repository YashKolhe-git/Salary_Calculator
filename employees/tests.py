import datetime
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from work_records.models import DailyWorkRecord, Payment
from wages.models import GlobalWageSetting, WageBasis
from .models import Employee


class EmployeeModelTests(TestCase):
    def test_create_employee_with_required_fields(self):
        emp = Employee.objects.create(name="Ramesh Kumar")
        self.assertEqual(emp.name, "Ramesh Kumar")
        self.assertTrue(emp.is_active)
        self.assertIsNone(emp.phone_number)
        self.assertIsNone(emp.age)
        self.assertIsNotNone(emp.created_at)
        self.assertIsNotNone(emp.updated_at)
        self.assertEqual(str(emp), "Ramesh Kumar")

    def test_create_employee_with_all_fields(self):
        emp = Employee.objects.create(
            name="Suresh Patel",
            phone_number="9876543210",
            age=32,
            is_active=True
        )
        self.assertEqual(emp.name, "Suresh Patel")
        self.assertEqual(emp.phone_number, "9876543210")
        self.assertEqual(emp.age, 32)
        self.assertTrue(emp.is_active)

    def test_employee_age_validation(self):
        emp = Employee(name="Invalid Age", age=150)
        with self.assertRaises(ValidationError):
            emp.full_clean()

    def test_employee_age_negative_validation(self):
        emp = Employee(name="Negative Age", age=0)
        with self.assertRaises(ValidationError):
            emp.full_clean()


class EmployeeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username='admin',
            password='adminpassword123',
            is_staff=True,
            is_superuser=True
        )
        self.regular_user = User.objects.create_user(
            username='worker',
            password='workerpassword123',
            is_staff=False
        )
        self.employee = Employee.objects.create(
            name="Vijay Kumar",
            phone_number="9988776655",
            age=29,
            is_active=True
        )

    def test_unauthenticated_request_rejected(self):
        response = self.client.get('/api/employees/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_non_staff_user_forbidden(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/api/employees/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_list_employees(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/employees/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check paginated results
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], "Vijay Kumar")

    def test_create_employee(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'name': 'Pooja Verma',
            'phone_number': '9123456780',
            'age': 25,
            'is_active': True
        }
        response = self.client.post('/api/employees/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Pooja Verma')
        self.assertTrue(Employee.objects.filter(name='Pooja Verma').exists())

    def test_create_employee_validation_errors(self):
        self.client.force_authenticate(user=self.admin_user)
        # Blank name
        response = self.client.post('/api/employees/', {'name': '   '})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid age
        response = self.client.post('/api/employees/', {'name': 'Valid Name', 'age': 150})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_and_update_employee(self):
        self.client.force_authenticate(user=self.admin_user)
        # Retrieve
        response = self.client.get(f'/api/employees/{self.employee.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Vijay Kumar')

        # Update (PATCH)
        response = self.client.patch(f'/api/employees/{self.employee.id}/', {'age': 30})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.age, 30)

    def test_deactivate_and_activate_employee(self):
        self.client.force_authenticate(user=self.admin_user)
        # Deactivate
        response = self.client.post(f'/api/employees/{self.employee.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

        # Reactivate
        response = self.client.post(f'/api/employees/{self.employee.id}/activate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_filter_and_search_employees(self):
        self.client.force_authenticate(user=self.admin_user)
        Employee.objects.create(name="Inactive Worker", is_active=False)

        # Filter active
        response = self.client.get('/api/employees/?is_active=true')
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Vijay Kumar')

        # Filter inactive
        response = self.client.get('/api/employees/?is_active=false')
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Inactive Worker')

        # Search
        response = self.client.get('/api/employees/?search=Vijay')
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Vijay Kumar')

    def test_physical_delete_is_disallowed(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(f'/api/employees/{self.employee.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Employee.objects.filter(id=self.employee.id).exists())

    def test_historical_work_records_remain_when_employee_deactivated(self):
        self.client.force_authenticate(user=self.admin_user)
        work_record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            hours_worked=8,
            minutes_worked=0,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )

        # Deactivate employee
        response = self.client.post(f'/api/employees/{self.employee.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Historical work record remains intact
        work_record.refresh_from_db()
        self.assertEqual(work_record.employee_id, self.employee.id)
        self.assertEqual(work_record.total_earnings, Decimal('800.00'))

    def test_balance_summary_authenticated_admin(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f'/api/employees/{self.employee.id}/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['employee_id'], self.employee.id)
        self.assertEqual(response.data['employee_name'], "Vijay Kumar")
        self.assertTrue(response.data['is_active'])

    def test_balance_summary_unauthenticated_rejected(self):
        response = self.client.get(f'/api/employees/{self.employee.id}/balance_summary/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_balance_summary_non_staff_forbidden(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(f'/api/employees/{self.employee.id}/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_balance_summary_nonexistent_employee(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/employees/99999/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_balance_summary_no_work_records(self):
        self.client.force_authenticate(user=self.admin_user)
        new_emp = Employee.objects.create(name="New Person")
        response = self.client.get(f'/api/employees/{new_emp.id}/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_earnings'], "0.00")
        self.assertEqual(response.data['total_paid'], "0.00")
        self.assertEqual(response.data['outstanding_balance'], "0.00")
        self.assertEqual(response.data['work_record_count'], 0)
        self.assertEqual(response.data['unpaid_record_count'], 0)
        self.assertEqual(response.data['partially_paid_record_count'], 0)
        self.assertEqual(response.data['paid_record_count'], 0)

    def test_balance_summary_correct_aggregation_and_counts(self):
        self.client.force_authenticate(user=self.admin_user)
        # Record 1: Unpaid (earnings 1000.00, paid 0.00)
        r1 = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        # Record 2: Partially paid (earnings 1000.00, paid 400.00)
        r2 = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 2),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        Payment.objects.create(
            work_record=r2,
            amount=Decimal('400.00'),
            payment_date=datetime.date(2026, 10, 2)
        )
        # Record 3: Fully paid (earnings 1000.00, paid 1000.00)
        r3 = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 3),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        Payment.objects.create(
            work_record=r3,
            amount=Decimal('1000.00'),
            payment_date=datetime.date(2026, 10, 3)
        )

        response = self.client.get(f'/api/employees/{self.employee.id}/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Total earnings = 3000.00, Total paid = 1400.00, Outstanding balance = 1600.00
        self.assertEqual(response.data['total_earnings'], "3000.00")
        self.assertEqual(response.data['total_paid'], "1400.00")
        self.assertEqual(response.data['outstanding_balance'], "1600.00")
        self.assertEqual(response.data['work_record_count'], 3)
        self.assertEqual(response.data['unpaid_record_count'], 1)
        self.assertEqual(response.data['partially_paid_record_count'], 1)
        self.assertEqual(response.data['paid_record_count'], 1)

    def test_balance_summary_no_duplicate_counting_multiple_payments(self):
        self.client.force_authenticate(user=self.admin_user)
        # Single record with multiple partial payments
        r = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 10),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        Payment.objects.create(work_record=r, amount=Decimal('200.00'), payment_date=datetime.date(2026, 10, 10))
        Payment.objects.create(work_record=r, amount=Decimal('300.00'), payment_date=datetime.date(2026, 10, 11))
        Payment.objects.create(work_record=r, amount=Decimal('100.00'), payment_date=datetime.date(2026, 10, 12))

        response = self.client.get(f'/api/employees/{self.employee.id}/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Total earnings must strictly remain 1000.00, NOT 3000.00!
        self.assertEqual(response.data['total_earnings'], "1000.00")
        self.assertEqual(response.data['total_paid'], "600.00")
        self.assertEqual(response.data['outstanding_balance'], "400.00")
        self.assertEqual(response.data['work_record_count'], 1)
        self.assertEqual(response.data['partially_paid_record_count'], 1)

    def test_balance_summary_inactive_employee(self):
        self.client.force_authenticate(user=self.admin_user)
        DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 15),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        # Deactivate
        self.employee.is_active = False
        self.employee.save()

        response = self.client.get(f'/api/employees/{self.employee.id}/balance_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])
        self.assertEqual(response.data['total_earnings'], "800.00")
        self.assertEqual(response.data['outstanding_balance'], "800.00")
        self.assertEqual(response.data['work_record_count'], 1)

    def test_employee_transactions_history_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)
        DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        response = self.client.get(f'/api/employees/{self.employee.id}/transactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['employee'], self.employee.id)

    def test_employee_applicable_wage_rate_and_basis_fields(self):
        self.client.force_authenticate(user=self.admin_user)
        GlobalWageSetting.objects.create(
            wage_amount=Decimal('750.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1)
        )
        response = self.client.get(f'/api/employees/{self.employee.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['applicable_wage_rate'], '750.00')
        self.assertEqual(response.data['applicable_wage_basis'], 'daily')

    def test_financial_summary_empty_organization(self):
        self.client.force_authenticate(user=self.admin_user)
        # Delete existing employee to test truly empty state
        Employee.objects.all().delete()
        response = self.client.get('/api/employees/financial_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_employees'], 0)
        self.assertEqual(response.data['active_employees'], 0)
        self.assertEqual(response.data['inactive_employees'], 0)
        self.assertEqual(response.data['total_earnings'], '0.00')
        self.assertEqual(response.data['total_paid'], '0.00')
        self.assertEqual(response.data['outstanding_balance'], '0.00')
        self.assertEqual(response.data['work_record_count'], 0)
        self.assertEqual(response.data['unpaid_record_count'], 0)
        self.assertEqual(response.data['partially_paid_record_count'], 0)
        self.assertEqual(response.data['paid_record_count'], 0)

    def test_financial_summary_with_records_and_payments(self):
        self.client.force_authenticate(user=self.admin_user)
        # Create second employee (inactive)
        emp2 = Employee.objects.create(name="Inactive Worker", is_active=False)

        # Record 1 on emp1: Total 1000, Paid 0 -> unpaid
        DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )

        # Record 2 on emp1: Total 1000, Paid 400 -> partially_paid
        r2 = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 2),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        Payment.objects.create(work_record=r2, amount=Decimal('400.00'), payment_date=datetime.date(2026, 10, 2))

        # Record 3 on emp2: Total 800, Paid 800 -> paid
        r3 = DailyWorkRecord.objects.create(
            employee=emp2,
            work_date=datetime.date(2026, 10, 3),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        Payment.objects.create(work_record=r3, amount=Decimal('800.00'), payment_date=datetime.date(2026, 10, 3))

        response = self.client.get('/api/employees/financial_summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_employees'], 2)
        self.assertEqual(response.data['active_employees'], 1)
        self.assertEqual(response.data['inactive_employees'], 1)
        # Total earnings = 1000 + 1000 + 800 = 2800.00
        self.assertEqual(response.data['total_earnings'], '2800.00')
        # Total paid = 400 + 800 = 1200.00
        self.assertEqual(response.data['total_paid'], '1200.00')
        # Outstanding = 2800 - 1200 = 1600.00
        self.assertEqual(response.data['outstanding_balance'], '1600.00')
        self.assertEqual(response.data['work_record_count'], 3)
        self.assertEqual(response.data['unpaid_record_count'], 1)
        self.assertEqual(response.data['partially_paid_record_count'], 1)
        self.assertEqual(response.data['paid_record_count'], 1)

    def test_dashboard_summary_alias_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)
        resp1 = self.client.get('/api/employees/financial_summary/')
        resp2 = self.client.get('/api/employees/dashboard_summary/')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

    def test_financial_summary_forbidden_for_non_staff(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get('/api/employees/financial_summary/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_employee_with_same_phone_rejected(self):
        self.client.force_authenticate(user=self.admin_user)
        # Attempt to create an employee with the same phone number as self.employee (9988776655)
        payload = {
            'name': 'Vijay Duplicate',
            'phone_number': '9988776655',
            'age': 35
        }
        response = self.client.post('/api/employees/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.data)
        self.assertIn('already exists', str(response.data['phone_number']))

    def test_different_employees_with_same_name_allowed(self):
        self.client.force_authenticate(user=self.admin_user)
        # Creating another employee with the same name "Vijay Kumar" but a different phone number must be allowed
        payload = {
            'name': 'Vijay Kumar',
            'phone_number': '9111222333',
            'age': 40
        }
        response = self.client.post('/api/employees/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Employee.objects.filter(name='Vijay Kumar').count(), 2)

    def test_update_employee_wage_does_not_create_new_profile_and_preserves_history(self):
        self.client.force_authenticate(user=self.admin_user)
        from wages.models import EmployeeWageRate
        # Initial wage rate
        r1 = EmployeeWageRate.objects.create(
            employee=self.employee,
            wage_amount=Decimal('500.00'),
            wage_basis='daily',
            effective_from=datetime.date(2026, 10, 1)
        )
        # Existing work record created under r1
        rec = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            wage_rate=Decimal('500.00'),
            wage_basis='daily',
            base_amount=Decimal('500.00'),
            total_earnings=Decimal('500.00')
        )
        emp_count_before = Employee.objects.count()

        # Update employee wage rate directly without creating new employee
        r1.effective_to = datetime.date(2026, 10, 20)
        r1.save()
        EmployeeWageRate.objects.create(
            employee=self.employee,
            wage_amount=Decimal('600.00'),
            wage_basis='hourly',
            effective_from=datetime.date(2026, 10, 21)
        )

        emp_count_after = Employee.objects.count()
        self.assertEqual(emp_count_before, emp_count_after)

        # Historical work record retains snapshot rate
        rec.refresh_from_db()
        self.assertEqual(rec.wage_rate, Decimal('500.00'))
        self.assertEqual(rec.wage_basis, 'daily')
        self.assertEqual(rec.total_earnings, Decimal('500.00'))



