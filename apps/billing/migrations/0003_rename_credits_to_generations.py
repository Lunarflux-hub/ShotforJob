import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_creditledgerentry_remove_creditledger_payment_and_more"),
    ]

    operations = [
        migrations.RenameModel(old_name="CreditPackage", new_name="GenerationPackage"),
        migrations.RenameModel(old_name="CreditLedgerEntry", new_name="GenerationLedgerEntry"),
        migrations.RenameField(
            model_name="generationpackage",
            old_name="credits",
            new_name="generations",
        ),
        migrations.AlterField(
            model_name="generationpackage",
            name="generations",
            field=models.PositiveIntegerField(help_text="Сколько генераций даёт этот пакет"),
        ),
        migrations.RenameField(
            model_name="payment",
            old_name="credits_to_grant",
            new_name="generations_granted",
        ),
        migrations.AlterField(
            model_name="generationledgerentry",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="generation_entries",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
