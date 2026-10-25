"""Remove Order Receipt module tables (customers, menu, orders)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("work_records", "0003_alter_dailyworkrecord_wage_basis"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS order_items CASCADE;
            DROP TABLE IF EXISTS orders CASCADE;
            DROP TABLE IF EXISTS order_number_sequence CASCADE;
            DROP TABLE IF EXISTS menu_items CASCADE;
            DROP TABLE IF EXISTS customers CASCADE;
            DROP TABLE IF EXISTS customer_code_sequence CASCADE;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            DELETE FROM django_migrations
            WHERE app IN ('customers', 'menu', 'orders');
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
