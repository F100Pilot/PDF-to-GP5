"""Local launcher: ``python -m app [--host H] [--port P] [--close-with-browser]``."""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time

import uvicorn

from .config import settings, youtube_key_status
from .main import app, presence

logger = logging.getLogger("uvicorn.error")


class _HidePresenceReports(logging.Filter):
    """Keep the console readable: pages report themselves every few seconds."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/presence" not in record.getMessage()


# Browsers keep idle connections open for a while after a page is closed, and uvicorn waits for
# them; on Windows their closing may never be noticed. Stop waiting after this, then force it.
GRACEFUL_SHUTDOWN_S = 3
FORCE_EXIT_AFTER_S = 8


def _stop_when_pages_closed(server: uvicorn.Server) -> None:
    while not server.should_exit:
        if presence.should_stop():
            logger.info("A página da aplicação foi fechada: a encerrar o servidor.")
            server.should_exit = True
            break
        time.sleep(1)
    else:
        return  # stopped some other way (Ctrl+C)
    time.sleep(GRACEFUL_SHUTDOWN_S)
    server.force_exit = True  # stop waiting for connections the browser still holds
    time.sleep(FORCE_EXIT_AFTER_S - GRACEFUL_SHUTDOWN_S)
    # Still running (this thread is a daemon, so it is gone once the process ends normally).
    logger.warning("O servidor não terminou sozinho: a forçar a saída.")
    logging.shutdown()
    os._exit(0)  # nothing is kept on disk, so a hard exit loses nothing


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
    if settings.youtube_api_key:
        print("Vídeo do YouTube: pesquisa automática ligada.", flush=True)
    else:
        print(f"Vídeo do YouTube: pesquisa automática desligada ({youtube_key_status()[1]}).", flush=True)
    config = uvicorn.Config(app, host=args.host, port=args.port, timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
    server = uvicorn.Server(config)
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
