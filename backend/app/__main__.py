"""Start the local server using validated environment configuration."""

import sys

import uvicorn

from app.config import ConfigurationError, load_settings
from app.main import create_app


def main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    uvicorn.run(
        create_app(settings),
        host=str(settings.host),
        port=settings.port,
        log_level=settings.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
