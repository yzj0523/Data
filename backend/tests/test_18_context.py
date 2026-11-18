import pytest

from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_followups_change_only_requested_scope(query_client):
    _, client, plan = query_client
    async with client() as api:
        first = await new_session(api)
        plan({'plan':{'metric':'revenue','year':2026,'group':'product_line'}})
        assert (await ask(api,first)).json()['status'] == 'ok'
    async with client() as api:
        plan({'changes':{'division':'北京'}})
        assert (await ask(api,first,'北京呢')).json()['result']['statistics']['total'] == 3000
        plan({'changes':{'year':2025}})
        assert (await ask(api,first,'改成2025年')).json()['result']['rows'] == [['通用计算',2500]]
        plan({'changes':{'chart':'pie'}})
        assert (await ask(api,first,'用饼图')).json()['result']['chart']['type'] == 'pie'
        assert (await ask(api,await new_session(api),'用饼图')).json()['status'] == 'clarification'
        assert (await ask(api,first,'改成饼图',sources=['sales','targets'])).json()['status'] == 'clarification'
