import pytest

from test_05_sessions import client_factory

pytestmark = pytest.mark.anyio


async def test_favorites_are_persistent_and_idempotent(client_factory):
    _, client = client_factory
    async with client() as api:
        for text in (' 北京收入 ','北京收入'):
            assert (await api.put('/api/favorites',json={'question':text,'enabled':True})).json() == ['北京收入']
    async with client() as api:
        assert (await api.get('/api/favorites')).json() == ['北京收入']
        assert (await api.put('/api/favorites',json={'question':'北京收入','enabled':False})).json() == []
