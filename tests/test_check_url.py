"""URL liveness verdicts: anti-bot and local TLS failures must not read as dead."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_report as vr  # noqa: E402


def _probe_stub(*results):
    it = iter(results)
    return lambda *a, **k: next(it)


def test_head_403_is_inconclusive_not_dead():
    with mock.patch.object(vr, "_probe", _probe_stub((False, 403), (False, 403))):
        ok, detail = vr.check_url("https://example.com/")
    assert ok is None and "anti-bot" in detail


def test_head_405_then_get_200_is_alive():
    with mock.patch.object(vr, "_probe", _probe_stub((False, 405), (True, 200))):
        assert vr.check_url("https://example.com/") == (True, 200)


def test_local_tls_failure_retried_insecure():
    tls = (None, "URLError: CERTIFICATE_VERIFY_FAILED")
    with mock.patch.object(vr, "_probe", _probe_stub(tls, tls, (True, 200))):
        ok, detail = vr.check_url("https://example.com/f.pdf")
    assert ok is True and "TLS chain unverified" in detail


def test_real_404_still_dead():
    with mock.patch.object(vr, "_probe", _probe_stub((False, 404), (False, 404))):
        assert vr.check_url("https://example.com/gone") == (False, 404)


def test_308_redirect_followed_not_dead():
    # Python < 3.11 urllib 不跟 308；_probe 要自己跟到最終頁
    import email.message
    import urllib.error

    hdrs = email.message.Message()
    hdrs["Location"] = "/new"
    err = urllib.error.HTTPError("https://example.com/old", 308, "PR", hdrs, None)

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = []

    def fake_urlopen(req, timeout=None, context=None):
        seen.append(req.full_url)
        if len(seen) == 1:
            raise err
        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        assert vr._probe("https://example.com/old", "HEAD", 5) == (True, 200)
    assert seen == ["https://example.com/old", "https://example.com/new"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
