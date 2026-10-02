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
import sys
import time
from collections.abc import Callable
from multiprocessing.connection import Connection

from . import i18n
from .converter import ConversionError, ConversionOptions, ConversionResult, convert_many, inspect, set_progress

logger = logging.getLogger(__name__)

_METHOD = "forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn"
_CTX = mp.get_context(_METHOD)
GENERIC_ERROR = "Erro interno ao processar o PDF."  # Portuguese original; see generic_error()
# Upper bound for the child's reply; a GP5 of a long song is a few hundred KB.
MAX_REPLY_BYTES = 32 * 1024 * 1024


def generic_error() -> str:
    """The generic failure text, in the language of the current request."""
    return i18n.tr(GENERIC_ERROR, "Internal error while processing the PDF.")


class ConversionTimeout(Exception):
    pass


class ConversionUnavailable(Exception):
    """The worker process could not be started (e.g. too many processes/files)."""


def _limit_resources(megabytes: int, cpu_seconds: int) -> None:
    """POSIX: cap address space and CPU time inside the child (Windows: see _windows_job)."""
    try:
        import resource
    except ImportError:  # Windows: the parent assigns the child to a Job Object
        return
    limit = megabytes * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 5))


def _windows_job(process: mp.process.BaseProcess, megabytes: int) -> object | None:
    """Windows has no RLIMIT_AS: put the child in a Job Object with a per-process memory cap.

    Returns the job handle (closed by the caller once the child has ended), or None
    when not on Windows or when the job could not be set up (a warning is logged).
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_ulonglong)
                for name in ("Read", "Write", "Other", "ReadBytes", "WriteBytes", "OtherBytes")
            ]

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job_object_extended_limit_information = 9
        job_object_limit_process_memory = 0x100
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = job_object_limit_process_memory
        limits.ProcessMemoryLimit = megabytes * 1024 * 1024
        ok = kernel32.SetInformationJobObject(
            job, job_object_extended_limit_information, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        handle = process._popen._handle  # type: ignore[attr-defined]  # spawn Popen on Windows
        if not ok or not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(handle)):
            kernel32.CloseHandle(job)
            raise OSError(ctypes.get_last_error(), "Job Object setup")
        return job
    except Exception:  # never fail the conversion because the limit could not be applied
        logger.warning("could not apply a memory limit to the worker on Windows", exc_info=True)
        return None


def _close_job(job: object | None) -> None:
    if job is not None:
        import ctypes

        ctypes.WinDLL("kernel32").CloseHandle(job)


def _reply(conn: Connection, **payload: object) -> None:
    # JSON, not pickle: the parent must never unpickle data produced while
    # parsing untrusted input (a compromised child could inject code).
    conn.send_bytes(json.dumps(payload).encode("utf-8"))


def _worker(
    conn: Connection,
    pdfs: list[bytes],
    options: ConversionOptions,
    memory_mb: int,
    job: str,
    cpu_seconds: int,
    lang: str = i18n.DEFAULT,
) -> None:
    i18n.use(lang)  # the child writes its warnings and errors in the user's language
    sent = [-1]

    def progress(fraction: float) -> None:  # whole percents only, each once
        percent = int(fraction * 100)
        if percent > sent[0]:
            sent[0] = percent
            _reply(conn, status="progress", percent=percent)

    set_progress(progress)
    try:
        _limit_resources(memory_mb, cpu_seconds)
        if job == "inspect":
            _reply(conn, status="ok", gp5="", report=inspect(pdfs[0], options))
            return
        result = convert_many(pdfs, options)
        _reply(conn, status="ok", gp5=base64.b64encode(result.gp5).decode("ascii"), report=result.report)
    except ConversionError as exc:
        _reply(conn, status="error", message=str(exc))
    except MemoryError:
        _reply(
            conn,
            status="error",
            message=i18n.tr(
                "O PDF excede o limite de memória de processamento.", "The PDF exceeds the processing memory limit."
            ),
        )
    except Exception:  # never leak internals to the client
        logger.exception("conversion failed")
        _reply(conn, status="error", message=generic_error())
    finally:
        set_progress(None)
        conn.close()


def _progress_of(raw: bytes) -> int | None:
    """The percent of a progress message from the child; None for any other message."""
    if len(raw) > 100:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("status") != "progress":
        return None
    percent = payload.get("percent")
    return min(max(percent, 0), 100) if isinstance(percent, int) and not isinstance(percent, bool) else 0


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
        raise ConversionError(generic_error()) from exc


def run_isolated(
    pdfs: bytes | list[bytes],
    options: ConversionOptions,
    timeout_s: int,
    memory_mb: int,
    job: str = "convert",
    on_progress: Callable[[int], None] | None = None,
) -> ConversionResult:
    """Run ``job`` ("convert" or "inspect") in a child process; inspect returns an empty gp5.

    ``pdfs`` is one PDF per track (inspect uses the first). ``on_progress`` gets the percent of
    the job done, as the child reports it.
    """
    if job not in ("convert", "inspect"):
        raise ValueError(f"unknown job {job!r}")
    if isinstance(pdfs, bytes):
        pdfs = [pdfs]
    receiver, sender = _CTX.Pipe(duplex=False)
    process = _CTX.Process(
        target=_worker,
        args=(sender, pdfs, options, memory_mb, job, max(1, int(timeout_s)) + 5, i18n.current()),
        daemon=True,
    )
    try:
        process.start()
    except OSError as exc:  # e.g. too many processes or open files
        receiver.close()
        sender.close()
        raise ConversionUnavailable() from exc
    sender.close()
    windows_job = _windows_job(process, memory_mb)
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not receiver.poll(remaining):
                raise ConversionTimeout()
            try:
                raw = receiver.recv_bytes(MAX_REPLY_BYTES)
            except (EOFError, OSError) as exc:  # child died or reply too large
                raise ConversionError(generic_error()) from exc
            percent = _progress_of(raw)
            if percent is None:
                break  # the result (or the error)
            if on_progress is not None:
                on_progress(percent)
    finally:
        receiver.close()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
        _close_job(windows_job)
    return _decode_reply(raw)
