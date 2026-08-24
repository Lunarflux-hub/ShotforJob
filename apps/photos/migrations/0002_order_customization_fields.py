import apps.photos.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='clothing',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='background_type',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='background_color',
            field=models.CharField(blank=True, max_length=7),
        ),
        migrations.AddField(
            model_name='order',
            name='background_image',
            field=models.ImageField(
                blank=True, null=True, upload_to=apps.photos.models.background_image_path
            ),
        ),
    ]
