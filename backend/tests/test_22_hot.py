import pytest

from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_hot_threshold_normalization_and_duplicate_request(query_client):
    _, client, plan = query_client
    plan({'plan':{'metric':'revenue','year':2026}})
    async with client() as api:
        sid = await new_session(api)
        for number in range(4):
            assert (await ask(api,sid,' 收入 ',request_id=str(number))).json()['status'] == 'ok'
            if number == 2:
                assert (await api.get('/api/questions/hot')).json() == []
        await ask(api,sid,'收入',request_id='3')
        assert (await api.get('/api/questions/hot')).json() == [{'question':'收入','count':4}]
    async with client() as api:
        assert (await api.get('/api/questions/hot')).json() == [{'question':'收入','count':4}]
        config = (await api.get('/api/app-config')).json()
        await api.put('/api/app-config',json=config | {'hot_enabled':False})
        assert (await api.get('/api/questions/hot')).json() == []
        await api.put('/api/app-config',json=config | {'hot_threshold':4})
        assert (await api.get('/api/questions/hot')).json() == []
