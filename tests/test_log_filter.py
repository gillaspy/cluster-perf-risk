"""The Suite API token never reaches a log handler (#7)."""
import io
import logging

import log_filter

TOKEN = "00000000-0000-0000-0000-00000000fake::00000000-0000-0000-0000-00000000fake"


def capture(logger_name, level, message, *args, **kwargs):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(log_filter.RedactingFilter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        logger.log(level, message, *args, **kwargs)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    return stream.getvalue()


def test_acquired_token_line_is_redacted():
    out = capture("aria.ops.suite_api_client", logging.DEBUG, "Acquired token " + TOKEN)
    assert TOKEN not in out
    assert "Acquired token <redacted>" in out


def test_token_acquire_response_body_is_redacted():
    body = '{"token":"' + TOKEN + '","validity":1793229999,"expiresAt":"Thursday","roles":[]}'
    out = capture("aria.ops.suite_api_client", logging.DEBUG, body)
    assert TOKEN not in out
    assert '"token":"<redacted>"' in out and '"validity":1793229999' in out


def test_authorization_header_is_redacted_on_any_logger():
    out = capture("__main__", logging.WARNING, "headers {'Authorization': 'vRealizeOpsToken " + TOKEN + "'}")
    assert TOKEN not in out


def test_long_sdk_debug_bodies_are_truncated_but_other_records_are_not():
    long = "x" * (log_filter.MAX_SDK_DEBUG_CHARS + 500)
    out = capture("aria.ops.suite_api_client", logging.DEBUG, long)
    assert len(out) < log_filter.MAX_SDK_DEBUG_CHARS + 100
    assert "500 more characters not logged" in out
    assert len(capture("__main__", logging.INFO, long)) > log_filter.MAX_SDK_DEBUG_CHARS + 500


def test_install_adds_the_filter_to_root_handlers():
    root = logging.getLogger()
    handler = logging.StreamHandler(io.StringIO())
    root.addHandler(handler)
    try:
        log_filter.install()
        assert any(isinstance(f, log_filter.RedactingFilter) for f in handler.filters)
    finally:
        root.removeHandler(handler)


def test_token_in_a_traceback_is_redacted():
    try:
        raise RuntimeError("Authorization: vRealizeOpsToken " + TOKEN)
    except RuntimeError:
        out = capture("__main__", logging.ERROR, "failed", exc_info=True)
    assert "Traceback" in out and "RuntimeError" in out
    assert TOKEN not in out


def test_a_badly_formatted_record_does_not_raise_at_the_call_site():
    # Only our filtered handler sees the record (pytest's own capture handler
    # re-raises logging errors by design).
    logger = logging.getLogger("bad_format_probe")
    logger.propagate = False
    handler = logging.StreamHandler(io.StringIO())
    handler.addFilter(log_filter.RedactingFilter())
    logger.addHandler(handler)
    try:
        logger.error("a %s %s", 1)  # one arg for two placeholders
    finally:
        logger.removeHandler(handler)
