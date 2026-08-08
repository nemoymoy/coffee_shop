# orders/migrations/0002_add_check_constraints.py

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE orders_orderitem
                ADD CONSTRAINT chk_orderitem_weight_multiple_50
                CHECK (coffee_weight_grams IS NULL OR coffee_weight_grams % 50 = 0);
            """,
            reverse_sql="""
                ALTER TABLE orders_orderitem DROP CONSTRAINT IF EXISTS chk_orderitem_weight_multiple_50;
            """,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE orders_orderitem
                ADD CONSTRAINT chk_orderitem_brewing_required_for_ground
                CHECK (
                    (coffee_form IS NULL OR coffee_form != 'ground')
                    OR
                    (coffee_form = 'ground' AND brewing_method IS NOT NULL)
                );
            """,
            reverse_sql="""
                ALTER TABLE orders_orderitem DROP CONSTRAINT IF EXISTS chk_orderitem_brewing_required_for_ground;
            """,
        ),
    ]
