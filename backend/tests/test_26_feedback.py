import pytest

from app.database import connection
from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_exact_answer_feedback_survives_edit_and_deletion(query_client):
    _, client, plan = query_client
    plan({'plan':{'metric':'revenue','year':2026,'division':'北京'}})
    async with client() as api:
        sid = await new_session(api)
        first = (await ask(api,sid,'早期答案')).json()
        await ask(api,sid,'后续答案')
        response = await api.post('/api/feedbacks',json={'turn_id':first['id']})
        assert response.status_code == 201
        feedback = response.json()
        assert feedback['question'] == '早期答案' and feedback['answer'] == first['result']
        await ask(api,sid,'已修改',operation='edit',origin_id=first['id'])
        await api.delete(f'/api/sessions/{sid}')
    async with client() as api:
        assert (await api.get(f'/api/feedbacks/{feedback["id"]}')).json() == feedback


async def test_feedback_transport_retry_is_idempotent_after_answer_deletion(query_client):
    _, client, plan = query_client
    plan({'plan':{'metric':'revenue','year':2026,'division':'北京'}})
    async with client() as api:
        sid = await new_session(api)
        first, second = [(await ask(api,sid,f'答案{i}')).json()['id'] for i in range(2)]
        payload = {'turn_id':first,'request_id':'report-attempt'}
        created = await api.post('/api/feedbacks',json=payload)
        assert created.status_code == 201
        distinct = await api.post('/api/feedbacks',json=payload | {'request_id':'different-attempt'})
        assert distinct.status_code == 409 and distinct.json()['error']['code'] == 'feedback_exists'
        conflict = await api.post('/api/feedbacks',json=payload | {'turn_id':second})
        assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'request_conflict'
        await api.delete(f'/api/sessions/{sid}')
        assert (await api.post('/api/feedbacks',json=payload)).json() == created.json()
        assert (await api.get('/api/feedbacks')).json()['total'] == 1


async def test_feedback_upgrade_preserves_existing_snapshot_and_review(query_client):
    path, client, _ = query_client
    with connection(path) as db:
        db.execute('''CREATE TABLE feedback (id TEXT PRIMARY KEY, turn_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, reporter TEXT NOT NULL,
                    status TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        db.execute('INSERT INTO feedback VALUES (?,?,?,?,?,?,?,?,?,?)', (
            'old-feedback','removed-turn','removed-session','旧问题','{"summary":"旧答案"}','演示用户',
            'resolved','已核对','2026-08-30','2026-08-31',
        ))
    async with client() as api:
        response = await api.get('/api/feedbacks/old-feedback')
        assert response.status_code == 200
        assert response.json() == {'id':'old-feedback','turn_id':'removed-turn','session_id':'removed-session',
                                   'question':'旧问题','answer':{'summary':'旧答案'},'reporter':'演示用户',
                                   'status':'resolved','notes':'已核对','created_at':'2026-08-30','updated_at':'2026-08-31'}
