"""Shared dependencies for application routes."""

from fastapi import Request

from app.config import Settings


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def settings_for(request: Request) -> Settings:
    settings = request.app.state.settings
    if settings is None:
        raise ApiError(503, 'configuration_error', '服务配置无效。')
    return settings
