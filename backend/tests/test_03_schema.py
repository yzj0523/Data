import sqlite3

import pytest

from app.database import initialize


def test_business_schema_preserves_contract_grain_and_exact_amount(tmp_path):
    path = tmp_path / 'sales.sqlite3'
    initialize(path)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute("INSERT INTO divisions VALUES ('bj', '北京代表处', '北京')")
        db.execute("INSERT INTO products VALUES ('p', '服务器', '型号A')")
        db.execute("INSERT INTO contracts VALUES ('c1','bj','p','政企','教育','2026-01-31',10101,8939,1)")
        db.execute("INSERT INTO contracts VALUES ('c2','bj','p','政企','交通','2026-02-02',200,177,0)")
        db.executemany('INSERT INTO monthly_sales VALUES (?,?,?,?,?)', [
            ('c1', '2026-01-01', 7001, 6196, None), ('c1', '2026-02-01', 3100, 2743, 100),
        ])
        db.execute("INSERT INTO annual_targets VALUES ('bj',2026,100000,50000)")
        db.execute("INSERT INTO projects VALUES ('a','项目A','bj','c1','2026-03-01','高风险','执行中')")
        assert db.execute('SELECT SUM(revenue_cents),COUNT(*) FROM monthly_sales').fetchone() == (10101, 2)
        assert db.execute('SELECT SUM(commercial_cents) FROM annual_targets').fetchone() == (100000,)
        assert db.execute('SELECT industry_group,industry,signed_on,landed_on FROM contracts JOIN projects ON contracts.id=projects.contract_id').fetchone() == ('政企', '教育', '2026-01-31', '2026-03-01')
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO monthly_sales VALUES ('c1','2026-01-01',1,1,1)")
