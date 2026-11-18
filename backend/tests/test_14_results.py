import pytest

from app.database import connection
from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_display_values_execution_and_chart_agree(query_client):
    _, client, plan = query_client
    async with client() as api:
        sid = await new_session(api)
        plan({'plan':{'metric':'revenue','year':2026,'industry_group':'政企','min_wan':3000,'max_wan':5000,'chart':'bar'}})
        r = (await ask(api,sid)).json()['result']
        assert r['statistics'] == {'row_count':2,'total':8000,'average':4000,'maximum':5000,'minimum':3000,'unit':'万元'}
        assert r['chart']['points'] == [{'label':label,'value':value} for label,value in r['rows']]
        assert r['execution']['sources'][0]['as_of'] == '2026-08-31'
        assert r['execution']['row_count'] == 2 and 'tokens' not in r['execution']
        assert '确认收入' in r['execution']['definition']
        assert '8000' in r['summary']
        plan({'plan':{'metric':'revenue','year':2020,'chart':'pie'}})
        r = (await ask(api,sid)).json()['result']
        assert r['rows'] == [] and r['chart'] is None and r['chart_reason']


async def test_incomplete_sales_amounts_keep_affected_groups_visible(query_client):
    path, client, plan = query_client
    with connection(path) as db:
        db.execute("UPDATE contracts SET net_cents=NULL WHERE id='c2'")
        db.execute("UPDATE monthly_sales SET revenue_cents=NULL WHERE contract_id='c7'")
    async with client() as api:
        sid = await new_session(api)
        plan({'plan':{'metric':'net_contract','year':2026,'division':'北京','group':'total','yoy':True}})
        total = (await ask(api,sid)).json()['result']
        assert total['rows'] == [['合计',None,3000,None]]
        assert '匹配的 2 条业务记录中有 1 条金额缺失' in total['summary']
        assert 'total' not in total['statistics'] and total['chart'] is None
        plan({'plan':{'metric':'net_contract','year':2026,'chart':'pie'}})
        grouped = (await ask(api,sid)).json()['result']
        assert ['北京代表处',None] in grouped['rows']
        assert ['成都代表处',None] in grouped['rows']
        assert ['上海代表处',5000] in grouped['rows']
        assert 'total' not in grouped['statistics'] and grouped['chart'] is None
        plan({'plan':{'metric':'paid','year':2026,'division':'深圳','group':'month'}})
        assert ['2026-05',0] in (await ask(api,sid)).json()['result']['rows']
        plan({'plan':{'metric':'revenue','year':2026,'division':'北京','yoy':True}})
        yoy = (await ask(api,sid)).json()['result']
        assert yoy['rows'] == [['北京代表处',3000,None,None]]
        assert '同期有记录的金额缺失' in yoy['summary']


@pytest.mark.parametrize('conditions',[{'top':1},{'min_wan':10000},{'share':True}])
async def test_unknown_sales_amounts_keep_ranking_and_filters_from_reporting_partial_results(query_client, conditions):
    _, client, plan = query_client
    plan({'plan':{'metric':'net_contract','year':2026,**conditions}})
    async with client() as api:
        turn = (await ask(api,await new_session(api))).json()
        assert turn['status'] == 'clarification'
        assert '缺失' in turn['result']['summary']
