"""Local launcher: ``python -m app [--host H] [--port P] [--close-with-browser]``."""

from __future__ import annotations

import argparse
import logging
import threading
import time

import uvicorn

from .main import app, presence

logger = logging.getLogger("uvicorn.error")


class _HidePresenceReports(logging.Filter):
    """Keep the console readable: pages report themselves every few seconds."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/presence" not in record.getMessage()


def _stop_when_pages_closed(server: uvicorn.Server) -> None:
    while not server.should_exit:
        if presence.should_stop():
            logger.info("A página da aplicação foi fechada: a encerrar o servidor.")
            server.should_exit = True
            return
        time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="Servidor local PDF -> GP5.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument(
        "--close-with-browser",
        action="store_true",
        help="encerrar o servidor quando a última página da aplicação for fechada",
    )
    args = parser.parse_args(argv)
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port))
    if args.close_with_browser:
        presence.enabled = True
        logging.getLogger("uvicorn.access").addFilter(_HidePresenceReports())
        threading.Thread(target=_stop_when_pages_closed, args=(server,), daemon=True).start()
    try:
        server.run()  # startup failures (e.g. port in use) exit with a non-zero code
    except KeyboardInterrupt:  # Ctrl+C: uvicorn already shut down cleanly
        pass
    return 0 if server.started else 1


if __name__ == "__main__":
    raise SystemExit(main())
