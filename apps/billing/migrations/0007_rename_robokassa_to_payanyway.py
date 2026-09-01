from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_first_purchase_price"),
    ]

    operations = [
        migrations.RenameField(
            model_name="payment",
            old_name="robokassa_operation_id",
            new_name="payanyway_operation_id",
        ),
    ]
