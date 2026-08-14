"""Production WSGI command for the Personal AI Knowledge Agent WebUI."""

import argparse
import os
from typing import Optional, Sequence

from .web import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the Personal AI Knowledge Agent WebUI")
    parser.add_argument(
        "--host",
        default=os.environ.get(
            "PERSONAL_AGENT_WEB_HOST",
            "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1",
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.environ.get("PERSONAL_AGENT_WEB_PORT")
            or os.environ.get("PORT")
            or "8000"
        ),
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("PERSONAL_AGENT_WEB_THREADS", "4")),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.port < 1 or arguments.port > 65535:
        raise SystemExit("port must be between 1 and 65535")
    if arguments.threads < 1 or arguments.threads > 64:
        raise SystemExit("threads must be between 1 and 64")
    try:
        from waitress import serve
    except ImportError as exc:
        raise SystemExit("waitress is required for the production web command") from exc
    serve(
        create_app(),
        host=arguments.host,
        port=arguments.port,
        threads=arguments.threads,
        clear_untrusted_proxy_headers=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
