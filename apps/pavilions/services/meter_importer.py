import pandas as pd
import os
import re
import tempfile
from datetime import datetime

from django.conf import settings
from django.db import transaction
from ..models import Pavilion, ElectricityMeter, ElectricityReading
from .pavilion_name_normalizer import expand_location_to_pavilion_names, find_pavilions_by_names
import logging

logger = logging.getLogger(__name__)


class MeterImporter:
    """
    Импорт счетчиков и показаний из Excel
    """

    def __init__(self, excel_file):
        """
        Инициализация импортёра

        Args:
            excel_file: загруженный Excel файл
        """
        self.excel_file = excel_file
        self.errors = []
        self.stats = {
            'sheets_processed': 0,
            'meters_created': 0,
            'meters_updated': 0,
            'readings_created': 0,
            'unmatched_pavilions': []
        }
        self.error_report_path = None
        self.error_report_url = None

    def import_data(self):
        """
        Основной метод импорта
        """
        try:
            # Создаем временный файл во временной системной директории
            temp_dir = tempfile.gettempdir()
            temp_filename = f"meters_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            temp_path = os.path.join(temp_dir, temp_filename)

            with open(temp_path, 'wb+') as f:
                for chunk in self.excel_file.chunks():
                    f.write(chunk)

            # Читаем Excel
            excel_file = pd.ExcelFile(temp_path, engine='openpyxl')

            # Ищем листы с показаниями
            reading_sheets = [sheet for sheet in excel_file.sheet_names
                            if sheet.startswith('показания')]

            if not reading_sheets:
                self.errors.append("Не найдены листы с показаниями (листы должны начинаться с 'показания')")
                return False

            # Обрабатываем каждый лист
            for sheet_name in reading_sheets:
                success = self._process_sheet(excel_file, sheet_name)
                if success:
                    self.stats['sheets_processed'] += 1

            # Удаляем временный файл
            if os.path.exists(temp_path):
                os.remove(temp_path)

            # Создаем отчет об ошибках
            if self.stats['unmatched_pavilions']:
                self._create_error_report()

            return True

        except Exception as e:
            logger.error(f"Ошибка импорта: {str(e)}")
            self.errors.append(f"Ошибка при обработке файла: {str(e)}")
            return False

    def _process_sheet(self, excel_file, sheet_name):
        """
        Обработка одного листа с показаниями
        """
        try:
            # Извлекаем дату из названия листа
            date_str = sheet_name.replace('показания', '').strip()

            # Парсим дату (поддерживаем разные форматы)
            try:
                # Пробуем разные форматы даты
                for fmt in ('%d.%m.%Y', '%d.%m.%y', '%d/%m/%Y', '%d/%m/%y'):
                    try:
                        reading_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    # Если не удалось распарсить, используем сегодняшнюю дату
                    reading_date = datetime.now().date()
                    self.errors.append(f"Не удалось распарсить дату из названия листа '{sheet_name}', использована сегодняшняя дата")
            except Exception as e:
                reading_date = datetime.now().date()
                self.errors.append(f"Ошибка парсинга даты '{sheet_name}': {str(e)}")

            # Читаем данные из листа
            df = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                dtype=str,
                na_filter=False
            )

            # Проверяем наличие необходимых колонок
            required_columns = ['№ счетчика', 'Серийник', 'Показания', 'Расположение', 'Проверено часов назад']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                self.errors.append(f"В листе '{sheet_name}' отсутствуют колонки: {', '.join(missing_columns)}")
                return False

            # Обрабатываем каждую строку
            with transaction.atomic():
                for index, row in df.iterrows():
                    self._process_row(row, reading_date)

            return True

        except Exception as e:
            logger.error(f"Ошибка обработки листа {sheet_name}: {str(e)}")
            self.errors.append(f"Ошибка в листе '{sheet_name}': {str(e)}")
            return False


    def _process_row(self, row, reading_date):
        """
        Обработка одной строки с данными счетчика
        """
        try:
            # Получаем данные из строки
            meter_number = str(row['№ счетчика']).strip()
            serial_number = str(row['Серийник']).strip()
            raw_reading = str(row['Показания']).strip()
            location_name = str(row['Расположение']).strip()
            hours_ago_str = str(row['Проверено часов назад']).strip()

            # Пропускаем пустые строки
            if not meter_number or not location_name:
                return

            # Разворачиваем в список имён и ищем павильоны
            names = expand_location_to_pavilion_names(location_name)
            pavilions = find_pavilions_by_names(names)

            if not pavilions:
                if location_name and location_name not in self.stats['unmatched_pavilions']:
                    self.stats['unmatched_pavilions'].append(location_name)
                return

            # Обрабатываем "Проверено часов назад"
            last_verified_hours_ago = None
            try:
                if hours_ago_str and hours_ago_str.isdigit():
                    last_verified_hours_ago = int(hours_ago_str)
            except Exception:
                pass

            # Получаем или создаем счетчик (M2M — павильоны задаём после)
            meter, created = ElectricityMeter.objects.get_or_create(
                meter_number=meter_number,
                defaults={
                    'serial_number': serial_number if serial_number else '',
                    'location': location_name,
                    'last_verified_hours_ago': last_verified_hours_ago
                }
            )
            meter.pavilions.set(pavilions)
            meter.serial_number = serial_number if serial_number else meter.serial_number
            meter.location = location_name
            meter.last_verified_hours_ago = last_verified_hours_ago
            meter.save()

            if created:
                self.stats['meters_created'] += 1
            else:
                self.stats['meters_updated'] += 1

            # Обрабатываем показания
            self._process_reading(meter, raw_reading, reading_date)

        except Exception as e:
            logger.error(f"Ошибка обработки строки: {str(e)}")
            self.errors.append(f"Ошибка в строке: {str(e)}")

    def _process_reading(self, meter, raw_reading, reading_date):
        """
        Обработка показаний счетчика
        """
        try:
            # Проверяем, не является ли показание сообщением об ошибке
            error_message = "Не на связи больше 168 часов"

            if error_message in raw_reading:
                # Это ошибка, не создаем показания
                self.errors.append(f"Счетчик {meter.meter_number}: {raw_reading}")
                return

            # Пытаемся преобразовать показания в число
            try:
                # Убираем все нецифровые символы, кроме точки и запятой
                cleaned_reading = re.sub(r'[^\d.,]', '', raw_reading)
                # Заменяем запятую на точку
                cleaned_reading = cleaned_reading.replace(',', '.')

                if cleaned_reading:
                    meter_reading = float(cleaned_reading)
                else:
                    # Пустые показания
                    return
            except (ValueError, TypeError):
                # Невалидные показания
                self.errors.append(f"Невалидные показания для счетчика {meter.meter_number}: {raw_reading}")
                return

            # Проверяем, есть ли уже показания на эту дату
            if ElectricityReading.objects.filter(meter=meter, date=reading_date).exists():
                # Показания уже есть, пропускаем
                return

            # Создаем показания
            ElectricityReading.objects.create(
                meter=meter,
                date=reading_date,
                meter_reading=meter_reading
            )
            self.stats['readings_created'] += 1

        except Exception as e:
            logger.error(f"Ошибка обработки показаний: {str(e)}")
            self.errors.append(f"Ошибка показаний: {str(e)}")

    def _create_error_report(self):
        """
        Создает файл с ненайденными павильонами
        """
        try:
            # Создаем отчет в виде текстового файла
            report_lines = [
                "Следующие павильоны из файла не найдены в системе:",
                "",
            ]
            for pavilion_name in self.stats['unmatched_pavilions']:
                report_lines.append(f"- {pavilion_name}")

            report_lines.append("")
            report_lines.append(f"Всего: {len(self.stats['unmatched_pavilions'])} павильонов")
            report_lines.append(f"Дата отчета: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

            report_content = "\n".join(report_lines)

            # Готовим директорию внутри MEDIA_ROOT
            media_root = getattr(settings, "MEDIA_ROOT", None)
            if not media_root:
                # На всякий случай, если MEDIA_ROOT не настроен
                media_root = settings.BASE_DIR / "media"

            errors_dir = os.path.join(media_root, "meter_import_errors")
            os.makedirs(errors_dir, exist_ok=True)

            filename = f"meters_import_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            file_path = os.path.join(errors_dir, filename)

            # Сохраняем отчет обычным файловым write
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            # Абсолютный путь на диске
            self.error_report_path = file_path

            # Относительный URL, если MEDIA_URL настроен
            media_url = getattr(settings, "MEDIA_URL", "/media/")
            # Убираем возможный BASE_DIR из пути и приводим к относительному
            self.error_report_url = f"{media_url.rstrip('/')}/meter_import_errors/{filename}"

        except Exception as e:
            logger.error(f"Ошибка создания отчета: {str(e)}")

    def get_stats(self):
        """
        Возвращает статистику импорта
        """
        return {
            'success': len(self.errors) == 0,
            'stats': self.stats,
            'errors': self.errors,
            'unmatched_count': len(self.stats['unmatched_pavilions']),
            'has_error_report': self.error_report_path is not None,
            'error_report_path': self.error_report_path,
            'error_report_url': self.error_report_url,
        }