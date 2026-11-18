import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx


SERVER = '''
import json
from urllib.parse import urlsplit

import httpx

from app import provider
from app.__main__ import main


class ResponseBody(httpx.SyncByteStream):
    def __iter__(self):
        answer = {"plan": {"metric": "revenue", "year": 2026, "division": "北京"}}
        yield json.dumps({"choices": [{"message": {"content": json.dumps(answer)}}]}).encode()


provider.public_endpoint = lambda url: (urlsplit(url), '93.184.215.14')
provider.http_client = lambda timeout: httpx.Client(transport=httpx.MockTransport(
    lambda request: httpx.Response(200, stream=ResponseBody())
))
raise SystemExit(main())
'''


@contextmanager
def real_server(env, root):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port = listener.getsockname()[1]
    process = subprocess.Popen([sys.executable,'-c',SERVER], cwd=root, env=env | {'AI_PORT':str(port)},
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3,trust_env=False) as api:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Test server exited during startup')
                try:
                    api.get('/api/health').raise_for_status()
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            yield api
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_seed_and_real_process_restart_preserve_demo_records(tmp_path):
    env = os.environ.copy() | {
        'AI_DATABASE_PATH':str(tmp_path / 'persistent.sqlite3'), 'AI_LOG_LEVEL':'warning',
        'AI_DEFAULT_MODEL_BASE_URL':'https://model.example/v1', 'AI_DEFAULT_MODEL_NAME':'fixture',
        'AI_DEFAULT_MODEL_API_KEY':'fixture-key',
    }
    subprocess.run([sys.executable,'-m','app.seed'],cwd=tmp_path,env=env,check=True,timeout=10)
    with real_server(env,tmp_path) as api:
        session = api.post('/api/sessions',json={'title':'重启前会话'}).raise_for_status().json()
        turn = api.post(f'/api/sessions/{session["id"]}/queries',json={
            'request_id':'persistent','question':'北京代表处 2026 年确认收入','source_ids':['sales'],
        }).raise_for_status().json()
        assert turn['result']['rows'] == [['北京代表处',3000]]
        report = api.post('/api/feedbacks',json={'turn_id':turn['id']}).raise_for_status().json()
        api.put('/api/favorites',json={'enabled':True,'question':turn['question']}).raise_for_status()
        preferences = api.get('/api/app-config').raise_for_status().json() | {'greeting':'重启后保留'}
        api.put('/api/app-config',json=preferences).raise_for_status()
    subprocess.run([sys.executable,'-m','app.seed'],cwd=tmp_path,env=env,check=True,timeout=10)
    with real_server(env,tmp_path) as api:
        assert api.get('/api/sessions').raise_for_status().json()[0]['id'] == session['id']
        assert api.get(f'/api/sessions/{session["id"]}/messages').raise_for_status().json() == [turn]
        assert api.get('/api/favorites').raise_for_status().json() == [turn['question']]
        assert api.get('/api/app-config').raise_for_status().json() == preferences
        assert api.get(f'/api/feedbacks/{report["id"]}').raise_for_status().json() == report
