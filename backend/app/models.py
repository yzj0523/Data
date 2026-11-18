"""Model registry. Credentials are encrypted under a deployment-local key."""

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator

from app.api import ApiError, settings_for
from app.config import Settings
from app.database import connection
from app.preferences import load_preferences

router = APIRouter()


class ModelInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)
    base_url: HttpUrl
    api_key: SecretStr

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('api_key')
    @classmethod
    def valid_key(cls, value):
        if not value.get_secret_value().strip() or len(value.get_secret_value()) > 2048 or any(ch.isspace() for ch in value.get_secret_value()):
            raise ValueError('Invalid credential')
        return value


@dataclass(frozen=True)
class Model:
    name: str
    base_url: str
    api_key: SecretStr


def public_endpoint(url: str):
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port or 443
        if parts.scheme != 'https' or not host or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError
        if host.rstrip('.').lower() == 'localhost' or host.lower().endswith(('.localhost','.local','.internal')):
            raise ValueError
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            addresses = list({ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
        if not addresses or any(not address.is_global or address.is_multicast or address.is_reserved for address in addresses):
            raise ValueError
        return parts, str(sorted(addresses, key=lambda address: (address.version, int(address)))[0])
    except OSError:
        raise ApiError(502, 'model_dns', '无法解析模型服务地址。') from None
    except ValueError:
        raise ApiError(422, 'model_address_rejected', '模型地址必须使用可公开访问的 HTTPS 服务。') from None


def cipher(settings: Settings) -> Fernet:
    try:
        if settings.model_encryption_key:
            return Fernet(settings.model_encryption_key.get_secret_value().encode('ascii'))
        path = settings.database_path.with_suffix('.model-key')
        return Fernet(path.read_bytes())
    except (OSError, ValueError, UnicodeError):
        raise ApiError(503, 'model_key_unavailable', '模型密钥保护配置不可用。') from None


def ensure_cipher(db, settings):
    # The transaction serializes concurrent first writes to the same database.
    path = settings.database_path.with_suffix('.model-key')
    if not settings.model_encryption_key and not path.exists():
        if db.execute('SELECT 1 FROM model_registry LIMIT 1').fetchone():
            raise ApiError(503, 'model_key_unavailable', '缺少原有模型密钥保护文件。')
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(Fernet.generate_key())
    return cipher(settings)


def model_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS model_registry (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, base_url TEXT NOT NULL, encrypted_key BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_choice (id INTEGER PRIMARY KEY, model_id TEXT REFERENCES model_registry(id));
    ''')


def configured_default(settings: Settings):
    if settings.default_model_base_url and settings.default_model_name and settings.default_model_api_key:
        return Model(settings.default_model_name, str(settings.default_model_base_url), settings.default_model_api_key)
    return None


def active_model(settings: Settings):
    if not load_preferences(settings).custom_model_enabled:
        return configured_default(settings)
    with connection(settings.database_path) as db:
        model_schema(db)
        row = db.execute('SELECT m.* FROM model_choice c JOIN model_registry m ON m.id=c.model_id WHERE c.id=1').fetchone()
    if row is None:
        return None
    try:
        key = cipher(settings).decrypt(row['encrypted_key']).decode('utf-8')
    except (InvalidToken, UnicodeError):
        raise ApiError(503, 'model_key_unavailable', '无法读取已保存的模型凭证。') from None
    return Model(row['name'], row['base_url'], SecretStr(key))


@router.get('/models')
def models(settings: Settings = Depends(settings_for)):
    with connection(settings.database_path) as db:
        model_schema(db)
        rows = [dict(row) for row in db.execute('SELECT id,name,base_url FROM model_registry ORDER BY name,id')]
        choice = db.execute('SELECT model_id FROM model_choice WHERE id=1').fetchone()
    default = configured_default(settings)
    return {'items': rows, 'selected_id': choice['model_id'] if choice else None,
            'default_name': default.name if default else None,
            'custom_enabled': load_preferences(settings).custom_model_enabled}


@router.post('/models', status_code=201)
def add_model(payload: ModelInput, settings: Settings = Depends(settings_for)):
    base_url = str(payload.base_url)
    public_endpoint(base_url)
    model_id = uuid4().hex
    with connection(settings.database_path) as db:
        model_schema(db)
        db.execute('BEGIN IMMEDIATE')
        encrypted = ensure_cipher(db, settings).encrypt(payload.api_key.get_secret_value().encode())
        db.execute('INSERT INTO model_registry VALUES (?,?,?,?)', (model_id, payload.name, base_url, encrypted))
    return {'id': model_id, 'name': payload.name, 'base_url': base_url}


class ModelChoice(BaseModel):
    model_id: str


@router.put('/models/selection')
def select_model(payload: ModelChoice, settings: Settings = Depends(settings_for)):
    with connection(settings.database_path) as db:
        model_schema(db)
        if not db.execute('SELECT 1 FROM model_registry WHERE id=?', (payload.model_id,)).fetchone():
            raise ApiError(404, 'model_not_found', '所选模型不存在。')
        db.execute('INSERT INTO model_choice VALUES (1,?) ON CONFLICT(id) DO UPDATE SET model_id=excluded.model_id', (payload.model_id,))
    return {'selected_id': payload.model_id}
