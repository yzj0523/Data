from datetime import timedelta
from threading import Event

import anyio
import httpx
import pytest

from app.database import connection
from app.sessions import utc_now
from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize('edit_index', [0,1,2])
async def test_edit_replaces_only_active_suffix_while_resend_appends(query_client, edit_index):
    _, client, plan = query_client
    plan({'plan':{'metric':'revenue','year':2026,'division':'北京'}})
    async with client() as api:
        sid = await new_session(api)
        original = [(await ask(api,sid,f'北京收入{i}')).json() for i in range(3)]
        resent = (await ask(api,sid,'不是原文',operation='resend',origin_id=original[0]['id'])).json()
        assert resent['question'] == original[0]['question']
        assert resent['origin_id'] == original[0]['id'] and resent['position'] == 4
        assert (await api.get(f'/api/sessions/{sid}/messages')).json() == [*original,resent]
        target = original[edit_index]
        assert (await ask(api,sid,' ',operation='edit',origin_id=target['id'])).status_code == 422
        plan({'plan':{'metric':'revenue','year':2025,'division':'北京'}})
        edited = (await ask(api,sid,'改看 2025',operation='edit',origin_id=target['id'])).json()
        assert edited['position'] == target['position'] and edited['id'] != target['id']
    async with client() as api:
        assert (await api.get(f'/api/sessions/{sid}/messages')).json() == [*original[:edit_index],edited]
        plan({'changes':{'chart':'line'}})
        assert (await ask(api,sid,'用折线图')).json()['result']['rows'] == [['北京代表处',2500]]


async def test_pending_and_failed_edit_preserve_history_and_feedback(query_client):
    _, client, plan = query_client
    started, release = Event(), Event()

    def provider(body):
        if body['messages'][-1]['content'] == '修改失败':
            started.set()
            assert release.wait(5)
            raise httpx.ReadTimeout('simulated')
        return {'plan':{'metric':'revenue','year':2026,'division':'北京'}}

    plan(provider)
    async with client() as api:
        sid = await new_session(api)
        original = [(await ask(api,sid,f'问题{i}')).json() for i in range(2)]
        payload = {'operation':'edit','origin_id':original[0]['id'],'request_id':'edit-timeout'}
        replies = []

        async def edit():
            replies.append((await ask(api,sid,'修改失败',**payload)).json())

        async with anyio.create_task_group() as group:
            group.start_soon(edit)
            try:
                assert await anyio.to_thread.run_sync(started.wait, 4)
                assert (await api.get(f'/api/sessions/{sid}/messages')).json() == original
                assert (await ask(api,sid,'修改失败',**payload)).json()['status'] == 'pending'
                assert (await ask(api,sid)).json()['error']['code'] == 'query_in_progress'
            finally:
                release.set()

        assert replies[0]['result']['code'] == 'model_timeout'
        assert replies[0]['active'] is False
        assert (await ask(api,sid,'修改失败',**payload)).json() == replies[0]
        plan({'clarification':True})
        clarification = (await ask(api,sid,'含糊的修改',**(payload | {'request_id':'clarify'}))).json()
        assert clarification['status'] == 'clarification' and clarification['active'] is False
        assert (await api.get(f'/api/sessions/{sid}/messages')).json() == original
        assert (await api.post('/api/feedbacks',json={'turn_id':original[0]['id']})).status_code == 201
        plan({'plan':{'metric':'revenue','year':2020}})
        empty = (await ask(api,sid,'改看空年份',**(payload | {'request_id':'empty'}))).json()
        assert empty['status'] == 'empty' and empty['active'] is True
        assert (await api.get(f'/api/sessions/{sid}/messages')).json() == [empty]


@pytest.mark.parametrize('interrupt', ['expire','delete'])
async def test_interrupted_edit_cannot_replace_active_history(query_client, interrupt):
    path, client, plan = query_client
    started, release = Event(), Event()

    def provider(body):
        if body['messages'][-1]['content'] == '未完成的编辑':
            started.set()
            assert release.wait(5)
        return {'plan':{'metric':'revenue','year':2026,'division':'北京'}}

    plan(provider)
    async with client() as api:
        sid = await new_session(api)
        origin = (await ask(api,sid,'原问题')).json()
        edit_params = {'operation':'edit','origin_id':origin['id'],'request_id':'interrupted-edit'}
        replies = []

        async def edit():
            replies.append(await ask(api,sid,'未完成的编辑',**edit_params))

        async with anyio.create_task_group() as group:
            group.start_soon(edit)
            try:
                assert await anyio.to_thread.run_sync(started.wait, 4)
                if interrupt == 'delete':
                    assert (await api.delete(f'/api/sessions/{sid}')).status_code == 204
                else:
                    with connection(path) as db:
                        db.execute('UPDATE turns SET created_at=? WHERE request_id=?',
                                   ((utc_now()-timedelta(minutes=20)).isoformat(),'interrupted-edit'))
                    assert (await api.get(f'/api/sessions/{sid}/messages')).json() == [origin]
                    retry = (await ask(api,sid,'未完成的编辑',**edit_params)).json()
                    assert retry['result']['code'] == 'request_interrupted' and retry['active'] is False
            finally:
                release.set()
        assert replies[0].json()['error']['code'] == 'query_obsolete'
        history = await api.get(f'/api/sessions/{sid}/messages')
        if interrupt == 'delete':
            assert history.status_code == 404
        else:
            assert history.json() == [origin]
            assert (await ask(api,sid,'新问题')).json()['status'] == 'ok'
