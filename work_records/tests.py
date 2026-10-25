import datetime
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.admin.sites import AdminSite
from django.db.models import ProtectedError
from employees.models import Employee
from wages.models import EmployeeWageRate, GlobalWageSetting, WageBasis
from .admin import PaymentAdmin, PaymentInline
from .models import DailyWorkRecord, Payment
from .services import (
    calculate_work_record_earnings,
    compute_payment_summary,
    process_work_record_payment,
)


class WorkRecordAndPaymentModelTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(name="Deepak Verma", is_active=True)

    def test_create_daily_work_record(self):
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            hours_worked=8,
            minutes_worked=30,
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            base_amount=Decimal('800.00'),
            overtime_minutes=60,
            overtime_amount=Decimal('100.00'),
            extra_pay=Decimal('50.00'),
            total_earnings=Decimal('950.00'),
            notes="Completed foundation work"
        )
        self.assertEqual(record.total_earnings, Decimal('950.00'))
        self.assertEqual(record.hours_worked, 8)
        self.assertEqual(record.minutes_worked, 30)
        self.assertIn("Deepak Verma", str(record))

    def test_unique_employee_per_work_date_constraint(self):
        work_date = datetime.date(2026, 10, 2)
        DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=work_date,
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        with self.assertRaises(IntegrityError):
            DailyWorkRecord.objects.create(
                employee=self.employee,
                work_date=work_date,
                wage_rate=Decimal('850.00'),
                wage_basis=WageBasis.DAILY,
                base_amount=Decimal('850.00'),
                total_earnings=Decimal('850.00')
            )

    def test_historical_wage_snapshot_preservation(self):
        wage_rate = EmployeeWageRate.objects.create(
            employee=self.employee,
            wage_amount=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 10, 1)
        )
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 1),
            wage_rate=wage_rate.wage_amount,
            wage_basis=wage_rate.wage_basis,
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        wage_rate.wage_amount = Decimal('900.00')
        wage_rate.save()

        record.refresh_from_db()
        self.assertEqual(record.wage_rate, Decimal('800.00'))
        self.assertEqual(record.total_earnings, Decimal('800.00'))

    def test_multiple_payments_for_work_record(self):
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 5),
            wage_rate=Decimal('1000.00'),
            wage_basis=WageBasis.DAILY,
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        p1 = Payment.objects.create(
            work_record=record,
            amount=Decimal('400.00'),
            payment_date=datetime.date(2026, 10, 5),
            payment_method='Cash'
        )
        p2 = Payment.objects.create(
            work_record=record,
            amount=Decimal('600.00'),
            payment_date=datetime.date(2026, 10, 6),
            payment_method='UPI'
        )
        self.assertEqual(record.payments.count(), 2)
        total_paid = sum(p.amount for p in record.payments.all())
        self.assertEqual(total_paid, Decimal('1000.00'))
        self.assertIn("Payment #", str(p1))

    def test_invalid_hours_worked(self):
        record = DailyWorkRecord(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 7),
            hours_worked=25,
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        with self.assertRaises(ValidationError):
            record.full_clean()


class EarningsCalculationTests(TestCase):
    def test_daily_wage_standard_hours(self):
        # 8 hours on 800 daily wage without manual input -> defaults to 800.00
        calc = calculate_work_record_earnings(
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            hours_worked=8,
            extra_pay=Decimal('0.00')
        )
        self.assertEqual(calc['base_amount'], Decimal('800.00'))
        self.assertEqual(calc['overtime_amount'], Decimal('0.00'))
        self.assertEqual(calc['total_earnings'], Decimal('800.00'))

    def test_daily_wage_half_day_not_prorated(self):
        # 4 hours on 800 daily wage is NOT prorated -> remains 800.00
        calc = calculate_work_record_earnings(
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            hours_worked=4,
            extra_pay=Decimal('0.00')
        )
        self.assertEqual(calc['base_amount'], Decimal('800.00'))
        self.assertEqual(calc['total_earnings'], Decimal('800.00'))

    def test_daily_wage_manual_earnings_entry(self):
        # Admin manually enters actual earnings of 850.00 for the day
        calc = calculate_work_record_earnings(
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            hours_worked=6,
            manual_base_amount=Decimal('850.00'),
            extra_pay=Decimal('0.00')
        )
        self.assertEqual(calc['base_amount'], Decimal('850.00'))
        self.assertEqual(calc['total_earnings'], Decimal('850.00'))

    def test_daily_wage_with_extra_pay(self):
        # 8 hours + 50 extra pay
        calc = calculate_work_record_earnings(
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            hours_worked=8,
            extra_pay=Decimal('50.00')
        )
        self.assertEqual(calc['base_amount'], Decimal('800.00'))
        self.assertEqual(calc['overtime_amount'], Decimal('0.00'))
        self.assertEqual(calc['extra_pay'], Decimal('50.00'))
        self.assertEqual(calc['total_earnings'], Decimal('850.00'))

    def test_hourly_wage_calculation(self):
        # 7 whole hours at 100/hr + 20 extra pay -> 700 + 20 = 720.00
        calc = calculate_work_record_earnings(
            wage_rate=Decimal('100.00'),
            wage_basis=WageBasis.HOURLY,
            hours_worked=7,
            extra_pay=Decimal('20.00')
        )
        self.assertEqual(calc['base_amount'], Decimal('700.00'))
        self.assertEqual(calc['overtime_amount'], Decimal('0.00'))
        self.assertEqual(calc['total_earnings'], Decimal('720.00'))

    def test_payment_summary_statuses(self):
        # Not paid
        summary = compute_payment_summary(Decimal('1000.00'), Decimal('0.00'))
        self.assertEqual(summary['payment_status'], 'not_paid')
        self.assertEqual(summary['balance_due'], Decimal('1000.00'))

        # Partially paid
        summary = compute_payment_summary(Decimal('1000.00'), Decimal('400.00'))
        self.assertEqual(summary['payment_status'], 'partially_paid')
        self.assertEqual(summary['balance_due'], Decimal('600.00'))

        # Fully paid
        summary = compute_payment_summary(Decimal('1000.00'), Decimal('1000.00'))
        self.assertEqual(summary['payment_status'], 'paid')
        self.assertEqual(summary['balance_due'], Decimal('0.00'))

        # Zero earnings -> paid
        summary = compute_payment_summary(Decimal('0.00'), Decimal('0.00'))
        self.assertEqual(summary['payment_status'], 'paid')
        self.assertEqual(summary['balance_due'], Decimal('0.00'))


class WorkRecordAndPaymentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username='admin',
            password='adminpassword123',
            is_staff=True,
            is_superuser=True
        )
        self.employee = Employee.objects.create(name="Deepak Verma", is_active=True)
        # Global wage: 800 daily
        self.global_wage = GlobalWageSetting.objects.create(
            wage_amount=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 1, 1)
        )

    def test_unauthenticated_work_records_denied(self):
        response = self.client.get('/api/work-records/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_create_work_record_with_automatic_earnings(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'employee': self.employee.id,
            'work_date': '2026-10-01',
            'hours_worked': 8,
            'minutes_worked': 0,
            'extra_pay': '50.00',
            'notes': 'Excavation day 1'
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['wage_rate'], '800.00')
        self.assertEqual(response.data['wage_basis'], 'daily')
        self.assertEqual(response.data['base_amount'], '800.00')
        self.assertEqual(response.data['overtime_amount'], '0.00')
        self.assertEqual(response.data['extra_pay'], '50.00')
        self.assertEqual(response.data['total_earnings'], '850.00')
        self.assertEqual(response.data['total_paid'], '0.00')
        self.assertEqual(response.data['balance_due'], '850.00')
        self.assertEqual(response.data['payment_status'], 'not_paid')

    def test_create_daily_work_record_with_manual_earnings(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'employee': self.employee.id,
            'work_date': '2026-10-02',
            'hours_worked': 7,
            'base_amount': '950.00',
            'extra_pay': '25.00'
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['wage_rate'], '800.00')  # Reference snapshot preserved
        self.assertEqual(response.data['base_amount'], '950.00')  # Manual entry accepted
        self.assertEqual(response.data['extra_pay'], '25.00')
        self.assertEqual(response.data['total_earnings'], '975.00')

    def test_create_hourly_work_record_whole_hours(self):
        self.client.force_authenticate(user=self.admin_user)
        hourly_emp = Employee.objects.create(name="Hourly Worker")
        EmployeeWageRate.objects.create(
            employee=hourly_emp,
            wage_amount=Decimal('150.00'),
            wage_basis=WageBasis.HOURLY,
            effective_from=datetime.date(2026, 1, 1)
        )
        payload = {
            'employee': hourly_emp.id,
            'work_date': '2026-10-02',
            'hours_worked': 6,
            'extra_pay': '30.00'
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # 6 hours * 150 = 900 base, 900 + 30 = 930 total
        self.assertEqual(response.data['wage_rate'], '150.00')
        self.assertEqual(response.data['wage_basis'], 'hourly')
        self.assertEqual(response.data['base_amount'], '900.00')
        self.assertEqual(response.data['extra_pay'], '30.00')
        self.assertEqual(response.data['total_earnings'], '930.00')

    def test_allow_minutes_in_work_record(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'employee': self.employee.id,
            'work_date': '2026-10-03',
            'hours_worked': 8,
            'minutes_worked': 30
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['minutes_worked'], 30)

    def test_reject_work_record_for_inactive_employee(self):
        self.client.force_authenticate(user=self.admin_user)
        self.employee.is_active = False
        self.employee.save()

        payload = {
            'employee': self.employee.id,
            'work_date': '2026-10-02',
            'hours_worked': 8,
            'minutes_worked': 0
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_duplicate_work_record_same_employee_and_date(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'employee': self.employee.id,
            'work_date': '2026-10-03',
            'hours_worked': 8,
            'minutes_worked': 0
        }
        r1 = self.client.post('/api/work-records/', payload)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        # Duplicate attempt
        r2 = self.client.post('/api/work-records/', payload)
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_client_cannot_spoof_wage_rate(self):
        self.client.force_authenticate(user=self.admin_user)
        # Attempt to spoof wage_rate
        payload = {
            'employee': self.employee.id,
            'work_date': '2026-10-04',
            'hours_worked': 8,
            'wage_rate': '9999.00',
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Server must use resolved wage rate 800.00, not spoofed 9999.00
        self.assertEqual(response.data['wage_rate'], '800.00')

    def test_update_work_record_preserves_wage_snapshot_and_recomputes_earnings(self):
        self.client.force_authenticate(user=self.admin_user)
        # 1. Create record with rate 800
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 5),
            hours_worked=8,
            minutes_worked=0,
            wage_rate=Decimal('800.00'),
            wage_basis=WageBasis.DAILY,
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        # 2. Later, global wage rate changes to 1200
        self.global_wage.wage_amount = Decimal('1200.00')
        self.global_wage.save()

        # 3. Client updates hours worked to 4
        response = self.client.patch(f'/api/work-records/{record.id}/', {'hours_worked': 4})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        record.refresh_from_db()
        # Rate snapshot must remain 800.00 (NOT updated to 1200.00)
        self.assertEqual(record.wage_rate, Decimal('800.00'))
        # Daily earnings are not prorated by hours worked, so base_amount remains 800.00
        self.assertEqual(record.base_amount, Decimal('800.00'))
        self.assertEqual(record.total_earnings, Decimal('800.00'))

        # 4. Client updates manual daily base_amount to 500.00
        patch_resp = self.client.patch(f'/api/work-records/{record.id}/', {'base_amount': '500.00'})
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.base_amount, Decimal('500.00'))
        self.assertEqual(record.total_earnings, Decimal('500.00'))
        self.assertEqual(record.wage_rate, Decimal('800.00'))

    def test_filter_work_records(self):
        self.client.force_authenticate(user=self.admin_user)
        emp2 = Employee.objects.create(name="Second Worker")
        DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 10),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        DailyWorkRecord.objects.create(
            employee=emp2,
            work_date=datetime.date(2026, 10, 15),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )

        # Filter by employee
        resp = self.client.get(f'/api/work-records/?employee={self.employee.id}')
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertEqual(len(results), 1)

        # Filter by date range
        resp = self.client.get('/api/work-records/?start_date=2026-10-12&end_date=2026-10-20')
        results = resp.data['results'] if 'results' in resp.data else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['employee'], emp2.id)

    def test_payments_and_status_transitions(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 20),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )

        # 1. Check initial status: not_paid
        resp = self.client.get(f'/api/work-records/{record.id}/')
        self.assertEqual(resp.data['payment_status'], 'not_paid')
        self.assertEqual(resp.data['total_paid'], '0.00')
        self.assertEqual(resp.data['balance_due'], '1000.00')

        # 2. Record partial payment: 400
        pay_payload = {
            'work_record': record.id,
            'amount': '400.00',
            'payment_date': '2026-10-20',
            'payment_method': 'Cash'
        }
        pay_resp = self.client.post('/api/payments/', pay_payload)
        self.assertEqual(pay_resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.get(f'/api/work-records/{record.id}/')
        self.assertEqual(resp.data['payment_status'], 'partially_paid')
        self.assertEqual(resp.data['total_paid'], '400.00')
        self.assertEqual(resp.data['balance_due'], '600.00')

        # 3. Reject overpayment (e.g. 700 when balance is 600)
        overpay_payload = {
            'work_record': record.id,
            'amount': '700.00',
            'payment_date': '2026-10-21'
        }
        overpay_resp = self.client.post('/api/payments/', overpay_payload)
        self.assertEqual(overpay_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Final payment of remaining balance: 600
        final_pay = {
            'work_record': record.id,
            'amount': '600.00',
            'payment_date': '2026-10-21',
            'payment_method': 'UPI'
        }
        final_resp = self.client.post('/api/payments/', final_pay)
        self.assertEqual(final_resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.get(f'/api/work-records/{record.id}/')
        self.assertEqual(resp.data['payment_status'], 'paid')
        self.assertEqual(resp.data['total_paid'], '1000.00')
        self.assertEqual(resp.data['balance_due'], '0.00')

        # 5. Nested payments endpoint
        payments_resp = self.client.get(f'/api/work-records/{record.id}/payments/')
        self.assertEqual(payments_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(payments_resp.data), 2)

    def test_reject_zero_or_negative_payment(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 22),
            wage_rate=Decimal('500.00'),
            wage_basis='daily',
            base_amount=Decimal('500.00'),
            total_earnings=Decimal('500.00')
        )
        response = self.client.post('/api/payments/', {
            'work_record': record.id,
            'amount': '0.00',
            'payment_date': '2026-10-22'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_payment_physical_deletion(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 23),
            wage_rate=Decimal('500.00'),
            wage_basis='daily',
            base_amount=Decimal('500.00'),
            total_earnings=Decimal('500.00')
        )
        payment = Payment.objects.create(
            work_record=record,
            amount=Decimal('200.00'),
            payment_date=datetime.date(2026, 10, 23)
        )
        response = self.client.delete(f'/api/payments/{payment.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Payment.objects.filter(id=payment.id).exists())

    def test_reject_work_record_delete_with_payments(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 24),
            wage_rate=Decimal('500.00'),
            wage_basis='daily',
            base_amount=Decimal('500.00'),
            total_earnings=Decimal('500.00')
        )
        Payment.objects.create(
            work_record=record,
            amount=Decimal('200.00'),
            payment_date=datetime.date(2026, 10, 24)
        )
        response = self.client.delete(f'/api/work-records/{record.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(DailyWorkRecord.objects.filter(id=record.id).exists())

    def test_work_record_delete_database_protected_error(self):
        # Database level check: deleting a work record with payments raises ProtectedError
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 25),
            wage_rate=Decimal('500.00'),
            wage_basis='daily',
            base_amount=Decimal('500.00'),
            total_earnings=Decimal('500.00')
        )
        Payment.objects.create(
            work_record=record,
            amount=Decimal('200.00'),
            payment_date=datetime.date(2026, 10, 25)
        )
        with self.assertRaises(ProtectedError):
            record.delete()

    def test_django_admin_payment_history_protections(self):
        # Admin interface must protect payment history from ordinary editing or deletion
        site = AdminSite()
        payment_admin = PaymentAdmin(Payment, site)
        payment_inline = PaymentInline(DailyWorkRecord, site)

        self.assertFalse(payment_admin.has_delete_permission(None))
        self.assertFalse(payment_admin.has_change_permission(None))
        self.assertFalse(payment_inline.has_delete_permission(None))
        self.assertFalse(payment_inline.has_change_permission(None))

    def test_editing_unpaid_work_record(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 26),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        # Edit notes and extra pay on unpaid record
        response = self.client.patch(f'/api/work-records/{record.id}/', {
            'extra_pay': '100.00',
            'notes': 'Overtime work'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.extra_pay, Decimal('100.00'))
        self.assertEqual(record.total_earnings, Decimal('900.00'))
        self.assertEqual(record.notes, 'Overtime work')

    def test_editing_partially_paid_work_record(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 27),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        Payment.objects.create(
            work_record=record,
            amount=Decimal('400.00'),
            payment_date=datetime.date(2026, 10, 27)
        )
        # Permitted edit: reduce base_amount to 600.00 (which is >= 400.00 already paid)
        response = self.client.patch(f'/api/work-records/{record.id}/', {
            'base_amount': '600.00'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.base_amount, Decimal('600.00'))
        self.assertEqual(record.total_earnings, Decimal('600.00'))

    def test_reject_earnings_reduction_below_already_paid(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 28),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        Payment.objects.create(
            work_record=record,
            amount=Decimal('600.00'),
            payment_date=datetime.date(2026, 10, 28)
        )
        # Attempt to reduce base_amount to 400.00 (below 600.00 already paid)
        response = self.client.patch(f'/api/work-records/{record.id}/', {
            'base_amount': '400.00'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be lower than the amount already paid', response.data['detail'])

    def test_preserving_payments_during_earnings_corrections(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 29),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        p1 = Payment.objects.create(
            work_record=record,
            amount=Decimal('300.00'),
            payment_date=datetime.date(2026, 10, 29),
            payment_method='Cash'
        )
        p2 = Payment.objects.create(
            work_record=record,
            amount=Decimal('200.00'),
            payment_date=datetime.date(2026, 10, 30),
            payment_method='UPI'
        )

        # Update notes and extra pay
        response = self.client.patch(f'/api/work-records/{record.id}/', {
            'extra_pay': '150.00',
            'notes': 'Bonus added'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Ensure payment records remain unchanged
        self.assertEqual(record.payments.count(), 2)
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.amount, Decimal('300.00'))
        self.assertEqual(p2.amount, Decimal('200.00'))

    def test_inactive_employee_allows_historical_corrections(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 30),
            hours_worked=8,
            wage_rate=Decimal('800.00'),
            wage_basis='daily',
            base_amount=Decimal('800.00'),
            total_earnings=Decimal('800.00')
        )
        # Deactivate employee
        self.employee.is_active = False
        self.employee.save()

        # Admin corrects notes on inactive employee's historical record -> should succeed!
        response = self.client.patch(f'/api/work-records/{record.id}/', {
            'notes': 'Corrected notes for inactive employee'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.notes, 'Corrected notes for inactive employee')

    def test_inactive_employee_allows_payments_against_outstanding_balances(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 10, 31),
            hours_worked=8,
            wage_rate=Decimal('1000.00'),
            wage_basis='daily',
            base_amount=Decimal('1000.00'),
            total_earnings=Decimal('1000.00')
        )
        # Deactivate employee
        self.employee.is_active = False
        self.employee.save()

        # Admin disburses payment to inactive employee against outstanding balance
        pay_payload = {
            'work_record': record.id,
            'amount': '500.00',
            'payment_date': '2026-11-01',
            'payment_method': 'Bank Transfer'
        }
        response = self.client.post('/api/payments/', pay_payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount'], '500.00')

        # Check updated status on work record
        record_resp = self.client.get(f'/api/work-records/{record.id}/')
        self.assertEqual(record_resp.data['total_paid'], '500.00')
        self.assertEqual(record_resp.data['balance_due'], '500.00')
        self.assertEqual(record_resp.data['payment_status'], 'partially_paid')

    def test_inactive_employee_prevents_new_work_records(self):
        self.client.force_authenticate(user=self.admin_user)
        self.employee.is_active = False
        self.employee.save()

        payload = {
            'employee': self.employee.id,
            'work_date': '2026-11-05',
            'hours_worked': 8,
            'minutes_worked': 0,
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('is inactive. Cannot create new work records', str(response.data))

    def test_transaction_consistency_on_failed_payment(self):
        self.client.force_authenticate(user=self.admin_user)
        record = DailyWorkRecord.objects.create(
            employee=self.employee,
            work_date=datetime.date(2026, 11, 2),
            hours_worked=8,
            wage_rate=Decimal('500.00'),
            wage_basis='daily',
            base_amount=Decimal('500.00'),
            total_earnings=Decimal('500.00')
        )
        # Attempt overpayment
        response = self.client.post('/api/payments/', {
            'work_record': record.id,
            'amount': '600.00',
            'payment_date': '2026-11-02'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # No payment row created
        self.assertEqual(Payment.objects.filter(work_record=record).count(), 0)

    def test_monthly_work_record_calculation_service(self):
        # 1. Agreed monthly reference rate 30000.00, manual base 1250.00, extra pay 150.00
        calc = calculate_work_record_earnings(
            wage_rate=Decimal('30000.00'),
            wage_basis=WageBasis.MONTHLY,
            hours_worked=8,
            manual_base_amount=Decimal('1250.00'),
            extra_pay=Decimal('150.00')
        )
        # Total earnings = manual regular earnings + extra pay
        self.assertEqual(calc['base_amount'], Decimal('1250.00'))
        self.assertEqual(calc['overtime_amount'], Decimal('0.00'))
        self.assertEqual(calc['extra_pay'], Decimal('150.00'))
        self.assertEqual(calc['total_earnings'], Decimal('1400.00'))
        # Must strictly NOT be 30000 / 30 = 1000 + 150
        self.assertNotEqual(calc['total_earnings'], Decimal('1150.00'))

        # 2. Missing manual base amount for monthly raises ValidationError
        with self.assertRaises(ValidationError):
            calculate_work_record_earnings(
                wage_rate=Decimal('30000.00'),
                wage_basis=WageBasis.MONTHLY,
                hours_worked=8,
                manual_base_amount=None
            )

    def test_create_monthly_work_record_api(self):
        self.client.force_authenticate(user=self.admin_user)
        # Setup monthly employee
        monthly_emp = Employee.objects.create(name="Anita Sharma", is_active=True)
        EmployeeWageRate.objects.create(
            employee=monthly_emp,
            wage_amount=Decimal('36000.00'),
            wage_basis=WageBasis.MONTHLY,
            effective_from=datetime.date(2026, 1, 1)
        )

        # 1. Reject if base_amount is missing
        fail_payload = {
            'employee': monthly_emp.id,
            'work_date': '2026-10-15',
            'hours_worked': 8
        }
        fail_resp = self.client.post('/api/work-records/', fail_payload)
        self.assertEqual(fail_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('base_amount', fail_resp.data)

        # 2. Success with manual regular earnings
        payload = {
            'employee': monthly_emp.id,
            'work_date': '2026-10-15',
            'hours_worked': 8,
            'base_amount': '1500.00',
            'extra_pay': '200.00',
            'notes': 'Monthly staff regular shift'
        }
        response = self.client.post('/api/work-records/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['wage_basis'], 'monthly')
        self.assertEqual(response.data['wage_rate'], '36000.00')
        self.assertEqual(response.data['base_amount'], '1500.00')
        self.assertEqual(response.data['extra_pay'], '200.00')
        self.assertEqual(response.data['total_earnings'], '1700.00')
        self.assertEqual(response.data['balance_due'], '1700.00')
        self.assertEqual(response.data['payment_status'], 'not_paid')

    def test_update_and_pay_monthly_work_record(self):
        self.client.force_authenticate(user=self.admin_user)
        monthly_emp = Employee.objects.create(name="Rohit Gaikwad", is_active=True)
        record = DailyWorkRecord.objects.create(
            employee=monthly_emp,
            work_date=datetime.date(2026, 10, 16),
            hours_worked=8,
            wage_rate=Decimal('40000.00'),
            wage_basis=WageBasis.MONTHLY,
            base_amount=Decimal('1600.00'),
            total_earnings=Decimal('1600.00')
        )

        # Disburse partial payment of 600.00
        pay_resp = self.client.post('/api/payments/', {
            'work_record': record.id,
            'amount': '600.00',
            'payment_date': '2026-10-16',
            'payment_method': 'Cash'
        })
        self.assertEqual(pay_resp.status_code, status.HTTP_201_CREATED)

        # Verify balance
        rec_resp = self.client.get(f'/api/work-records/{record.id}/')
        self.assertEqual(rec_resp.data['total_paid'], '600.00')
        self.assertEqual(rec_resp.data['balance_due'], '1000.00')
        self.assertEqual(rec_resp.data['payment_status'], 'partially_paid')

        # Permitted edit: update base_amount to 1200.00 (which is >= 600.00 already paid)
        patch_resp = self.client.patch(f'/api/work-records/{record.id}/', {
            'base_amount': '1200.00'
        })
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.base_amount, Decimal('1200.00'))
        self.assertEqual(record.total_earnings, Decimal('1200.00'))
        self.assertEqual(record.wage_basis, 'monthly')

        # Prohibited edit: reduce base_amount below 600.00
        fail_patch = self.client.patch(f'/api/work-records/{record.id}/', {
            'base_amount': '500.00'
        })
        self.assertEqual(fail_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be lower than the amount already paid', fail_patch.data['detail'])

    def test_hourly_employee_whole_hours(self):
        self.client.force_authenticate(user=self.admin_user)
        hourly_emp = Employee.objects.create(name="Anil Shinde", is_active=True)
        EmployeeWageRate.objects.create(
            employee=hourly_emp,
            wage_amount=Decimal('150.00'),
            wage_basis=WageBasis.HOURLY,
            effective_from=datetime.date(2026, 10, 1)
        )
        payload = {
            'employee': hourly_emp.id,
            'work_date': '2026-10-18',
            'hours_worked': 8,
            'minutes_worked': 0,
            'extra_pay': '50.00'
        }
        resp = self.client.post('/api/work-records/', payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['base_amount'], '1200.00')
        self.assertEqual(resp.data['extra_pay'], '50.00')
        self.assertEqual(resp.data['total_earnings'], '1250.00')

    def test_hourly_employee_fractional_time_7h_30m(self):
        self.client.force_authenticate(user=self.admin_user)
        hourly_emp = Employee.objects.create(name="Ganesh Kadam", is_active=True)
        EmployeeWageRate.objects.create(
            employee=hourly_emp,
            wage_amount=Decimal('150.00'),
            wage_basis=WageBasis.HOURLY,
            effective_from=datetime.date(2026, 10, 1)
        )
        # 7 hours 30 minutes at ₹150/hr = ₹1,125 regular + ₹100 extra pay = ₹1,225 total
        payload = {
            'employee': hourly_emp.id,
            'work_date': '2026-10-19',
            'hours_worked': 7,
            'minutes_worked': 30,
            'extra_pay': '100.00'
        }
        resp = self.client.post('/api/work-records/', payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['base_amount'], '1125.00')
        self.assertEqual(resp.data['extra_pay'], '100.00')
        self.assertEqual(resp.data['total_earnings'], '1225.00')

    def test_hourly_employee_invalid_minutes_rejected(self):
        self.client.force_authenticate(user=self.admin_user)
        hourly_emp = Employee.objects.create(name="Sunil More", is_active=True)
        EmployeeWageRate.objects.create(
            employee=hourly_emp,
            wage_amount=Decimal('150.00'),
            wage_basis=WageBasis.HOURLY,
            effective_from=datetime.date(2026, 10, 1)
        )
        # 60 minutes is invalid (must be 0-59)
        payload = {
            'employee': hourly_emp.id,
            'work_date': '2026-10-20',
            'hours_worked': 7,
            'minutes_worked': 60,
        }
        resp = self.client.post('/api/work-records/', payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('minutes_worked', resp.data)

    def test_daily_employee_without_hours_minutes(self):
        self.client.force_authenticate(user=self.admin_user)
        daily_emp = Employee.objects.create(name="Vijay Daily", is_active=True)
        EmployeeWageRate.objects.create(
            employee=daily_emp,
            wage_amount=Decimal('600.00'),
            wage_basis=WageBasis.DAILY,
            effective_from=datetime.date(2026, 10, 1)
        )
        # Daily worker with manually entered regular earnings and extra pay, without hours/minutes
        payload = {
            'employee': daily_emp.id,
            'work_date': '2026-10-21',
            'base_amount': '650.00',
            'extra_pay': '75.00'
        }
        resp = self.client.post('/api/work-records/', payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['base_amount'], '650.00')
        self.assertEqual(resp.data['extra_pay'], '75.00')
        self.assertEqual(resp.data['total_earnings'], '725.00')
        self.assertEqual(resp.data['hours_worked'], 0)
        self.assertEqual(resp.data['minutes_worked'], 0)

    def test_monthly_employee_without_hours_minutes_and_never_divided_by_30(self):
        self.client.force_authenticate(user=self.admin_user)
        monthly_emp = Employee.objects.create(name="Ajay Monthly", is_active=True)
        EmployeeWageRate.objects.create(
            employee=monthly_emp,
            wage_amount=Decimal('30000.00'),
            wage_basis=WageBasis.MONTHLY,
            effective_from=datetime.date(2026, 10, 1)
        )
        # Monthly earnings must be entered manually and NEVER divided by 30 (not 1000.00)
        payload = {
            'employee': monthly_emp.id,
            'work_date': '2026-10-22',
            'base_amount': '1350.00',
            'extra_pay': '150.00'
        }
        resp = self.client.post('/api/work-records/', payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['base_amount'], '1350.00')
        self.assertEqual(resp.data['extra_pay'], '150.00')
        self.assertEqual(resp.data['total_earnings'], '1500.00')
        self.assertNotEqual(resp.data['base_amount'], '1000.00')
        self.assertEqual(resp.data['hours_worked'], 0)
        self.assertEqual(resp.data['minutes_worked'], 0)


