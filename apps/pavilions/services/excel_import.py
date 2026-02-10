import pandas as pd
from io import BytesIO
from ..models import Building, Pavilion


def import_excel(file):
    """загрузка павильонов из excel"""

    # 1. Читаем файл
    df = pd.read_excel(
        file,
        sheet_name='все павильоны 1с',
        engine='openpyxl'
    )

    # 2. Берем колонку "Объект" (в Excel это колонка А)
    pavilion_names = df['Объект'].dropna().astype(str).tolist()

    # 3. Создаем одно здание для всех павильонов
    building, _ = Building.objects.get_or_create(
        name="Основной рынок",
        defaults={'address': ''}
    )

    # 4. Заносим все павильоны в базу
    created_count = 0

    for name in pavilion_names:
        # Убираем пробелы в начале и конце
        name = name.strip()

        # Пропускаем пустые строки
        if not name:
            continue

        # Проверяем, есть ли уже такой павильон
        if not Pavilion.objects.filter(building=building, name=name).exists():
            Pavilion.objects.create(
                building=building,
                name=name,
                area=45.00,  # Площадь по умолчанию
                status='free'
            )
            created_count += 1

    return len(pavilion_names), created_count