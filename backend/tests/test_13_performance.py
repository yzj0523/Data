from datetime import date

import pytest

from app.database import connection
from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_target_rate_and_risk_query_match_database_grain(query_client):
    _, client, plan = query_client
    async with client() as api:
        sid = await new_session(api)
        for metric, expected in [('commercial_rate',[80,4800,6000]),('solution_rate',[46,460,1000])]:
            plan({'plan':{'metric':metric,'year':2026,'division':'北京'}})
            assert (await ask(api,sid,sources=['sales','targets'])).json()['result']['rows'] == [['北京代表处',*expected]]
            assert (await ask(api,sid,sources=['sales'])).json()['result']['code'] == 'source_scope'
        plan({'plan':{'metric':'solution_rate','year':2026,'division':'上海'}})
        assert (await ask(api,sid,sources=['sales','targets'])).json()['status'] == 'clarification'
        plan({'plan':{'metric':'risk_count','group':'total'}})
        assert (await ask(api,sid,sources=['projects'])).json()['result']['rows'] == [['合计',3]]
        plan({'plan':{'metric':'risk_details','group':'total'}})
        assert [row[0] for row in (await ask(api,sid,sources=['projects'])).json()['result']['rows']] == ['j1','j4','j5']


@pytest.mark.parametrize(('metric','sql','target'), [
    ('commercial_rate', "UPDATE contracts SET net_cents=NULL WHERE id='c2'",6000),
    ('solution_rate', "UPDATE monthly_sales SET net_revenue_cents=NULL WHERE contract_id='c2' AND period='2026-03-01'",1000),
])
async def test_missing_amount_suppresses_rate_and_partial_total(query_client, metric, sql, target):
    path, client, plan = query_client
    with connection(path) as db:
        db.execute("INSERT INTO monthly_sales (contract_id,period,net_revenue_cents) VALUES ('c2','2026-03-01',0)")
        db.execute("INSERT INTO annual_targets VALUES ('cd',2026,100000000,100000000)")
        db.execute("UPDATE annual_targets SET solution_cents=100000000 WHERE division_id IN ('sh','hz') AND year=2026")
        db.execute(sql)
    async with client() as api:
        sid = await new_session(api)
        for group, label in [('division','北京代表处'),('total','合计')]:
            plan({'plan':{'metric':metric,'year':2026,'division':'北京','group':group}})
            result = (await ask(api,sid,sources=['sales','targets'])).json()['result']
            assert result['rows'] == [[label,None,None,target]]
            assert '实际金额缺失' in result['summary'] and result['chart'] is None
        plan({'plan':{'metric':metric,'year':2026,'group':'total'}})
        assert (await ask(api,sid,sources=['sales','targets'])).json()['result']['rows'] == [
            ['合计',None,None,17600 if metric == 'commercial_rate' else 2900],
        ]


async def test_risk_relative_and_absolute_period_use_same_landing_date_filter(query_client, monkeypatch):
    _, client, plan = query_client
    monkeypatch.setattr('app.query_plan.business_today', lambda: date(2026,11,18))
    async with client() as api:
        sid = await new_session(api)
        for year, count in [(None,3),('this_year',2),(2026,2)]:
            for metric in ('risk_count','risk_details'):
                plan({'plan':{'metric':metric,'year':year,'group':'total'}})
                result = (await ask(api,sid,sources=['projects'])).json()['result']
                if metric == 'risk_count':
                    assert result['rows'] == [['合计',count]]
                else:
                    assert [row[0] for row in result['rows']] == (['j1','j4','j5'] if year is None else ['j1','j5'])
                assert ('date_start' in result['execution']) == (year is not None)
                assert ('落地日期缺失' in result['execution']['definition']) == (year is not None)


async def test_target_amount_uses_only_target_source_and_preserves_zero_and_missing(query_client):
    _, client, plan = query_client
    async with client() as api:
        sid = await new_session(api)
        for metric, group, division, expected in [
            ('commercial_target','total',None,[['合计',17500]]),
            ('solution_target','division','北京',[['北京代表处',1000]]),
            ('solution_target','division','上海',[['上海代表处',0]]),
            ('solution_target','total',None,[['合计',None]]),
        ]:
            plan({'plan':{'metric':metric,'year':2026,'group':group,'division':division}})
            result = (await ask(api,sid,sources=['targets'])).json()['result']
            assert result['rows'] == expected
            assert [source['id'] for source in result['execution']['sources']] == ['targets']
            assert result['execution']['date_end_exclusive'] == '2027-01-01'
            if expected[0][1] is None:
                assert '目标金额缺失' in result['summary']
            assert (await ask(api,sid,sources=['sales'])).json()['result']['code'] == 'source_scope'
