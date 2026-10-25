from django.contrib import admin
from .models import EmployeeWageRate, GlobalWageSetting


@admin.register(GlobalWageSetting)
class GlobalWageSettingAdmin(admin.ModelAdmin):
    list_display = ('wage_amount', 'wage_basis', 'effective_from', 'effective_to', 'created_at')
    list_filter = ('wage_basis', 'effective_from')
    search_fields = ('wage_amount',)
    ordering = ('-effective_from', '-created_at')


@admin.register(EmployeeWageRate)
class EmployeeWageRateAdmin(admin.ModelAdmin):
    list_display = ('employee', 'wage_amount', 'wage_basis', 'effective_from', 'effective_to', 'created_at')
    list_filter = ('wage_basis', 'effective_from', 'employee')
    search_fields = ('employee__name', 'wage_amount')
    autocomplete_fields = ('employee',)
    ordering = ('-effective_from', '-created_at')
