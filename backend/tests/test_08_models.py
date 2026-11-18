import socket
import sqlite3

import pytest

from test_05_sessions import client_factory

pytestmark = pytest.mark.anyio
PAYLOAD = {'name':'演示模型','base_url':'https://model.example/v1', 'api_key':'model-test-secret-unique'}


async def test_model_selection_persists_without_plaintext_key(client_factory, monkeypatch, caplog):
    path, client = client_factory
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',('93.184.215.14',443))])
    async with client() as api:
        assert (await api.get('/api/models')).json()['default_name'] is None
        added = await api.post('/api/models', json=PAYLOAD)
        assert added.status_code == 201 and PAYLOAD['api_key'] not in added.text
        model_id = added.json()['id']
        assert (await api.put('/api/models/selection', json={'model_id':'missing'})).status_code == 404
        assert (await api.put('/api/models/selection', json={'model_id':model_id})).status_code == 200
        for address in ('http://model.example', 'https://127.0.0.1', 'https://[::1]', 'https://localhost'):
            assert (await api.post('/api/models', json=PAYLOAD | {'base_url':address})).status_code == 422
    async with client() as api:
        response = await api.get('/api/models')
        assert response.json()['selected_id'] == model_id
        assert PAYLOAD['api_key'] not in response.text + caplog.text
    assert PAYLOAD['api_key'].encode() not in path.read_bytes()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT encrypted_key FROM model_registry').fetchone()[0] != PAYLOAD['api_key'].encode()
