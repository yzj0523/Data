"""Persist the active application preferences."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

from app.api import settings_for
from app.config import Settings
from app.database import connection

router = APIRouter()
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Greeting = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    greeting_enabled: bool = True
    greeting: Greeting = '欢迎使用智能AI问数，您可以向我咨询经营数据、报表分析相关问题。'
    opening_questions: list[Question] = Field(default_factory=lambda: [
        '各产品线销售情况', '北京的产品线收入情况', '深圳的产品销售情况',
    ], max_length=10)
    suggestions_enabled: bool = True
    hot_enabled: bool = True
    hot_threshold: StrictInt = Field(default=3, gt=0)
    custom_model_enabled: bool = False


def load_preferences(settings: Settings) -> Preferences:
    with connection(settings.database_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        row = db.execute('SELECT value FROM preferences WHERE id=1').fetchone()
        return Preferences.model_validate_json(row['value']) if row else Preferences()


@router.get('/app-config')
def get_preferences(settings: Settings = Depends(settings_for)) -> Preferences:
    return load_preferences(settings)


@router.put('/app-config')
def put_preferences(payload: Preferences, settings: Settings = Depends(settings_for)) -> Preferences:
    with connection(settings.database_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO preferences VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (payload.model_dump_json(),))
    return payload
