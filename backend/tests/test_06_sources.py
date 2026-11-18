import pytest

from app.seed import seed
from test_05_sessions import client_factory

pytestmark = pytest.mark.anyio


async def test_catalog_reports_real_dataset_availability(client_factory):
    path, client = client_factory
    async with client() as api:
        initial = (await api.get('/api/sources')).json()
        assert len(initial) == 8 and not any(item['available'] for item in initial)
        seed(path)
        sources = {s['id']:s for s in (await api.get('/api/sources')).json()}
        assert {k for k,s in sources.items() if s['available']} == {'sales','targets','projects'}
        assert sources['sales']['name'] == '商业市场台账'
        assert sources['sales']['as_of'] == '2026-08-31'
        assert sources['sales']['amount_unit'] == '人民币分'
        assert {'行业','行业大类'} <= set(sources['sales']['fields'])
        assert sources['key-divisions']['available'] is False
