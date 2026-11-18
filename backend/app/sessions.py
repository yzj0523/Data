"""Persistent sessions and structured conversation turns."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, StringConstraints

from app.api import ApiError, settings_for
from app.config import Settings
from app.database import connection

router = APIRouter()
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
SCHEMA = '''
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL, request_id TEXT NOT NULL, question TEXT NOT NULL,
    status TEXT NOT NULL, result TEXT, origin_id TEXT, source_ids TEXT NOT NULL DEFAULT '[]',
    operation TEXT NOT NULL DEFAULT 'ask',
    active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
    UNIQUE(session_id, request_id)
);
CREATE INDEX IF NOT EXISTS turns_history ON turns(session_id,active,position);
'''


@contextmanager
def session_store(settings: Settings):
    with connection(settings.database_path) as db:
        db.executescript(SCHEMA)
        if not any(row['name'] == 'operation' for row in db.execute('PRAGMA table_info(turns)')):
            db.execute('BEGIN IMMEDIATE')
            if not any(row['name'] == 'operation' for row in db.execute('PRAGMA table_info(turns)')):
                db.execute("ALTER TABLE turns ADD COLUMN operation TEXT NOT NULL DEFAULT 'ask'")
                db.execute("""UPDATE turns SET operation=CASE
                    WHEN EXISTS(SELECT 1 FROM turns AS origin WHERE origin.id=turns.origin_id
                                AND origin.session_id=turns.session_id AND origin.position=turns.position) THEN 'edit'
                    WHEN EXISTS(SELECT 1 FROM turns AS origin WHERE origin.id=turns.origin_id
                                AND origin.session_id=turns.session_id AND origin.position<turns.position) THEN 'resend'
                    ELSE 'legacy' END WHERE origin_id IS NOT NULL""")
            db.commit()
        yield db


def utc_now() -> datetime:
    return datetime.now(UTC)


def expire_pending(db, settings: Settings, session_id: str):
    budget = settings.model_timeout_seconds * 2 + settings.query_timeout_seconds * 2 + 30
    cutoff = (utc_now() - timedelta(seconds=budget)).isoformat()
    failure = json.dumps({'code':'request_interrupted','summary':'查询进程已中断，请重新发送问题。'},ensure_ascii=False)
    return db.execute("UPDATE turns SET status='failed',result=? WHERE session_id=? AND status='pending' AND created_at<?",
                      (failure,session_id,cutoff)).rowcount


def require_session(db, session_id: str):
    row = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
    if row is None:
        raise ApiError(404, 'session_not_found', '会话不存在。')
    return row


def session_json(row):
    return {**dict(row), 'pinned': bool(row['pinned'])}


def turn_json(row):
    return {key: row[key] for key in ('id','session_id','position','request_id','question','status','origin_id','created_at')} | {
        'result': json.loads(row['result']) if row['result'] else None,
        'source_ids': json.loads(row['source_ids']),
        'active': bool(row['active']),
    }


class CreateSession(BaseModel):
    title: Title = '新对话'


class UpdateSession(BaseModel):
    title: Title | None = None
    pinned: bool | None = None


@router.post('/sessions', status_code=201)
def create_session(payload: CreateSession, settings: Settings = Depends(settings_for)):
    now = utc_now().isoformat()
    session_id = uuid4().hex
    with session_store(settings) as db:
        db.execute('INSERT INTO sessions VALUES (?,?,0,?,?)', (session_id, payload.title, now, now))
        return session_json(require_session(db, session_id))


@router.get('/sessions')
def sessions(settings: Settings = Depends(settings_for)):
    cutoff = (utc_now() - timedelta(days=30)).isoformat()
    with session_store(settings) as db:
        rows = db.execute('SELECT * FROM sessions WHERE updated_at >= ? ORDER BY pinned DESC,updated_at DESC,id', (cutoff,))
        return [session_json(row) for row in rows]


@router.patch('/sessions/{session_id}')
def update_session(session_id: str, payload: UpdateSession, settings: Settings = Depends(settings_for)):
    with session_store(settings) as db:
        db.execute('BEGIN IMMEDIATE')
        current = require_session(db, session_id)
        title = payload.title if payload.title is not None else current['title']
        pinned = payload.pinned if payload.pinned is not None else current['pinned']
        db.execute('UPDATE sessions SET title=?,pinned=? WHERE id=?', (title, pinned, session_id))
        return session_json(require_session(db, session_id))


@router.delete('/sessions/{session_id}', status_code=204)
def delete_session(session_id: str, settings: Settings = Depends(settings_for)):
    with session_store(settings) as db:
        if not db.execute('DELETE FROM sessions WHERE id=?', (session_id,)).rowcount:
            raise ApiError(404, 'session_not_found', '会话不存在。')
    return Response(status_code=204)


@router.get('/sessions/{session_id}/messages')
def messages(session_id: str, settings: Settings = Depends(settings_for)):
    with session_store(settings) as db:
        db.execute('BEGIN IMMEDIATE')
        require_session(db, session_id)
        expire_pending(db, settings, session_id)
        rows = db.execute('SELECT * FROM turns WHERE session_id=? AND active=1 ORDER BY position', (session_id,))
        return [turn_json(row) for row in rows]
