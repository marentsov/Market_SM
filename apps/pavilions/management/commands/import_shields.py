import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.pavilions.models import ElectricityMeter, ElectricShield


class Command(BaseCommand):
    help = 'Импорт электрощитков для счетчиков из Excel'

    def add_arguments(self, parser):
        parser.add_argument('excel_path', type=str, help='Путь к Excel файлу')

    def handle(self, *args, **options):
        excel_path = options['excel_path']

        self.stdout.write(f"Чтение файла: {excel_path}")

        try:
            # Читаем лист с щитками
            df = pd.read_excel(
                excel_path,
                sheet_name='25.02.2026 щитки',
                dtype=str,
                na_filter=False
            )

            # Проверяем наличие необходимых колонок
            if '№ счетчика' not in df.columns or 'Щиток' not in df.columns:
                self.stderr.write("Ошибка: Не найдены колонки '№ счетчика' и 'Щиток'")
                return

            stats = {
                'total': 0,
                'updated': 0,
                'skipped': 0,
                'shields_created': 0
            }

            with transaction.atomic():
                for idx, row in df.iterrows():
                    meter_number = str(row['№ счетчика']).strip()
                    shield_name = str(row['Щиток']).strip()

                    if not meter_number or not shield_name:
                        continue

                    stats['total'] += 1

                    # Пропускаем "NO BOX"
                    if shield_name.upper() == 'NO BOX':
                        stats['skipped'] += 1
                        continue

                    # Ищем счетчик
                    try:
                        meter = ElectricityMeter.objects.get(meter_number=meter_number)
                    except ElectricityMeter.DoesNotExist:
                        self.stdout.write(f"  Счетчик {meter_number} не найден")
                        stats['skipped'] += 1
                        continue

                    # Находим или создаем щиток
                    shield, created = ElectricShield.objects.get_or_create(
                        name=shield_name,
                        defaults={'description': f'Импортирован из файла {excel_path}'}
                    )

                    if created:
                        stats['shields_created'] += 1
                        self.stdout.write(f"  Создан щиток: {shield_name}")

                    # Обновляем счетчик
                    meter.electric_shield = shield
                    meter.save()
                    stats['updated'] += 1

                    self.stdout.write(f"  Счетчик {meter_number} -> щиток {shield_name}")

            # Выводим статистику
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write(self.style.SUCCESS("Импорт завершен!"))
            self.stdout.write(f"Всего обработано строк: {stats['total']}")
            self.stdout.write(f"Обновлено счетчиков: {stats['updated']}")
            self.stdout.write(f"Создано новых щитков: {stats['shields_created']}")
            self.stdout.write(f"Пропущено (NO BOX или счетчик не найден): {stats['skipped']}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Ошибка: {str(e)}"))