import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0008_promo_codes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="promocode",
            name="code",
            field=models.CharField(
                help_text=(
                    "Промокод, который вводит пользователь (регистр не важен). "
                    "Разрешены латиница, цифры, «-», «_»."
                ),
                max_length=32,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Промокод может содержать только латинские буквы, цифры, «-» и «_».",
                        regex="^[A-Za-z0-9_-]+$",
                    )
                ],
            ),
        ),
    ]
