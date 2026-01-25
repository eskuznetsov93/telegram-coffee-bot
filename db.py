# работа с базой
import sqlite3
import logging
import re
from typing import List, Optional, Dict, Tuple
from models import Coffee
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "coffee.db"):
        """Инициализация базы данных"""
        self.db_path = db_path
        
        # Словарь типичных ошибок в написании (правильное -> варианты с ошибками)
        # Ключ - правильное написание, значение - список вариантов с ошибками
        self.typo_corrections = {
            # Плантации и регионы
            'dak': ['dack', 'dak coffee', 'dakcoffee', 'dak cofee'],
            'huila': ['guilla', 'huilla', 'huela', 'huila'],
            'guji': ['gudji', 'gudzhi', 'gudji', 'gudzhi'],
            'yirgacheffe': ['yirgachefe', 'yirgachef', 'yirgacheffe', 'yirgachefe'],
            'sidamo': ['sidama', 'sidamo'],
            'harrar': ['harar', 'harrar', 'harar'],
            'geisha': ['gesha', 'geisha', 'geysha'],
            'bourbon': ['bourbon', 'bourboun', 'bourbon'],
            'caturra': ['caturra', 'caturа', 'caturra'],  # кириллическая 'а'
            'typica': ['typica', 'typicа', 'typica'],
            
            # Обжарщики
            'submarine': ['submarin', 'submarinе', 'submarin'],  # кириллическая 'е'
            'camera obscura': ['camera obscurа', 'camera obscurа', 'camera obscura'],  # кириллическая 'а'
            'dak coffee': ['dak coffee', 'dack coffee', 'dak cofee', 'dakcoffee'],
        }
        
        self.init_db()
    
    def _normalize_name(self, name: str) -> str:
        """Нормализация названия: lowercase, удаление лишних пробелов"""
        if not name:
            return ""
        # Приводим к lowercase, удаляем лишние пробелы
        normalized = re.sub(r'\s+', ' ', name.strip().lower())
        return normalized
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Вычисление расстояния Левенштейна между двумя строками"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _find_correct_spelling(self, name: str) -> Optional[str]:
        """Поиск правильного написания в словаре типичных ошибок"""
        normalized = self._normalize_name(name)
        
        # Проверяем прямые совпадения
        for correct, variants in self.typo_corrections.items():
            if normalized == correct:
                return correct
            if normalized in variants:
                return correct
        
        # Проверяем похожие варианты (расстояние <= 1)
        for correct, variants in self.typo_corrections.items():
            if self._levenshtein_distance(normalized, correct) <= 1:
                return correct
            for variant in variants:
                if self._levenshtein_distance(normalized, variant) <= 1:
                    return correct
        
        return None
    
    def _normalize_for_grouping(self, name: str) -> str:
        """Нормализация названия для группировки с учетом опечаток"""
        if not name:
            return ""
        
        normalized = self._normalize_name(name)
        
        # Проверяем словарь типичных ошибок
        correct_spelling = self._find_correct_spelling(normalized)
        if correct_spelling:
            return correct_spelling
        
        # Если не найдено в словаре, возвращаем нормализованное значение
        return normalized
    
    def _group_similar_names(self, names: List[str], max_distance: int = 1) -> Dict[str, str]:
        """Группировка похожих названий по расстоянию Левенштейна
        Возвращает словарь: оригинальное название -> каноническое название группы"""
        if not names:
            return {}
        
        # Создаем словарь: оригинальное название -> каноническое название
        name_to_canonical = {}
        
        # Сначала нормализуем все названия и создаем группы
        normalized_to_originals = {}
        for name in names:
            normalized = self._normalize_for_grouping(name)
            if normalized not in normalized_to_originals:
                normalized_to_originals[normalized] = []
            normalized_to_originals[normalized].append(name)
        
        # Группируем похожие нормализованные названия
        normalized_groups = {}
        processed = set()
        normalized_list = list(normalized_to_originals.keys())
        
        for i, norm1 in enumerate(normalized_list):
            if norm1 in processed:
                continue
            
            # Используем самое частое оригинальное название как каноническое
            originals1 = normalized_to_originals[norm1]
            canonical = max(originals1, key=lambda x: originals1.count(x))
            normalized_groups[norm1] = canonical
            
            # Ищем похожие названия
            for j, norm2 in enumerate(normalized_list[i+1:], start=i+1):
                if norm2 in processed:
                    continue
                
                distance = self._levenshtein_distance(norm1, norm2)
                if distance <= max_distance:
                    # Объединяем в одну группу
                    normalized_groups[norm2] = canonical
                    processed.add(norm2)
            
            processed.add(norm1)
        
        # Создаем финальный словарь: оригинальное название -> каноническое
        for name in names:
            normalized = self._normalize_for_grouping(name)
            canonical = normalized_groups.get(normalized, name)
            name_to_canonical[name] = canonical
        
        return name_to_canonical
    
    def init_db(self):
        """Создание таблиц, если их нет"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица кофе
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coffee (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                country TEXT NOT NULL,
                plantation TEXT NOT NULL,
                processing TEXT NOT NULL,
                roaster TEXT NOT NULL,
                q_grade INTEGER,
                my_rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для хранения уникальных комбинаций страна-плантация
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT NOT NULL,
                plantation TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(country, plantation)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_coffee(self, coffee: Coffee) -> int:
        """Добавление кофе в базу данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO coffee (user_id, country, plantation, processing, roaster, q_grade, my_rating, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            coffee.user_id,
            coffee.country,
            coffee.plantation,
            coffee.processing,
            coffee.roaster,
            coffee.q_grade,
            coffee.my_rating,
            coffee.created_at
        ))
        coffee_id = cursor.lastrowid
        conn.commit()
        
        # Сохраняем комбинацию страна-плантация в таблицу locations
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO locations (country, plantation)
                VALUES (?, ?)
            """, (coffee.country, coffee.plantation))
            conn.commit()
        except Exception as e:
            logger.warning(f"Не удалось сохранить локацию: {e}")
        
        conn.close()
        return coffee_id
    
    def get_coffee_by_user(self, user_id: int) -> List[Coffee]:
        """Получение всех кофе пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, country, plantation, processing, roaster, q_grade, my_rating, created_at
            FROM coffee
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        coffee_list = []
        for row in rows:
            coffee = Coffee(
                id=row[0],
                user_id=row[1],
                country=row[2],
                plantation=row[3],
                processing=row[4],
                roaster=row[5],
                q_grade=row[6],
                my_rating=row[7],
                created_at=datetime.fromisoformat(row[8]) if row[8] else None
            )
            coffee_list.append(coffee)
        return coffee_list
    
    def get_coffee_by_id(self, coffee_id: int) -> Optional[Coffee]:
        """Получение кофе по ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, country, plantation, processing, roaster, q_grade, my_rating, created_at
            FROM coffee
            WHERE id = ?
        """, (coffee_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Coffee(
                id=row[0],
                user_id=row[1],
                country=row[2],
                plantation=row[3],
                processing=row[4],
                roaster=row[5],
                q_grade=row[6],
                my_rating=row[7],
                created_at=datetime.fromisoformat(row[8]) if row[8] else None
            )
        return None
    
    def get_coffee_by_user_sorted_by_rating(self, user_id: int) -> List[Coffee]:
        """Получение всех кофе пользователя, отсортированных по оценке (DESC)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, country, plantation, processing, roaster, q_grade, my_rating, created_at
            FROM coffee
            WHERE user_id = ?
            ORDER BY my_rating DESC, created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        coffee_list = []
        for row in rows:
            coffee = Coffee(
                id=row[0],
                user_id=row[1],
                country=row[2],
                plantation=row[3],
                processing=row[4],
                roaster=row[5],
                q_grade=row[6],
                my_rating=row[7],
                created_at=datetime.fromisoformat(row[8]) if row[8] else None
            )
            coffee_list.append(coffee)
        return coffee_list
    
    def get_all_coffee(self) -> List[Coffee]:
        """Получение всех кофе от всех пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, country, plantation, processing, roaster, q_grade, my_rating, created_at
            FROM coffee
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        coffee_list = []
        for row in rows:
            coffee = Coffee(
                id=row[0],
                user_id=row[1],
                country=row[2],
                plantation=row[3],
                processing=row[4],
                roaster=row[5],
                q_grade=row[6],
                my_rating=row[7],
                created_at=datetime.fromisoformat(row[8]) if row[8] else None
            )
            coffee_list.append(coffee)
        return coffee_list
    
    def get_all_countries(self, limit: int = 15) -> List[str]:
        """Get list of countries sorted by frequency and last use date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                country,
                COUNT(*) as usage_count,
                MAX(created_at) as last_used
            FROM coffee
            GROUP BY country
            ORDER BY usage_count DESC, last_used ASC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows] if rows else []
    
    def get_plantations_by_country(self, country: str, limit: int = 15) -> List[str]:
        """Get list of plantations for a country sorted by frequency and last use date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                plantation,
                COUNT(*) as usage_count,
                MAX(created_at) as last_used
            FROM coffee
            WHERE country = ?
            GROUP BY plantation
            ORDER BY usage_count DESC, last_used ASC
            LIMIT ?
        """, (country, limit))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows] if rows else []
    
    def get_all_roasters(self, limit: int = 15) -> List[str]:
        """Get list of all unique roasters sorted by frequency and last use date (case-insensitive)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                MIN(roaster) as roaster,
                COUNT(*) as usage_count,
                MAX(created_at) as last_used
            FROM coffee
            WHERE roaster IS NOT NULL AND roaster != ''
            GROUP BY UPPER(roaster)
            ORDER BY usage_count DESC, last_used ASC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows] if rows else []
    
    def get_grouped_coffee_by_user(self, user_id: int) -> List[dict]:
        """Получение кофе пользователя, сгруппированных по plantation+processing+q_grade+roaster, отсортированных по рейтингу"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                plantation,
                processing,
                q_grade,
                roaster,
                country,
                MAX(my_rating) as max_rating,
                COUNT(*) as count
            FROM coffee
            WHERE user_id = ?
            GROUP BY plantation, processing, q_grade, roaster
            ORDER BY max_rating DESC, count DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append({
                'plantation': row[0],
                'processing': row[1],
                'q_grade': row[2],
                'roaster': row[3],
                'country': row[4],
                'max_rating': row[5],
                'count': row[6]
            })
        return result
    
    def get_grouped_coffee_average_rating(self) -> List[dict]:
        """Получение кофе, сгруппированных по plantation+processing+q_grade+roaster, с средним рейтингом
        с учетом нормализации названий (игнорирование регистра, опечаток, типичных ошибок)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем все записи
        cursor.execute("""
            SELECT 
                plantation,
                processing,
                q_grade,
                roaster,
                country,
                my_rating
            FROM coffee
            WHERE my_rating IS NOT NULL
        """)
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return []
        
        # Собираем уникальные названия для нормализации
        plantations = set()
        roasters = set()
        for row in rows:
            if row[0]:  # plantation
                plantations.add(row[0])
            if row[3]:  # roaster
                roasters.add(row[3])
        
        # Группируем похожие названия
        plantation_groups = self._group_similar_names(list(plantations))
        roaster_groups = self._group_similar_names(list(roasters))
        
        # Группируем записи с учетом нормализации
        grouped = {}
        for row in rows:
            plantation = row[0] or ""
            processing = row[1] or ""
            q_grade = row[2]
            roaster = row[3] or ""
            country = row[4] or ""
            rating = row[5]
            
            # Нормализуем названия для группировки (используем оригинальное название для поиска канонического)
            norm_plantation = plantation_groups.get(plantation, plantation) if plantation else ""
            norm_roaster = roaster_groups.get(roaster, roaster) if roaster else ""
            
            # Используем нормализованные значения как ключ группы
            group_key = (norm_plantation, processing, q_grade, norm_roaster)
            
            if group_key not in grouped:
                grouped[group_key] = {
                    'plantation': norm_plantation,
                    'processing': processing,
                    'q_grade': q_grade,
                    'roaster': norm_roaster,
                    'country': country,  # Берем первую встретившуюся страну
                    'ratings': [],
                    'count': 0
                }
            
            grouped[group_key]['ratings'].append(rating)
            grouped[group_key]['count'] += 1
        
        # Вычисляем средний рейтинг и формируем результат
        result = []
        for group_data in grouped.values():
            avg_rating = sum(group_data['ratings']) / len(group_data['ratings'])
            result.append({
                'plantation': group_data['plantation'],
                'processing': group_data['processing'],
                'q_grade': group_data['q_grade'],
                'roaster': group_data['roaster'],
                'country': group_data['country'],
                'avg_rating': round(avg_rating, 2),
                'count': group_data['count']
            })
        
        # Сортируем по среднему рейтингу и количеству оценок
        result.sort(key=lambda x: (x['avg_rating'], x['count']), reverse=True)
        
        return result
