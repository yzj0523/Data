import json
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.main import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    path = tmp_path / 'app.sqlite3'
    monkeypatch.setenv('AI_DATABASE_PATH', str(path))

    def client(**kwargs):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(), **kwargs), base_url='http://test')

    return path, client


async def test_sessions_persist_pin_history_and_delete(client_factory):
    path, client = client_factory
    async with client() as api:
        a = (await api.post('/api/sessions', json={'title': '第一组'})).json()['id']
        b = (await api.post('/api/sessions', json={})).json()['id']
        old = (await api.post('/api/sessions', json={})).json()['id']
        assert (await api.patch(f'/api/sessions/{a}', json={'title':' 北京 ', 'pinned':True})).json()['title'] == '北京'
        assert (await api.patch(f'/api/sessions/{b}', json={'title':' '})).status_code == 422
    with sqlite3.connect(path) as db:
        db.execute('UPDATE sessions SET updated_at=? WHERE id=?', ((datetime.now(UTC)-timedelta(days=32)).isoformat(),old))
        db.execute('INSERT INTO turns (id,session_id,position,request_id,question,status,result,created_at) VALUES (?,?,?,?,?,?,?,?)',
                   ('m1', b, 0, 'r1', '收入？', 'ok', json.dumps({'rows':[[30]]}), datetime.now(UTC).isoformat()))
    async with client() as api:
        assert [s['id'] for s in (await api.get('/api/sessions')).json()] == [a,b]
        assert (await api.get(f'/api/sessions/{old}/messages')).json() == []
        history = (await api.get(f'/api/sessions/{b}/messages')).json()
        assert history[0]['id'] == 'm1' and history[0]['result'] == {'rows': [[30]]}
        assert (await api.delete(f'/api/sessions/{b}')).status_code == 204
        assert (await api.get(f'/api/sessions/{b}/messages')).json()['error']['code'] == 'session_not_found'
