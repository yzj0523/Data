import pytest

from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_suggestions_follow_the_preference_and_query_status(query_client):
    _, client, plan = query_client
    async with client() as api:
        sid = await new_session(api)
        plan({'plan':{'metric':'revenue','year':2026}})
        result = (await ask(api,sid)).json()['result']
        assert len(set(result['suggestions'])) == 3
        assert all('确认收入' in question for question in result['suggestions'])
        plan({'changes':{'group':'month'}})
        assert (await ask(api,sid,result['suggestions'][1])).json()['result']['rows'][0] == ['2026-01',6500]
        plan({'plan':{'metric':'revenue','year':2020}})
        assert 'suggestions' not in (await ask(api,sid)).json()['result']
        config = (await api.get('/api/app-config')).json()
        await api.put('/api/app-config',json=config | {'suggestions_enabled':False})
    async with client() as api:
        plan({'plan':{'metric':'revenue','year':2026}})
        assert 'suggestions' not in (await ask(api,sid)).json()['result']


@pytest.mark.parametrize(('metric','expected'), [('commercial_target',6000),('solution_target',1000)])
async def test_target_suggestions_stay_within_the_target_source(query_client, metric, expected):
    _, client, plan = query_client
    plan({'plan':{'metric':metric,'year':2026,'division':'北京'}})
    async with client() as api:
        sid = await new_session(api)
        turn = (await ask(api,sid,'北京年度目标',sources=['targets'])).json()
        assert turn['result']['rows'] == [['北京代表处',expected]]
        suggestions = turn['result']['suggestions']
        assert len(set(suggestions)) == 3
        actions = [
            ('按经营单元',{'group':'division'},'北京代表处','bar'),
            ('合计',{'group':'total'},'合计','bar'),
            ('条形图',{'chart':'horizontal'},'合计','horizontal'),
        ]
        for text, (wording, changes, label, chart) in zip(suggestions,actions,strict=True):
            assert wording in text
            plan({'changes':changes})
            followup = (await ask(api,sid,text,sources=['targets'])).json()
            assert followup['status'] == 'ok'
            assert followup['result']['rows'] == [[label,expected]]
            assert followup['result']['chart']['type'] == chart
            assert [source['id'] for source in followup['result']['execution']['sources']] == ['targets']
