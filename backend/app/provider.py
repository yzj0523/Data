"""OpenAI-compatible HTTPS requests and sanitized provider failures."""

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import BoundedSemaphore
from time import monotonic

import httpx
from fastapi import APIRouter, Depends

from app.api import ApiError, settings_for
from app.config import Settings
from app.models import Model, ModelInput, public_endpoint

router = APIRouter()
MAX_RESPONSE_BYTES = 256_000
PROVIDER_WORKERS = 8
provider_slots = BoundedSemaphore(PROVIDER_WORKERS)
provider_workers = ThreadPoolExecutor(max_workers=PROVIDER_WORKERS, thread_name_prefix='model-provider')


def http_client(timeout: float):
    return httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False)


def complete(model: Model, messages: list, *, structured: bool = False, timeout: float = 15):
    deadline = monotonic() + timeout
    try:
        if not provider_slots.acquire(timeout=remaining(deadline)):
            raise TimeoutError
        try:
            future = provider_workers.submit(request_completion, model, messages, structured, deadline)
        except BaseException:
            provider_slots.release()
            raise
        # DNS and socket calls may outlive the caller. Keep their slot until they exit.
        future.add_done_callback(lambda _: provider_slots.release())
        try:
            return future.result(timeout=remaining(deadline))
        finally:
            future.cancel()
    except TimeoutError:
        raise ApiError(504, 'model_timeout', '模型响应超时，请重试。') from None


def remaining(deadline):
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise TimeoutError
    return seconds


def request_completion(model, messages, structured, deadline):
    remaining(deadline)
    parts, address = public_endpoint(model.base_url)
    remaining(deadline)
    host = parts.hostname
    port = parts.port or 443
    path = parts.path.rstrip('/') + '/chat/completions'
    body = {'model': model.name, 'messages': messages}
    if structured:
        body['response_format'] = {'type': 'json_object'}
    else:
        body['max_tokens'] = 8
    # Dial only the validated IP, but verify TLS and route HTTP by the original hostname.
    authority = f'[{host}]' if ':' in host else host
    if port != 443:
        authority += f':{port}'
    try:
        with http_client(remaining(deadline)) as client:
            request = client.build_request(
                'POST', httpx.URL(scheme='https', host=address, port=port, path=path), json=body,
                headers={'Host': authority, 'Authorization': f'Bearer {model.api_key.get_secret_value()}', 'Accept-Encoding':'identity'},
                extensions={'sni_hostname':host},
            )
            remaining(deadline)
            response = client.send(request, stream=True)
            try:
                remaining(deadline)
                errors = {
                    401: ('model_auth', '模型服务拒绝了凭证。'),
                    403: ('model_auth', '模型服务拒绝了访问。'),
                    404: ('model_not_found', '模型或模型接口不存在。'),
                    429: ('model_rate_limited', '模型服务限流，请稍后重试。'),
                }
                if response.status_code != 200:
                    code, message = errors.get(response.status_code, ('model_rejected', '模型服务未接受请求，请检查模型名称和接口地址。'))
                    raise ApiError(502, code, message)
                raw = bytearray()
                for chunk in response.iter_raw():
                    remaining(deadline)
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise ValueError
                data = json.loads(raw)
            finally:
                response.close()
        remaining(deadline)
        text = data['choices'][0]['message']['content']
        if not isinstance(text, str) or not text.strip():
            raise ValueError
        usage = data.get('usage')
        tokens = usage.get('total_tokens') if isinstance(usage, dict) else None
        return (json.loads(text) if structured else text), (tokens if type(tokens) is int and tokens >= 0 else None)
    except httpx.TimeoutException:
        raise ApiError(504, 'model_timeout', '模型响应超时，请重试。') from None
    except (httpx.RequestError, UnicodeError):
        raise ApiError(502, 'model_connection', '无法连接模型服务。') from None
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise ApiError(502, 'model_response', '模型返回了无法识别的内容。') from None


@router.post('/models/test')
def test_connection(payload: ModelInput, settings: Settings = Depends(settings_for)):
    _, tokens = complete(Model(payload.name, str(payload.base_url), payload.api_key), [
        {'role':'user','content':'Reply with OK.'},
    ], timeout=settings.model_timeout_seconds)
    result = {'status':'connected','name':payload.name}
    if tokens is not None:
        result['tokens'] = tokens
    return result
