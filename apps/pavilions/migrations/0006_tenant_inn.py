# Generated manually for Tenant.inn

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pavilions', '0005_pavilion_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='inn',
            field=models.CharField(blank=True, db_index=True, max_length=20, verbose_name='ИНН'),
        ),
    ]
