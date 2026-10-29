"""
Keeps the Suite API session token out of adapter.log.

The SDK's SuiteApiClient logs the token it acquires ("Acquired token ...")
and every response body, including the token-acquire response, at DEBUG
(aria/ops/suite_api_client.py in vmware-aria-operations-integration-sdk-lib
1.1.0). Raising the adapter's log level to DEBUG through loglevels.cfg would
otherwise write a usable bearer token into /var/log/adapter.log and its
rotations. install() adds a filter to the log handlers that redacts the
token from every record, including exception tracebacks and stack text, and
truncates long DEBUG records from the SDK (response bodies, the result
written to the output pipe). The filter never raises: a record it cannot
process is logged unchanged rather than breaking the caller.
"""
from __future__ import annotations

import logging
import re

REDACTED = "<redacted>"
MAX_SDK_DEBUG_CHARS = 2000

_TOKEN_PATTERNS = [
    # SuiteApiClient.get_token(): logger.debug("Acquired token " + self.token)
    re.compile(r"(Acquired token )\S+"),
    # The token-acquire response body: {"token":"...", ...}
    re.compile(r'("token"\s*:\s*")[^"]*(")'),
    # The Authorization header value, should a request ever be logged
    re.compile(r"(vRealizeOpsToken\s+)[^\s\"',}]+"),
]


def redact(message: str) -> str:
    for pattern in _TOKEN_PATTERNS:
        message = pattern.sub(
            lambda m: m.group(1) + REDACTED + (m.group(2) if m.re.groups > 1 else ""), message
        )
    return message


_formatter = logging.Formatter()


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            self._clean(record)
        except Exception:  # noqa: BLE001
            # A record whose args do not match its format must not raise at
            # the call site; let the handler report it as logging normally does.
            pass
        return True

    @staticmethod
    def _clean(record: logging.LogRecord) -> None:
        message = record.getMessage()
        cleaned = redact(message)
        if (
            record.levelno <= logging.DEBUG
            and record.name.startswith("aria.ops")
            and len(cleaned) > MAX_SDK_DEBUG_CHARS
        ):
            cleaned = (
                cleaned[:MAX_SDK_DEBUG_CHARS]
                + f" ... [{len(cleaned) - MAX_SDK_DEBUG_CHARS} more characters not logged]"
            )
        if cleaned != message:
            record.msg = cleaned
            record.args = None
        # Formatters reuse record.exc_text when it is set, so the redacted
        # traceback is what gets written.
        if record.exc_info and not record.exc_text:
            record.exc_text = _formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)


def install() -> None:
    """Add the filter to every handler on the root logger. Call after
    aria.ops.adapter_logging.setup_logging(), which creates the handlers."""
    redacting_filter = RedactingFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redacting_filter)
