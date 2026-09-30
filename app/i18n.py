"""The app's languages for text the SERVER writes: error details and the
warnings of a conversion. Portuguese is the original; English is always there;
any other language the UI has (``app/static/i18n-<code>.js``) may be given too.

Each message is written once where it is produced, in its languages —
``tr("não encontrado", "not found")``, ``tr(pt, en, es="no encontrado")`` — so
they cannot drift apart and no lookup table has to be kept in step with the
code. A language a message was not written in reads the English. The language
is the one the browser sent with the request (``X-App-Lang``, see
``LanguageMiddleware``); the conversion's child process gets it from
``sandbox.run_isolated``. Outside a request it is Portuguese.
See ``.claude/skills/pdf-to-gp5-i18n/SKILL.md``.
"""

from __future__ import annotations

import re
from contextvars import ContextVar, Token

DEFAULT = "pt"
HEADER = "x-app-lang"
_CODE = re.compile(r"[a-z]{2,3}")

_lang: ContextVar[str | None] = ContextVar("pdf_to_gp5_lang", default=None)


def valid(lang: object) -> bool:
    """A language code as the UI sends it ("pt", "en", "es"…)."""
    return isinstance(lang, str) and _CODE.fullmatch(lang) is not None


def use(lang: str | None) -> Token[str | None]:
    """Set the language for the current context; a malformed value falls back
    to Portuguese. Returns the token to reset it with."""
    return _lang.set(lang if valid(lang) else None)


def reset(token: Token[str | None]) -> None:
    _lang.reset(token)


def current() -> str:
    return _lang.get() or DEFAULT


def tr(pt: str, en: str, **other: str) -> str:
    """The message in the language the user reads: ``pt``, ``en``, or one of
    ``other`` by code — English for a language it was not written in."""
    lang = current()
    if lang == "pt":
        return pt
    return other.get(lang, en)


class LanguageMiddleware:
    """Reads ``X-App-Lang`` into the request's context, so ``tr`` answers in it."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = dict(scope.get("headers") or []).get(HEADER.encode())
        token = use(raw.decode("latin-1").strip().lower() if raw else None)
        try:
            await self.app(scope, receive, send)
        finally:
            reset(token)
