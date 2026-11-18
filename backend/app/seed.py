"""Install versioned, synthetic demonstration data without replacing user state."""

from app.config import ConfigurationError, load_settings
from app.database import connection, initialize

VERSION = 'demo-1'
DIVISIONS = [('bj', '北京代表处', '北京'), ('sh', '上海代表处', '上海'), ('sz', '深圳代表处', '深圳'), ('hz', '杭州代表处', '杭州'), ('cd', '成都代表处', '成都')]
PRODUCTS = [('p1', '通用计算', 'GC-100'), ('p2', '智能计算', 'IC-200'), ('p3', '商业解决方案', 'BS-300'), ('p4', '智能计算', 'IC-400')]
CONTRACTS = [
    ('c1','bj','p1','政企','教育','2026-01-19',4000000000,3600000000,0),
    ('c2','bj','p3','政企','教育','2026-02-09',1300000000,1200000000,1),
    ('c3','sh','p2','政企','交通','2026-01-12',5500000000,5000000000,0),
    ('c4','sz','p3','商业市场','零售','2026-03-16',3300000000,3000000000,1),
    ('c5','hz','p4','政企','医疗','2026-04-04',1100000000,1000000000,0),
    ('c6','cd','p4','商业市场','制造','2026-05-08',1100000000,None,0),
    ('c7','bj','p1','政企','教育','2025-01-19',3300000000,3000000000,0),
    ('c8','sh','p2','政企','交通','2025-01-12',4400000000,4000000000,0),
    ('c9','sz','p3','商业市场','零售','2025-02-10',1100000000,1000000000,1),
    ('c10','sh','p2','政企','交通','2025-09-21',9900000000,9000000000,0),
]
MONTHLY = [
    ('c1','2026-01-01',2000000000,1800000000,1400000000),
    ('c1','2026-02-01',500000000,450000000,100000000),
    ('c2','2026-02-01',500000000,460000000,None),
    ('c3','2026-01-01',4500000000,4000000000,3500000000),
    ('c3','2026-03-01',500000000,450000000,400000000),
    ('c4','2026-03-01',1000000000,900000000,650000000),
    ('c4','2026-05-01',0,0,0),
    ('c5','2026-06-01',1000000000,900000000,400000000),
    ('c6','2026-07-01',1000000000,900000000,300000000),
    ('c7','2025-01-01',2500000000,2250000000,900000000),
    ('c8','2025-01-01',3800000000,3400000000,2900000000),
    ('c9','2025-02-01',0,0,0),
    ('c10','2025-09-01',8000000000,7200000000,4000000000),
]
TARGETS = [('bj',2026,6000000000,1000000000),('sh',2026,6000000000,0),('sz',2026,3500000000,1600000000),('hz',2026,2000000000,None),('bj',2025,5500000000,900000000)]
PROJECTS = [
    ('j1','北京教育算力升级','bj','c1','2026-04-15','高风险','执行中'),
    ('j2','上海交通数据平台','sh','c3','2026-02-20','低风险','已落地'),
    ('j3','深圳零售方案','sz','c4',None,'中风险','评估中'),
    ('j4','杭州智慧医疗','hz','c5',None,'高风险','评估中'),
    ('j5','成都制造算力','cd','c6','2026-08-26','高风险','执行中'),
]


def seed(path):
    initialize(path)
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM dataset WHERE version = ?', (VERSION,)).fetchone():
            return
        for table, rows in (
            ('divisions', DIVISIONS), ('products', PRODUCTS), ('contracts', CONTRACTS),
            ('monthly_sales', MONTHLY), ('annual_targets', TARGETS), ('projects', PROJECTS),
            ('dataset', [(source, VERSION, '2026-08-31') for source in ('sales', 'targets', 'projects')]),
        ):
            placeholders = ','.join('?' for _ in rows[0])
            db.executemany(f'INSERT INTO {table} VALUES ({placeholders})', rows)


def main():
    try:
        seed(load_settings().database_path)
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    print(f'Demonstration data {VERSION} ready')


if __name__ == '__main__':
    main()
