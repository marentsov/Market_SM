import os
import tempfile
import logging
from datetime import datetime

import pandas as pd

from django.db import transaction

from ..models import Building, Pavilion, Tenant, Contract
from .pavilion_name_normalizer import find_pavilion_by_name

logger = logging.getLogger(__name__)


# Варианты названий листа (с учётом разных регистров/пробелов)
SHEET_NAMES = ['актуальные арендаторы', 'Актуальные арендаторы']
REQUIRED_COLUMNS = ['Контрагент', 'ИНН', 'Договор', 'Объект']


class ContractsImporter:
    """Импорт договоров и арендаторов из Excel."""

    def __init__(self, excel_file):
        self.excel_file = excel_file
        self.errors = []
        self.stats = {
            'tenants_created': 0,
            'tenants_updated': 0,
            'contracts_created': 0,
            'contracts_updated': 0,
            'pavilions_updated': 0,
            'unmatched_pavilions': [],
        }

    def import_data(self):
        """Основной метод импорта."""
        try:
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"contracts_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

            with open(temp_path, 'wb+') as f:
                for chunk in self.excel_file.chunks():
                    f.write(chunk)

            excel = pd.ExcelFile(temp_path, engine='openpyxl')
            sheet_name = self._find_sheet(excel)
            if not sheet_name:
                self.errors.append('Лист "актуальные арендаторы" не найден.')
                return False

            df = pd.read_excel(
                temp_path,
                sheet_name=sheet_name,
                dtype={'Контрагент': str, 'ИНН': str, 'Договор': str, 'Объект': str},
                keep_default_na=False,
                na_filter=False,
                usecols=['Контрагент', 'ИНН', 'Договор', 'Объект']
            )

            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                self.errors.append(f'Отсутствуют колонки: {", ".join(missing)}')
                return False

            with transaction.atomic():
                for _, row in df.iterrows():
                    self._process_row(row)

            if os.path.exists(temp_path):
                os.remove(temp_path)

            return True

        except Exception as e:
            logger.error(f"Ошибка импорта договоров: {e}")
            self.errors.append(f"Ошибка при обработке файла: {e}")
            return False

    def _find_sheet(self, excel):
        for name in excel.sheet_names:
            if name.strip().lower() == 'актуальные арендаторы':
                return name
        return None

    def _extract_building_code(self, contract_name):
        """
        Извлекает шифр здания из названия договора.
        Ищет паттерн 'КК/XXX' где XXX — буквы/цифры до пробела.
        Возвращает шифр или None.
        """
        import re

        match = re.search(r'(КК/[А-ЯA-Z0-9]+)', contract_name)
        return match.group(1) if match else None

    def _get_building_from_contract(self, contract_name):
        """
        Определяет здание по названию договора.
        Возвращает объект Building.
        """
        BUILDING_CODE_MAP = {
            'КК/АП': 'Славянский Стан',
            'КК/В': 'Вещевой',
            'КК/М': 'Строительный',
            'КК/МБ': 'Строительный',
        }
        DEFAULT_BUILDING_NAME = 'Основной рынок'

        code = self._extract_building_code(contract_name)

        if code and code in BUILDING_CODE_MAP:
            building_name = BUILDING_CODE_MAP[code]
        else:
            building_name = DEFAULT_BUILDING_NAME
            if code:
                self.errors.append(f'Неизвестный шифр здания: {code} в договоре "{contract_name}"')

        building, _ = Building.objects.get_or_create(
            name=building_name,
            defaults={'address': ''}
        )
        return building

    def _process_row(self, row):
        """Обработка одной строки: контрагент -> арендатор, договор, объект -> павильон."""
        tenant_name = str(row['Контрагент']).strip()
        inn = str(row.get('ИНН', '')).strip()
        contract_name = str(row['Договор']).strip()
        pavilion_name = str(row['Объект']).strip()

        if not tenant_name or not contract_name or not pavilion_name:
            return

        # 1. Определяем правильное здание по договору
        building = self._get_building_from_contract(contract_name)

        # 2. Сначала ищем в правильном здании
        pavilion = find_pavilion_by_name(pavilion_name, building=building)

        # 3. Не нашли? Ищем везде
        if not pavilion:
            pavilion = find_pavilion_by_name(pavilion_name)

            if pavilion:
                # Нашли в другом здании — записываем в errors
                old_building = pavilion.building.name
                self.errors.append(
                    f"Павильон '{pavilion_name}' перенесён из '{old_building}' "
                    f"в '{building.name}' (договор: {contract_name})"
                )
            else:
                # Совсем не нашли — unmatched
                if pavilion_name not in self.stats['unmatched_pavilions']:
                    self.stats['unmatched_pavilions'].append(pavilion_name)
                return

        # Арендатор
        tenant, created = Tenant.objects.get_or_create(
            name=tenant_name,
            defaults={'inn': inn}
        )
        if created:
            self.stats['tenants_created'] += 1
        else:
            if inn and tenant.inn != inn:
                tenant.inn = inn
                tenant.save()
                self.stats['tenants_updated'] += 1

        # Договор
        contract, created = Contract.objects.get_or_create(
            name=contract_name,
            defaults={}
        )
        if created:
            self.stats['contracts_created'] += 1

        # Привязка к павильону
        needs_update = False

        if pavilion.building_id != building.id:
            pavilion.building = building
            needs_update = True

        if pavilion.tenant_id != tenant.id:
            pavilion.tenant = tenant
            needs_update = True

        if pavilion.contract_id != contract.id:
            pavilion.contract = contract
            needs_update = True

        if pavilion.status != 'rented':
            pavilion.status = 'rented'
            needs_update = True

        if needs_update:
            pavilion.save()
            self.stats['pavilions_updated'] += 1

    def get_stats(self):
        return {
            'success': len(self.errors) == 0,
            'stats': self.stats,
            'errors': self.errors,
            'unmatched_count': len(self.stats['unmatched_pavilions']),
        }