"""Business data catalog with explicit availability and table scope."""

from fastapi import APIRouter, Depends

from app.api import settings_for
from app.config import Settings
from app.database import connection, initialize

router = APIRouter()

SOURCE_CATALOG = {
    'sales': ('商业市场台账', '台账', ('合同签订日期','经营单元','地区','行业大类','行业','产品线','产品型号','签约额','确认收入','回款'), ('contracts','monthly_sales','divisions','products')),
    'projects': ('PPL明细台账', '台账', ('项目','风险等级','经营单元','落地日期','阶段'), ('projects','divisions')),
    'targets': ('整体目标台账', '台账', ('经营单元','目标年度','商业目标','商解目标'), ('annual_targets','divisions')),
    'attainment': ('整体达成', '报表', (), ()),
    'product-analysis': ('产品分析', '报表', (), ()),
    'solution': ('商解专项', '报表', (), ()),
    'industry-analysis': ('行业达成', '报表', (), ()),
    'key-divisions': ('重点单元', '报表', (), ()),
}


def catalog(settings):
    initialize(settings.database_path)
    with connection(settings.database_path) as db:
        metadata = {row['id']: dict(row) for row in db.execute('SELECT * FROM dataset')}
    return [{
        'id': key, 'name': label, 'group': group, 'fields': fields,
        'available': bool(tables and key in metadata),
        'as_of': metadata.get(key, {}).get('as_of'),
        'version': metadata.get(key, {}).get('version'),
        'amount_unit': '人民币分' if key in ('sales','targets') else None,
    } for key, (label, group, fields, tables) in SOURCE_CATALOG.items()]


@router.get('/sources')
def sources(settings: Settings = Depends(settings_for)):
    return catalog(settings)
