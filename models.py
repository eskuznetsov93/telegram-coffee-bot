# структура кофе
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Coffee:
    """Модель данных для кофе"""
    id: Optional[int] = None
    user_id: int = 0
    country: str = ""
    plantation: str = ""
    processing: str = ""
    roaster: str = ""
    q_grade: Optional[int] = None
    my_rating: Optional[int] = None
    created_at: Optional[datetime] = None
