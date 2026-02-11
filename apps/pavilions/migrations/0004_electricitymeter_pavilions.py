# Generated manually for pavilion -> pavilions M2M

from django.db import migrations, models


def copy_pavilion_to_pavilions(apps, schema_editor):
    """Копируем старый FK pavilion в новый M2M pavilions."""
    ElectricityMeter = apps.get_model('pavilions', 'ElectricityMeter')
    for meter in ElectricityMeter.objects.select_related('pavilion').all():
        if meter.pavilion_id:
            meter.pavilions.add(meter.pavilion_id)


def reverse_pavilions_to_pavilion(apps, schema_editor):
    """Откат: берём первый павильон из M2M и пишем в старый FK."""
    ElectricityMeter = apps.get_model('pavilions', 'ElectricityMeter')
    for meter in ElectricityMeter.objects.prefetch_related('pavilions').all():
        first = meter.pavilions.first()
        if first:
            meter.pavilion_id = first.id
            meter.save()


class Migration(migrations.Migration):

    dependencies = [
        ('pavilions', '0003_remove_pavilion_electricity_meter_number_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='electricitymeter',
            name='pavilions',
            field=models.ManyToManyField(
                blank=True,
                help_text='Павильоны, которые обслуживает этот счетчик',
                related_name='electricity_meters',
                to='pavilions.pavilion',
                verbose_name='Павильоны'
            ),
        ),
        migrations.RunPython(copy_pavilion_to_pavilions, reverse_pavilions_to_pavilion),
        migrations.RemoveField(
            model_name='electricitymeter',
            name='pavilion',
        ),
        migrations.AlterModelOptions(
            name='electricitymeter',
            options={'ordering': ['meter_number'], 'verbose_name': 'Счетчик электроэнергии', 'verbose_name_plural': 'Счетчики электроэнергии'},
        ),
    ]
