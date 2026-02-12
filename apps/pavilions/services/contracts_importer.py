"""
Импорт договоров и арендаторов из Excel.
Лист "актуальные арендаторы": Контрагент, ИНН, Договор, Объект.
"""
import os
import tempfile
import logging
from datetime import datetime

import pandas as pd

from django.db import transaction

from ..models import Building, Pavilion, Tenant, Contract

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

            df = pd.read_excel(excel, sheet_name=sheet_name, dtype=str, na_filter=False)

            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                self.errors.append(f'Отсутствуют колонки: {", ".join(missing)}')
                return False

            building = self._get_building()

            with transaction.atomic():
                for _, row in df.iterrows():
                    self._process_row(row, building)

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

    def _get_building(self):
        building, _ = Building.objects.get_or_create(
            name="Основной рынок",
            defaults={'address': ''}
        )
        return building

    def _process_row(self, row, building):
        """Обработка одной строки: контрагент -> арендатор, договор, объект -> павильон."""
        tenant_name = str(row['Контрагент']).strip()
        inn = str(row.get('ИНН', '')).strip()
        contract_name = str(row['Договор']).strip()
        pavilion_name = str(row['Объект']).strip()

        if not tenant_name or not contract_name or not pavilion_name:
            return

        # Павильон
        pavilion = Pavilion.objects.filter(building=building, name=pavilion_name).first()
        if not pavilion:
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
            if inn:
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
        if pavilion.tenant_id != tenant.id or pavilion.contract_id != contract.id:
            pavilion.tenant = tenant
            pavilion.contract = contract
            pavilion.status = 'rented'
            pavilion.save()
            self.stats['pavilions_updated'] += 1

    def get_stats(self):
        return {
            'success': len(self.errors) == 0,
            'stats': self.stats,
            'errors': self.errors,
            'unmatched_count': len(self.stats['unmatched_pavilions']),
        }
