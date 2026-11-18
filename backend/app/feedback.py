"""Capture the exact answer visible at the time of a data-error report."""

import json
from uuid import uuid4

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints

from app.api import ApiError, settings_for
from app.config import Settings
from app.sessions import session_store, utc_now

router = APIRouter()


FEEDBACK_SCHEMA = '''CREATE TABLE IF NOT EXISTS feedback (
        id TEXT PRIMARY KEY, turn_id TEXT NOT NULL, session_id TEXT NOT NULL,
        question TEXT NOT NULL, answer TEXT NOT NULL, reporter TEXT NOT NULL,
        status TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, request_id TEXT UNIQUE
    )'''


def feedback_schema(db):
    db.execute(FEEDBACK_SCHEMA)
    if any(row['name'] == 'request_id' for row in db.execute('PRAGMA table_info(feedback)')):
        return
    db.execute('BEGIN IMMEDIATE')
    if not any(row['name'] == 'request_id' for row in db.execute('PRAGMA table_info(feedback)')):
        db.execute('ALTER TABLE feedback RENAME TO feedback_legacy')
        db.execute(FEEDBACK_SCHEMA)
        db.execute('''INSERT INTO feedback (id,turn_id,session_id,question,answer,reporter,status,notes,created_at,updated_at)
                      SELECT id,turn_id,session_id,question,answer,reporter,status,notes,created_at,updated_at FROM feedback_legacy''')
        db.execute('DROP TABLE feedback_legacy')
    db.commit()


def feedback_json(row):
    return {key: row[key] for key in row.keys() if key != 'request_id'} | {'answer':json.loads(row['answer'])}


def require_feedback(db, feedback_id):
    row = db.execute('SELECT * FROM feedback WHERE id=?', (feedback_id,)).fetchone()
    if not row:
        raise ApiError(404, 'feedback_not_found', '反馈记录不存在。')
    return row


class Report(BaseModel):
    turn_id: str = Field(min_length=1, max_length=120)
    request_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None


@router.post('/feedbacks', status_code=201)
def submit_report(payload: Report, settings: Settings = Depends(settings_for)):
    with session_store(settings) as db:
        feedback_schema(db)
        db.execute('BEGIN IMMEDIATE')
        if payload.request_id:
            previous = db.execute('SELECT * FROM feedback WHERE request_id=?', (payload.request_id,)).fetchone()
            if previous:
                if previous['turn_id'] != payload.turn_id:
                    raise ApiError(409, 'request_conflict', '该请求标识已用于其他答案。')
                return feedback_json(previous)
        turn = db.execute("SELECT * FROM turns WHERE id=? AND status='ok' AND active=1", (payload.turn_id,)).fetchone()
        if not turn:
            raise ApiError(404, 'answer_not_found', '没有找到可反馈的答案。')
        # Preserve the current user-facing behavior for distinct requests while Q08 is open.
        if db.execute('SELECT 1 FROM feedback WHERE turn_id=?', (payload.turn_id,)).fetchone():
            raise ApiError(409, 'feedback_exists', '该答案已有反馈，重复反馈处理规则尚待确认。')
        feedback_id, now = uuid4().hex, utc_now().isoformat()
        db.execute('''INSERT INTO feedback (id,turn_id,session_id,question,answer,reporter,status,notes,created_at,updated_at,request_id)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
            feedback_id,turn['id'],turn['session_id'],turn['question'],turn['result'],'演示用户','pending','',now,now,payload.request_id,
        ))
        return feedback_json(require_feedback(db, feedback_id))


@router.get('/feedbacks/{feedback_id}')
def get_feedback(feedback_id: str, settings: Settings = Depends(settings_for)):
    with session_store(settings) as db:
        feedback_schema(db)
        return feedback_json(require_feedback(db, feedback_id))


@router.get('/feedbacks')
def list_feedbacks(
    question: str = Query(default='', max_length=200), reporter: str = Query(default='', max_length=120),
    status: Literal['pending','resolved'] | None = None, page: int = Query(default=1, ge=1),
    page_size: int = 10, settings: Settings = Depends(settings_for),
):
    if page_size not in (5,10,20):
        raise ApiError(422, 'invalid_page_size', '每页只能选择 5、10 或 20 条。')
    filters = ['instr(lower(question), lower(?)) > 0 OR ? = \'\'','instr(lower(reporter), lower(?)) > 0 OR ? = \'\'']
    params = [question,question,reporter,reporter]
    if status:
        filters.append('status = ?')
        params.append(status)
    where = ' AND '.join(f'({condition})' for condition in filters)
    with session_store(settings) as db:
        feedback_schema(db)
        db.execute('BEGIN')
        total = db.execute(f'SELECT COUNT(*) FROM feedback WHERE {where}', params).fetchone()[0]
        pages = max(1, (total+page_size-1)//page_size)
        page = min(page,pages)
        items = [dict(row) for row in db.execute(f'''SELECT id,turn_id,question,reporter,status,created_at FROM feedback
            WHERE {where} ORDER BY created_at DESC,id LIMIT ? OFFSET ?''', [*params,page_size,(page-1)*page_size])]
    return {'items':items,'total':total,'page':page,'page_size':page_size,'pages':pages}


class Review(BaseModel):
    status: Literal['pending','resolved']
    notes: str = Field(max_length=4000)


@router.patch('/feedbacks/{feedback_id}')
def review_feedback(feedback_id: str, payload: Review, settings: Settings = Depends(settings_for)):
    with session_store(settings) as db:
        feedback_schema(db)
        db.execute('UPDATE feedback SET status=?,notes=?,updated_at=? WHERE id=?', (payload.status,payload.notes,utc_now().isoformat(),feedback_id))
        return feedback_json(require_feedback(db,feedback_id))
