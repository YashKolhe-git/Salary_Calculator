from django.contrib import admin
from .models import DailyWorkRecord, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ('amount', 'payment_date', 'payment_method', 'notes', 'created_at')
    readonly_fields = ('amount', 'payment_date', 'payment_method', 'notes', 'created_at')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyWorkRecord)
class DailyWorkRecordAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'employee',
        'work_date',
        'hours_worked',
        'minutes_worked',
        'wage_rate',
        'wage_basis',
        'base_amount',
        'overtime_amount',
        'extra_pay',
        'total_earnings',
    )
    list_filter = ('wage_basis', 'work_date', 'employee')
    search_fields = ('employee__name', 'notes')
    date_hierarchy = 'work_date'
    autocomplete_fields = ('employee',)
    inlines = [PaymentInline]
    ordering = ('-work_date', '-created_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'work_record',
        'get_employee',
        'amount',
        'payment_date',
        'payment_method',
        'created_at',
    )
    list_filter = ('payment_date', 'payment_method')
    search_fields = ('work_record__employee__name', 'payment_method', 'notes')
    date_hierarchy = 'payment_date'
    ordering = ('-payment_date', '-created_at')
    readonly_fields = ('work_record', 'amount', 'payment_date', 'payment_method', 'notes', 'created_at')

    @admin.display(ordering='work_record__employee__name', description='Employee')
    def get_employee(self, obj):
        return obj.work_record.employee.name

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
