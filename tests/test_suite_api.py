"""Suite API plumbing: timeouts and the token session."""
from unittest import mock

import pytest
import suite_api
from aria.ops.suite_api_client import SuiteApiClient
from aria.ops.suite_api_client import SuiteApiConnectionParameters


def response(status=200, body=None):
    r = mock.MagicMock()
    r.ok = status < 400
    r.status_code = status
    r.json.return_value = body if body is not None else {}
    r.text = ""
    r.__enter__.return_value = r
    return r


class Recorder:
    """Stands in for requests.get/post (the SDK logs request_func.__name__)."""

    def __init__(self, responder):
        self.calls = []
        self.responder = responder

    def fake(self, name):
        def request(**kwargs):
            self.calls.append(kwargs)
            return self.responder(**kwargs)

        request.__name__ = name
        return request


def ok(**kwargs):
    return response(body={"token": "t"})


def real_client():
    return SuiteApiClient(SuiteApiConnectionParameters("ops.example.test", "user", "not-a-secret"))


def test_every_request_including_token_acquire_and_release_has_a_timeout():
    client = suite_api.apply_request_timeout(real_client())
    rec = Recorder(ok)
    with mock.patch("requests.post", rec.fake("post")), mock.patch("requests.get", rec.fake("get")):
        with suite_api.session(client):
            client.get("/api/resources/x/properties")
    assert len(rec.calls) == 3  # acquire, get, release
    assert all(c["timeout"] == suite_api.REQUEST_TIMEOUT for c in rec.calls)


def test_a_caller_timeout_wins():
    client = suite_api.apply_request_timeout(real_client())
    rec = Recorder(ok)
    with mock.patch("requests.get", rec.fake("get")):
        client.get("/api/x", timeout=5)
    assert rec.calls[0]["timeout"] == 5


def test_failed_release_is_logged_not_raised():
    client = suite_api.apply_request_timeout(real_client())

    def post(**kwargs):
        if kwargs["url"].endswith("auth/token/release"):
            raise TimeoutError("release hung")
        return response(body={"token": "t"})

    with mock.patch("requests.post", Recorder(post).fake("post")):
        with suite_api.session(client):
            pass  # reads succeeded; the release must not raise


def test_an_error_inside_the_session_still_releases_and_propagates():
    client = suite_api.apply_request_timeout(real_client())
    rec = Recorder(ok)
    with mock.patch("requests.post", rec.fake("post")):
        with pytest.raises(RuntimeError):
            with suite_api.session(client):
                raise RuntimeError("boom")
    assert rec.calls[-1]["url"].endswith("auth/token/release")
