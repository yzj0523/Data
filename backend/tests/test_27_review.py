import pytest

from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_filters_pagination_and_review_preserve_snapshot(query_client):
    _, client, plan = query_client
    plan({'plan':{'metric':'revenue','year':2026}})
    async with client() as api:
        sid = await new_session(api)
        for index in range(6):
            turn = (await ask(api,sid,f'收入 {index}')).json()
            assert (await api.post('/api/feedbacks', json={'turn_id':turn['id']})).status_code == 201
        url = '/api/feedbacks?question=收入&reporter=演示&status=pending&page_size=5&page=2'
        pending = (await api.get(url)).json()
        assert pending['total'] == 6 and pending['page'] == 2 and len(pending['items']) == 1
        target = pending['items'][0]['id']
        old = (await api.get(f'/api/feedbacks/{target}')).json()
        revised = (await api.patch(f'/api/feedbacks/{target}',json={'status':'resolved','notes':'已核对 <标签>'})).json()
        assert revised['answer'] == old['answer']
        pending = (await api.get(url)).json()
        assert pending['total'] == 5 and pending['page'] == 1
        for size in (10,20):
            assert (await api.get(f'/api/feedbacks?page_size={size}')).json()['total'] == 6
        assert (await api.get('/api/feedbacks?reporter=其他')).json()['total'] == 0
    async with client() as api:
        assert (await api.get(f'/api/feedbacks/{target}')).json() == revised
