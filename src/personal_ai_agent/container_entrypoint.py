"""Initialize the bundled demo knowledge index before starting the WSGI server."""

import os
import sys
from typing import Optional, Sequence

from .application import ApplicationService
from .web_server import main as serve_web


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if any(item in {"-h", "--help"} for item in arguments):
        return serve_web(arguments)
    config_path = os.environ.get("PERSONAL_AGENT_CONFIG", "agent.config.json")
    result = ApplicationService.from_file(config_path).sync_vault()
    if result.failed:
        raise SystemExit("demo Vault synchronization failed")
    return serve_web(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
