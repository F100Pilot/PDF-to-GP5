"""Run conversions in a short-lived child process.

PDF parsing handles untrusted input; a crafted file could trigger excessive
CPU or memory use inside pdfminer. Isolating each job lets us enforce a hard
wall-clock timeout (the child is killed) and an address-space limit without
affecting the web server process.
"""

from __future__ import annotations

import base64
import json
import logging
import multiprocessing as mp
from multiprocessing.connection import Connection

from .converter import ConversionError, ConversionOptions, ConversionResult, convert

logger = logging.getLogger(__name__)

_METHOD = "forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn"
_CTX = mp.get_context(_METHOD)
GENERIC_ERROR = "Erro interno ao processar o PDF."
# Upper bound for the child's reply; a GP5 of a long song is a few hundred KB.
MAX_REPLY_BYTES = 32 * 1024 * 1024


class ConversionTimeout(Exception):
    pass


def _limit_memory(megabytes: int) -> None:
    try:
        import resource
    except ImportError:  # non-POSIX platform
        return
    limit = megabytes * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _reply(conn: Connection, **payload: object) -> None:
    # JSON, not pickle: the parent must never unpickle data produced while
    # parsing untrusted input (a compromised child could inject code).
    conn.send_bytes(json.dumps(payload).encode("utf-8"))


def _worker(conn: Connection, pdf: bytes, options: ConversionOptions, memory_mb: int) -> None:
    try:
        _limit_memory(memory_mb)
        result = convert(pdf, options)
        _reply(conn, status="ok", gp5=base64.b64encode(result.gp5).decode("ascii"), report=result.report)
    except ConversionError as exc:
        _reply(conn, status="error", message=str(exc))
    except MemoryError:
        _reply(conn, status="error", message="O PDF excede o limite de memória de processamento.")
    except Exception:  # never leak internals to the client
        logger.exception("conversion failed")
        _reply(conn, status="error", message=GENERIC_ERROR)
    finally:
        conn.close()


def _decode_reply(raw: bytes) -> ConversionResult:
    try:
        payload = json.loads(raw)
        if payload["status"] == "error":
            raise ConversionError(str(payload["message"]))
        if payload["status"] != "ok" or not isinstance(payload["report"], dict):
            raise ValueError("unexpected status")
        return ConversionResult(gp5=base64.b64decode(payload["gp5"], validate=True), report=payload["report"])
    except ConversionError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise ConversionError(GENERIC_ERROR) from exc


def run_isolated(pdf: bytes, options: ConversionOptions, timeout_s: int, memory_mb: int) -> ConversionResult:
    receiver, sender = _CTX.Pipe(duplex=False)
    process = _CTX.Process(target=_worker, args=(sender, pdf, options, memory_mb), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout_s):
            raise ConversionTimeout()
        try:
            raw = receiver.recv_bytes(MAX_REPLY_BYTES)
        except (EOFError, OSError) as exc:  # child died or reply too large
            raise ConversionError(GENERIC_ERROR) from exc
    finally:
        receiver.close()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
    return _decode_reply(raw)
