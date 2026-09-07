"""HTTPS helpers that remain reliable inside frozen cross-platform builds."""

import ssl
import urllib.request
from pathlib import Path


USER_AGENT = "LocallyFPS"


def tls_context():
    """Use the bundled CA store when a packaged Python has host-specific paths."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def open_url(url_or_request, *, timeout=60):
    if isinstance(url_or_request, str):
        url_or_request = urllib.request.Request(
            url_or_request, headers={"User-Agent": USER_AGENT},
        )
    return urllib.request.urlopen(
        url_or_request, timeout=timeout, context=tls_context(),
    )


def download_file(url, destination, reporthook=None, *, timeout=60):
    """Stream a URL to disk with urlretrieve-compatible progress callbacks."""
    destination = Path(destination)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    block_size = 256 * 1024
    with open_url(request, timeout=timeout) as response, open(destination, "wb") as output:
        try:
            total_size = int(response.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            total_size = 0
        block_number = 0
        if reporthook:
            reporthook(block_number, block_size, total_size)
        while True:
            chunk = response.read(block_size)
            if not chunk:
                break
            output.write(chunk)
            block_number += 1
            if reporthook:
                reporthook(block_number, block_size, total_size)
    return str(destination), response.headers
