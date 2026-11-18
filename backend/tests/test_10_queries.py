import json
import sqlite3
from uuid import uuid4

import httpx
import pytest

from app.seed import seed
from test_05_sessions import client_factory
from test_09_provider import Wire, use_provider

pytestmark = pytest.mark.anyio


@pytest.fixture
def query_client(client_factory, monkeypatch):
    path, client = client_factory
    seed(path)
    for key,value in {'BASE_URL':'https://model.example/v1','NAME':'demo','API_KEY':'test-key'}.items():
        monkeypatch.setenv(f'AI_DEFAULT_MODEL_{key}', value)

    def set_plan(plan):
        def handler(request):
            body = json.loads(request.content)
            content = plan(body) if callable(plan) else plan
            return httpx.Response(200, stream=Wire({'choices':[{'message':{'content':json.dumps(content)}}]}))
        use_provider(monkeypatch, handler)

    return path, client, set_plan


async def ask(api, session, question='经营单元确认收入', sources=None, **extra):
    return await api.post(f'/api/sessions/{session}/queries', json={
        'request_id':uuid4().hex,'question':question,'source_ids':['sales'] if sources is None else sources,**extra,
    })


async def new_session(api):
    return (await api.post('/api/sessions', json={})).json()['id']


async def test_model_plan_drives_actual_database_and_history(query_client):
    path, client, set_plan = query_client
    set_plan(lambda body: {'plan':{'metric':'revenue','year':2025 if '2025' in body['messages'][-1]['content'] else 2026, 'division':'北京'}})
    async with client() as api:
        session = await new_session(api)
        first = (await ask(api, session,'2026年北京确认收入')).json()
        second = (await ask(api, session,'北京 2025 年收入多少')).json()
        with sqlite3.connect(path) as db:
            expected = db.execute("SELECT SUM(revenue_cents) FROM monthly_sales JOIN contracts ON id=contract_id WHERE division_id='bj' AND period LIKE '2026-%'").fetchone()[0] / 1_000_000
        assert first['result']['rows'] == [['北京代表处',expected]] == [['北京代表处',3000]]
        assert second['result']['rows'] == [['北京代表处',2500]]
    async with client() as api:
        assert (await api.get(f'/api/sessions/{session}/messages')).json() == [first,second]


async def test_scope_empty_and_untrusted_raw_sql(query_client, monkeypatch):
    path, client, set_plan = query_client
    async with client() as api:
        session = await new_session(api)
        assert (await ask(api, session, sources=[])).status_code == 422
        set_plan({'plan':{'metric':'revenue','year':2020}})
        assert (await ask(api,session,sources=['targets'])).json()['result']['code'] == 'source_scope'
        assert (await ask(api,session)).json()['status'] == 'empty'
        set_plan({'plan':{'metric':'revenue','year':2026,'sql':'raw SQL is forbidden'}})
        assert (await ask(api,session)).json()['result']['code'] == 'model_plan_invalid'
        monkeypatch.delenv('AI_DEFAULT_MODEL_API_KEY')
    async with client() as api:
        assert (await ask(api,session)).json()['result']['code'] == 'model_unavailable'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM contracts').fetchone() == (10,)
