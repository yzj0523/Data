from threading import Event

import anyio
import pytest

from app.database import connection
from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_duplicate_pending_requests_and_late_completion_cannot_revive_session(query_client):
    _, client, plan = query_client
    started, release = Event(), Event()
    def provider(body):
        question = body['messages'][-1]['content']
        if question == '等候中的北京查询':
            started.set()
            assert release.wait(5)
        return {'plan':{'metric':'revenue','year':2026,'division':'北京' if '北京' in question else '上海'}}
    plan(provider)
    async with client() as api:
        a, b = await new_session(api), await new_session(api)
        completion = []
        async def slow():
            completion.append(await ask(api,a,'等候中的北京查询',request_id='one'))
        async with anyio.create_task_group() as group:
            group.start_soon(slow)
            try:
                assert await anyio.to_thread.run_sync(started.wait, 4)
                duplicate = (await ask(api,a,'等候中的北京查询',request_id='one')).json()
                assert duplicate['status'] == 'pending'
                assert (await ask(api,a,'不同问题',request_id='one')).status_code == 409
                assert (await ask(api,a,'另一个请求')).json()['error']['code'] == 'query_in_progress'
                other = (await ask(api,b,'上海查询')).json()
                assert other['result']['rows'] == [['上海代表处',5000]]
                assert (await api.delete(f'/api/sessions/{a}')).status_code == 204
            finally:
                release.set()
        assert completion[0].json()['error']['code'] == 'query_obsolete'
        assert (await api.get(f'/api/sessions/{b}/messages')).json() == [other]
import sqlite3
from datetime import UTC, datetime, timedelta


async def test_interrupted_pending_turn_recovers_when_reopening_history(query_client):
    path, client, plan = query_client
    async with client() as api:
        sid = await new_session(api)
        with sqlite3.connect(path) as db:
            db.execute('INSERT INTO turns (id,session_id,position,request_id,question,status,created_at) VALUES (?,?,?,?,?,?,?)',
                       ('interrupted',sid,1,'old','收入','pending',(datetime.now(UTC)-timedelta(minutes=20)).isoformat()))
        turn = (await api.get(f'/api/sessions/{sid}/messages')).json()[0]
        assert turn['status'] == 'failed' and turn['result']['code'] == 'request_interrupted'
        plan({'plan':{'metric':'revenue','year':2026}})
        assert (await ask(api,sid)).json()['status'] == 'ok'


async def test_query_request_identity_includes_operation_across_schema_upgrade(query_client):
    path, client, plan = query_client
    plan({'plan':{'metric':'revenue','year':2026,'division':'北京'}})
    async with client() as api:
        sid = await new_session(api)
        origin = (await ask(api,sid,'原问题',request_id='original')).json()
        replay = {'operation':'resend','origin_id':origin['id'],'request_id':'same-key'}
        resent = (await ask(api,sid,'原问题',**replay)).json()
        with connection(path) as db:
            db.execute('ALTER TABLE turns DROP COLUMN operation')
        assert (await ask(api,sid,'原问题',**replay)).json() == resent
        changed = await ask(api,sid,'原问题',**(replay | {'operation':'edit'}))
        assert changed.status_code == 409 and changed.json()['error']['code'] == 'request_conflict'
        assert (await ask(api,sid,origin_id=origin['id'])).status_code == 422
        assert (await ask(api,sid,operation='edit')).status_code == 422
        assert (await ask(api,sid,operation='resend',origin_id=' ')).status_code == 422
        assert (await api.get(f'/api/sessions/{sid}/messages')).json() == [origin,resent]
