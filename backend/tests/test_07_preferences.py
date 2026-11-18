import pytest

from test_05_sessions import client_factory

pytestmark = pytest.mark.anyio


async def test_preferences_validation_and_persistence(client_factory):
    _, client = client_factory
    async with client() as api:
        url = '/api/app-config'
        config = (await api.get(url)).json()
        assert config['hot_threshold'] == 3
        config.update(opening_questions=['问'*100]*10, hot_threshold=2, greeting_enabled=False)
        assert (await api.put(url, json=config)).json() == config
        for change in ({'opening_questions':['问']*11}, {'opening_questions':['问'*101]},
                       {'hot_threshold':1.5}, {'hot_threshold':0}, {'greeting':'   '}, {'speech':True}):
            assert (await api.put(url, json=config | change)).status_code == 422
        assert (await api.get(url)).json() == config
        assert (await api.put(url, json=config | {'opening_questions':[]})).status_code == 200
    async with client() as api:
        assert (await api.get(url)).json() == config | {'opening_questions':[]}
