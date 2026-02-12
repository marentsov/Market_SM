"""
Модуль для нормализации названий павильонов и поиска их в БД.
Используется при импорте счётчиков, договоров и других операциях.
"""
import re

from ..models import Pavilion


def normalize_single_name(name):
    """
    Нормализует одно название павильона:
    - Убирает скобки и доп. инфо: 'Г21/1 (2 этаж)' -> 'Г21/1'
    - Убирает суффикс типа 5квт: 'Е11/1 5квт' -> 'Е11/1'
    
    Args:
        name: Строка с названием павильона
        
    Returns:
        Нормализованное название
    """
    base = name.strip()
    
    # Скобки: Г21/1 (2 этаж) -> Г21/1
    if ' (' in base:
        base = base.split(' (')[0].strip()
    
    # Пробел + суффикс (5квт и т.п.): Е11/1 5квт -> Е11/1
    # Отсекаем только если часть до пробела заканчивается цифрой (полный номер)
    if ' ' in base:
        before_space = base.split(' ', 1)[0]
        if before_space and before_space[-1].isdigit():
            base = before_space
    
    return base


def expand_location_to_pavilion_names(location_name):
    """
    Разворачивает строку расположения в список имён павильонов.
    
    Примеры:
    - 'Общий Г11/1, Г10/111/6 (+)' -> ['Г11/1'] (берём только первый)
    - 'Общий В18/5, В18/519/7' -> ['В18/5']
    - 'Е10/1,2' -> ['Е10/1', 'Е10/2'] (один счётчик на несколько павильонов)
    - 'Е11/5,6' -> ['Е11/5', 'Е11/6']
    - 'Г9/1, Д10/1, Д12/1' -> ['Г9/1', 'Д10/1', 'Д12/1'] (разные префиксы)
    - 'Е11/1 5квт' -> ['Е11/1']
    - 'Пассаж 61' -> ['Пассаж 61', 'Пассаж61'] (с пробелом и без)
    
    Args:
        location_name: Строка с расположением из Excel
        
    Returns:
        Список нормализованных названий павильонов
    """
    base = location_name.strip()
    
    # Общий X, Y (...) -> берём только первый павильон
    if base.lower().startswith('общий '):
        base = base[6:].strip()  # убираем "Общий "
        if ',' in base:
            base = base.split(',')[0].strip()
    
    # Если нет запятых - просто нормализуем и возвращаем варианты
    if ',' not in base:
        normalized = normalize_single_name(base)
        normalized_no_spaces = re.sub(r'\s+', '', normalized)
        # Возвращаем оба варианта если они различаются
        if normalized == normalized_no_spaces:
            return [normalized]
        return [normalized, normalized_no_spaces]
    
    # Есть запятые - разворачиваем
    parts = [p.strip() for p in base.split(',') if p.strip()]
    if not parts:
        return []
    
    first = normalize_single_name(parts[0])
    
    # Паттерн X/Y,Z: первый кусок "Е10/1", извлекаем префикс "Е10/"
    match = re.match(r'^(.+/\s*)(\d+)$', first)
    if match:
        prefix = match.group(1)
        prefix = re.sub(r'\s+', '', prefix)
        result = [first]
        
        for p in parts[1:]:
            p = p.strip()
            if p.isdigit():
                # Просто цифра - добавляем префикс
                result.append(prefix + p)
            else:
                # Полное имя - нормализуем
                result.append(normalize_single_name(p))
        return result
    
    # Разные префиксы — каждое имя как есть
    return [normalize_single_name(p) for p in parts]


def find_pavilions_by_names(names, building=None):
    """
    Ищет павильоны по списку имён с учётом нормализации.
    
    Args:
        names: Список названий павильонов
        building: Опционально - здание для ограничения поиска
        
    Returns:
        Список найденных объектов Pavilion (без дублей)
    """
    found = []
    seen_ids = set()
    
    for name in names:
        if not name:
            continue
        
        # Пробуем имя и его вариант без пробелов
        candidates = [name]
        normalized = re.sub(r'\s+', '', name)
        if normalized != name:
            candidates.append(normalized)
        
        for candidate in candidates:
            if not candidate:
                continue
            
            try:
                query = Pavilion.objects.filter(name=candidate)
                if building:
                    query = query.filter(building=building)
                
                pavilion = query.first()
                if pavilion and pavilion.id not in seen_ids:
                    seen_ids.add(pavilion.id)
                    found.append(pavilion)
                    break
            except Exception:
                continue
    
    return found


def find_pavilion_by_name(name, building=None):
    """
    Ищет один павильон по названию с учётом нормализации.
    Удобная обёртка для случаев, когда нужен один павильон.
    
    Args:
        name: Название павильона
        building: Опционально - здание для ограничения поиска
        
    Returns:
        Объект Pavilion или None
    """
    names = expand_location_to_pavilion_names(name)
    pavilions = find_pavilions_by_names(names, building=building)
    return pavilions[0] if pavilions else None
