"""Offline checks for the development downloader's URL and file boundaries."""

import hashlib
import io
import urllib.error
import urllib.request
import urllib.response

import pytest

from tools.screen_text_lab.training import bootstrap


@pytest.mark.parametrize("url", [
    "file:///synthetic.txt", "http://api.nuget.org/", "ftp://api.nuget.org/",
    "https://untrusted.invalid/archive.zip", bootstrap.PYTHON_URL + "?mirror=1",
    bootstrap.PYTHON_URL.replace("api.nuget.org", "api.nuget.org.untrusted.invalid"),
    bootstrap.PADDLEOCR_URL.replace(bootstrap.REVISION, "main"),
])
def test_unlisted_urls_fail_before_network_or_output(tmp_path, monkeypatch, url):
    monkeypatch.setattr(bootstrap, "_https_only_opener",
                        lambda: pytest.fail("Unlisted URL reached the network"))
    target = tmp_path / "new" / "archive.zip"
    with pytest.raises(ValueError, match="official HTTPS"):
        bootstrap.download(url, target)
    assert not target.parent.exists()


@pytest.mark.parametrize("scheme", ["file", "http", "ftp"])
def test_opener_rejects_other_schemes_even_with_https_proxies(tmp_path, monkeypatch, scheme):
    source = tmp_path / "synthetic.txt"
    source.write_bytes(b"synthetic local content")
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {
        "https": "http://proxy.invalid:8080", scheme: "https://proxy.invalid:443"})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open",
                        lambda *args: pytest.fail("Non-HTTPS URL reached transport"))
    url = source.as_uri() if scheme == "file" else f"{scheme}://synthetic.invalid/"
    with pytest.raises(urllib.error.URLError):
        bootstrap._https_only_opener().open(url, timeout=1)
    assert source.read_bytes() == b"synthetic local content"


@pytest.mark.parametrize("url", [bootstrap.PYTHON_URL, bootstrap.PADDLEOCR_URL])
def test_official_download_preserves_https_proxy_and_reports_bytes(tmp_path, monkeypatch, url):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://proxy.invalid:8080"})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    seen = []
    content = b"synthetic package only"

    def transport(handler, request):
        seen.append((request.type, request.host, request._tunnel_host, request.full_url))
        response = urllib.response.addinfourl(io.BytesIO(content), {}, request.full_url, 200)
        response.msg = "OK"
        return response

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", transport)
    target = tmp_path / "archive.zip"
    record = bootstrap.download(url, target)
    assert target.read_bytes() == content
    assert record == {"url": url, "path": str(target), "size": len(content),
                      "sha256": hashlib.sha256(content).hexdigest()}
    assert seen == [("https", "proxy.invalid:8080", url.split("/")[2], url)]


@pytest.mark.parametrize("location", ["file:///synthetic.txt", "https://untrusted.invalid/archive.zip"])
def test_redirect_is_rejected_without_following_or_creating_output(tmp_path, monkeypatch, location):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    seen = []

    def transport(handler, request):
        seen.append(request.full_url)
        response = urllib.response.addinfourl(io.BytesIO(b""), {"Location": location}, request.full_url, 302)
        response.msg = "Found"
        return response

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", transport)
    target = tmp_path / "archive.zip"
    with pytest.raises(urllib.error.HTTPError) as exc:
        bootstrap.download(bootstrap.PYTHON_URL, target)
    assert exc.value.code == 302
    exc.value.close()
    assert seen == [bootstrap.PYTHON_URL]
    assert not target.exists()


def test_existing_download_is_preserved_before_network(tmp_path, monkeypatch):
    target = tmp_path / "archive.zip"
    target.write_bytes(b"existing package")
    monkeypatch.setattr(bootstrap, "_https_only_opener",
                        lambda: pytest.fail("Existing output reached the network"))
    with pytest.raises(FileExistsError):
        bootstrap.download(bootstrap.PYTHON_URL, target)
    assert target.read_bytes() == b"existing package"
