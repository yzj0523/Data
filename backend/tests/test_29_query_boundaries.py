import sqlite3

import httpx
import pytest

from test_05_sessions import client_factory
from test_09_provider import use_provider
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_limits_reject_overflow_and_preserve_admitted_history(query_client, monkeypatch):
    path, client, plan = query_client
    monkeypatch.setenv('AI_QUESTION_MAX_LENGTH','6')
    monkeypatch.setenv('AI_QUERY_MAX_ROWS','2')
    async with client() as api:
        sid = await new_session(api)
        plan({'plan':{'metric':'revenue','year':2026,'group':'product_model'}})
        assert (await ask(api,sid,'查确认收入额啊')).status_code == 422
        large = (await ask(api,sid,'确认收入')).json()
        assert large['status'] == 'failed' and large['result']['code'] == 'query_row_limit'
        plan({'plan':{'metric':'revenue','year':2026,'top':2}})
        assert (await ask(api,sid,'前两名')).json()['result']['rows'] == [['上海代表处',5000],['北京代表处',3000]]
        plan({'changes':{'untrusted_nested_plan':{'table':'preferences'}}})
        invalid = (await ask(api,sid,'改筛选')).json()
        assert invalid['result']['code'] == 'model_plan_invalid'
        assert len((await api.get(f'/api/sessions/{sid}/messages')).json()) == 3
        with sqlite3.connect(path) as db:
            db.execute("UPDATE dataset SET as_of='not-a-date' WHERE id='sales'")
        plan({'plan':{'metric':'revenue','year':2026}})
        assert (await ask(api,sid,'查收入')).json()['result']['code'] == 'query_unavailable'


async def test_provider_timeout_and_network_disconnect_are_visible_in_history(query_client, monkeypatch):
    _, client, _ = query_client
    for failure, code in ((httpx.ReadTimeout, 'model_timeout'), (httpx.ReadError, 'model_connection')):
        def fail(request):
            raise failure('supplier secret must not be included')
        use_provider(monkeypatch, fail)
        async with client() as api:
            sid = await new_session(api)
            answer = (await ask(api,sid)).json()
            assert answer['status'] == 'failed' and answer['result']['code'] == code
            response = await api.get(f'/api/sessions/{sid}/messages')
            assert response.json() == [answer] and 'supplier secret' not in response.text
