from datetime import date

import pytest

from test_10_queries import ask, new_session, query_client
from test_05_sessions import client_factory

pytestmark = pytest.mark.anyio


async def test_monthly_top_n_ranks_before_limiting_and_charts_in_time_order(query_client, monkeypatch):
    _, client, plan = query_client
    monkeypatch.setattr('app.query_plan.business_today', lambda: date(2026,11,18))
    base = {'metric':'gross_contract','year':2026,'group':'month','chart':'line'}
    async with client() as api:
        sid = await new_session(api)
        for extra, expected in [
            ({},[['2026-01',9500],['2026-02',1300],['2026-03',3300],['2026-04',1100],['2026-05',1100]]),
            ({'top':2},[['2026-01',9500],['2026-03',3300]]),
            ({'top':3,'direction':'ascending'},[['2026-04',1100],['2026-05',1100],['2026-02',1300]]),
        ]:
            plan({'plan':base | extra})
            result = (await ask(api,sid)).json()['result']
            assert result['rows'] == expected
            assert [point['label'] for point in result['chart']['points']] == sorted(row[0] for row in expected)
        plan({'plan':base | {'top':1,'direction':'ascending'}})
        assert (await ask(api,sid)).json()['status'] == 'clarification'


async def test_aggregated_interval_rank_and_ambiguity(query_client):
    _, client, plan = query_client
    async with client() as api:
        sid = await new_session(api)
        plan({'plan': {'metric':'revenue','year':2026,'industry_group':'政企','group':'division','min_wan':3000,'max_wan':5000}})
        assert (await ask(api,sid)).json()['result']['rows'] == [['上海代表处',5000],['北京代表处',3000]]
        plan({'plan': {'metric':'gross_contract','year':2026,'group':'product_model','top':2}})
        assert (await ask(api,sid)).json()['result']['rows'] == [['IC-200',5500],['BS-300',4600]]
        plan({'plan': {'metric':'revenue','year':2026,'group':'product_line','top':10}})
        assert len((await ask(api,sid)).json()['result']['rows']) == 3
        plan({'clarification':True})
        assert (await ask(api,sid,'卖得最好的是？')).json()['status'] == 'clarification'
