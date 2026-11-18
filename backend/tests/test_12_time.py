from datetime import date

import pytest

from app import query_plan
from app.database import connection
from test_05_sessions import client_factory
from test_10_queries import ask, new_session, query_client

pytestmark = pytest.mark.anyio


async def test_trends_use_distinct_dates_and_preserve_missing_months(query_client, monkeypatch):
    _, client, plan = query_client
    monkeypatch.setattr(query_plan, 'business_today', lambda: date(2026, 11, 18))
    async with client() as api:
        sid = await new_session(api)
        plan({'plan':{'metric':'revenue','year':'this_year','group':'month','yoy':True}})
        result = (await ask(api,sid)).json()['result']
        rows = {row[0]:row[1:] for row in result['rows']}
        assert rows['2026-01'] == [6500,6300,3.17]
        assert rows['2026-02'] == [1000,0,None]
        assert rows['2026-05'] == [0,None,None]
        assert '2026-04' not in rows and '2026-09' not in rows
        assert result['execution']['date_end_exclusive'] == '2026-09-01'
        plan({'plan':{'metric':'gross_contract','year':2026,'group':'month'}})
        assert (await ask(api,sid)).json()['result']['rows'][:2] == [['2026-01',9500],['2026-02',1300]]
        plan({'plan':{'metric':'revenue','year':'this_month'}})
        assert (await ask(api,sid)).json()['status'] == 'empty'


@pytest.mark.parametrize(('cutoff','baseline_end','expected'), [
    (date(2024,2,28),'2023-03-01',[200,100,100]),
    (date(2024,2,29),'2023-03-01',[300,100,200]),
    (date(2025,2,28),'2024-03-01',[600,300,100]),
])
async def test_contract_yoy_includes_the_last_day_of_the_comparable_month(query_client, monkeypatch, cutoff, baseline_end, expected):
    path, client, plan = query_client
    monkeypatch.setattr(query_plan, 'business_today', lambda: cutoff)
    with connection(path) as db:
        db.executemany("""INSERT INTO contracts (id,division_id,product_id,industry_group,industry,signed_on,gross_cents)
                       VALUES (?,'bj','p1','测试','测试',?,?)""", [
            ('a','2023-02-28',100_000_000),
            ('b','2023-03-01',900_000_000),
            ('c','2024-02-28',200_000_000),
            ('d','2024-02-29',100_000_000),
            ('e','2024-03-01',900_000_000),
            ('f','2025-02-28',600_000_000),
        ])
        baseline = db.execute("""SELECT SUM(gross_cents) FROM contracts
                              WHERE industry='测试' AND signed_on LIKE ?""", (f'{cutoff.year-1}-02-%',)).fetchone()[0]
    plan({'plan':{'metric':'gross_contract','year':cutoff.year,'month':2,'industry':'测试','group':'total','yoy':True}})
    async with client() as api:
        turn = (await ask(api,await new_session(api),'二月签约额同比')).json()
        assert turn['status'] == 'ok'
        assert baseline/1_000_000 == expected[1]
        assert turn['result']['rows'] == [['合计',*expected]]
        assert turn['result']['execution']['comparison']['parameters'][1] == baseline_end
