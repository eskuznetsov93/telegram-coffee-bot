# работа с базой
import sqlite3
from typing import List, Optional
from models import Coffee
from datetime import datetime


class Database:
    def __init__(self, db_path: str = "coffee.db"):
        """Инициализация базы данных"""
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Создание таблицы, если её нет"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
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
