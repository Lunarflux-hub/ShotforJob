from django.db import migrations
from django.db.models import Sum


def backfill_balances(apps, schema_editor):
    GenerationLedgerEntry = apps.get_model("billing", "GenerationLedgerEntry")
    UserBalance = apps.get_model("billing", "UserBalance")

    totals = (
        GenerationLedgerEntry.objects.values("user_id")
        .annotate(total=Sum("amount"))
    )
    UserBalance.objects.bulk_create(
        [UserBalance(user_id=row["user_id"], generations=row["total"]) for row in totals],
        ignore_conflicts=True,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_userbalance_generationledgerentry_order"),
    ]

    operations = [
        migrations.RunPython(backfill_balances, noop_reverse),
    ]
