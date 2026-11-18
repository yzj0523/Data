import json

import httpx
import pytest

from app.seed import seed
from test_05_sessions import client_factory
from test_08_models import PAYLOAD
from test_09_provider import Wire, use_provider
from test_10_queries import ask, new_session

pytestmark = pytest.mark.anyio


async def test_execution_uses_persisted_model_only_when_enabled(client_factory, monkeypatch):
    path, client = client_factory
    seed(path)
    monkeypatch.setenv('AI_DEFAULT_MODEL_BASE_URL', 'https://model.example/v1')
    monkeypatch.setenv('AI_DEFAULT_MODEL_NAME', '默认模型')
    monkeypatch.setenv('AI_DEFAULT_MODEL_API_KEY', 'default-test-key')

    transmitted = []
    def upstream(request):
        transmitted.append((json.loads(request.content)['model'],request.headers['Authorization']))
        content = json.dumps({'plan':{'metric':'revenue','year':2026}})
        return httpx.Response(200, stream=Wire({'choices':[{'message':{'content':content}}]}))

    use_provider(monkeypatch, upstream)
    async with client() as api:
        session = await new_session(api)
        model = (await api.post('/api/models',json=PAYLOAD)).json()
        await api.put('/api/models/selection',json={'model_id':model['id']})
        config = (await api.get('/api/app-config')).json()
        assert (await ask(api,session)).json()['result']['execution']['model'] == '默认模型'
        await api.put('/api/app-config',json=config | {'custom_model_enabled':True})
    async with client() as api:
        answer = await ask(api,session)
        assert answer.json()['result']['execution']['model'] == PAYLOAD['name']
        assert PAYLOAD['api_key'] not in answer.text
    assert transmitted == [('默认模型','Bearer default-test-key'),(PAYLOAD['name'],'Bearer '+PAYLOAD['api_key'])]
