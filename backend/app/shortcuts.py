"""Persistent favorites for the demo workspace."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints

from app.api import ApiError, settings_for
from app.config import Settings
from app.database import connection
from app.preferences import load_preferences

router = APIRouter()


class FavoriteInput(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    enabled: bool


def read_favorites(db):
    return [row['question'] for row in db.execute('SELECT question FROM favorites ORDER BY rowid DESC')]


def create_favorites(db):
    db.execute('CREATE TABLE IF NOT EXISTS favorites (question TEXT NOT NULL UNIQUE)')


@router.get('/favorites')
def favorites(settings: Settings = Depends(settings_for)):
    with connection(settings.database_path) as db:
        create_favorites(db)
        return read_favorites(db)


@router.put('/favorites')
def update_favorite(payload: FavoriteInput, settings: Settings = Depends(settings_for)):
    if len(payload.question) > settings.question_max_length:
        raise ApiError(422, 'question_too_long', '问题超出当前长度限制。')
    with connection(settings.database_path) as db:
        create_favorites(db)
        if payload.enabled:
            db.execute('INSERT INTO favorites(question) VALUES (?) ON CONFLICT DO NOTHING', (payload.question,))
        else:
            db.execute('DELETE FROM favorites WHERE question=?', (payload.question,))
        return read_favorites(db)


def create_counts(db):
    db.execute('CREATE TABLE IF NOT EXISTS question_counts (question TEXT PRIMARY KEY, count INTEGER NOT NULL)')


def record_question(db, question):
    create_counts(db)
    db.execute('INSERT INTO question_counts VALUES (?,1) ON CONFLICT(question) DO UPDATE SET count=count+1', (question,))


@router.get('/questions/hot')
def hot_questions(settings: Settings = Depends(settings_for)):
    preferences = load_preferences(settings)
    if not preferences.hot_enabled:
        return []
    with connection(settings.database_path) as db:
        create_counts(db)
        return [dict(row) for row in db.execute('SELECT * FROM question_counts WHERE count>? ORDER BY count DESC,question', (preferences.hot_threshold,))]
