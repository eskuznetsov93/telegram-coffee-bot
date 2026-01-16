# работа с базой
import sqlite3
import logging
from typing import List, Optional
from models import Coffee
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "coffee.db"):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.init_db()
    
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
    
    def get_all_countries(self) -> List[str]:
        """Получение списка всех уникальных стран"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT country FROM locations ORDER BY country")
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows] if rows else []
    
    def get_plantations_by_country(self, country: str) -> List[str]:
        """Получение списка плантаций для конкретной страны"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT plantation 
            FROM locations 
            WHERE country = ? 
            ORDER BY plantation
        """, (country,))
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
        """Получение кофе, сгруппированных по plantation+processing+q_grade+roaster, с средним рейтингом"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                plantation,
                processing,
                q_grade,
                roaster,
                country,
                AVG(my_rating) as avg_rating,
                COUNT(*) as count
            FROM coffee
            WHERE my_rating IS NOT NULL
            GROUP BY plantation, processing, q_grade, roaster
            ORDER BY avg_rating DESC, count DESC
        """)
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
                'avg_rating': round(row[5], 2) if row[5] else None,
                'count': row[6]
            })
        return result
