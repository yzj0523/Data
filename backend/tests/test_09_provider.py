import json
import socket
from threading import Event

import httpx
import pytest

from app import provider
from test_05_sessions import client_factory
from test_08_models import PAYLOAD

pytestmark = pytest.mark.anyio


class Wire(httpx.SyncByteStream):
    def __init__(self, response):
        self.response = response

    def __iter__(self):
        yield json.dumps(self.response).encode()


def use_provider(monkeypatch, handler):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('93.184.215.14',443))])
    monkeypatch.setattr(provider, 'http_client', lambda timeout: httpx.Client(transport=httpx.MockTransport(handler)))


async def test_probe_obeys_provider_response_and_never_echoes_key(client_factory, monkeypatch):
    _, client = client_factory
    def upstream(request):
        assert request.url.path == '/v1/chat/completions'
        assert request.headers['Host'] == 'model.example'
        assert request.extensions['sni_hostname'] == 'model.example'
        assert request.headers['Authorization'] == 'Bearer ' + PAYLOAD['api_key']
        model = json.loads(request.content)['model']
        if model == 'timeout':
            raise httpx.ReadTimeout('simulated')
        status = {'auth':401,'missing':404,'limit':429,'redirect':302}.get(model,200)
        data = {} if model == 'bad' else {'choices':[{'message':{'content':'OK'}}]}
        return httpx.Response(status, stream=Wire(data), headers={'Location':'https://example.com'})
    use_provider(monkeypatch, upstream)
    async with client() as api:
        for name, code in [('auth','model_auth'),('missing','model_not_found'),('limit','model_rate_limited'),
                           ('timeout','model_timeout'),('bad','model_response'),('redirect','model_rejected')]:
            res = await api.post('/api/models/test', json=PAYLOAD | {'name':name})
            assert res.status_code >= 400 and res.json()['error']['code'] == code
            assert PAYLOAD['api_key'] not in res.text
        assert (await api.post('/api/models/test', json=PAYLOAD)).json() == {'status':'connected','name':PAYLOAD['name']}


async def test_probe_deadline_includes_blocked_dns_and_uses_configured_io_budget(client_factory, monkeypatch):
    _, client = client_factory
    started, unblock, finished = Event(), Event(), Event()
    budgets = []
    monkeypatch.setenv('AI_MODEL_TIMEOUT_SECONDS','0.25')

    def resolve(*args, **kwargs):
        started.set()
        try:
            assert unblock.wait(5)
            return [(2,1,6,'',('93.184.215.14',443))]
        finally:
            finished.set()

    def make_client(timeout):
        budgets.append(timeout)
        return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, stream=Wire({'choices':[{'message':{'content':'OK'}}]}))))

    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(provider, 'http_client', make_client)
    async with client() as api:
        try:
            response = await api.post('/api/models/test', json=PAYLOAD)
            assert started.is_set() and not finished.is_set()
            assert response.status_code == 504 and response.json()['error']['code'] == 'model_timeout'
            assert not budgets
        finally:
            unblock.set()
        assert (await api.post('/api/models/test', json=PAYLOAD)).status_code == 200
        assert len(budgets) == 1 and 0 < budgets[0] <= 0.25


async def test_probe_deadline_includes_stream_body(client_factory, monkeypatch):
    _, client = client_factory
    started, unblock, finished = Event(), Event(), Event()
    monkeypatch.setenv('AI_MODEL_TIMEOUT_SECONDS','0.25')

    class SlowBody(httpx.SyncByteStream):
        def __iter__(self):
            started.set()
            try:
                assert unblock.wait(5)
                yield b'{}'
            finally:
                finished.set()

    use_provider(monkeypatch, lambda _: httpx.Response(200, stream=SlowBody()))
    async with client() as api:
        try:
            response = await api.post('/api/models/test', json=PAYLOAD)
            assert started.is_set() and not finished.is_set()
            assert response.status_code == 504 and response.json()['error']['code'] == 'model_timeout'
        finally:
            unblock.set()
