"""Loaded into Python programs started by `whittle run` (through PYTHONPATH).

A program that calls a model provider by a URL written in its code would bypass the
recording proxy; this sends those requests through it. The libraries are patched as they
are imported, so nothing is imported that the program would not import itself, and nothing
else is touched.
"""
import os
import sys

_PROXY = os.environ.get("WHITTLE_PROXY", "")
_HOSTS = set(filter(None, os.environ.get("WHITTLE_HOSTS", "").split(",")))


def _reroute(url):
    try:
        from urllib.parse import urlsplit

        u = urlsplit(str(url))
    except Exception:
        return None
    if u.scheme != "https" or u.netloc not in _HOSTS:
        return None
    return "%s/h/%s%s%s" % (_PROXY, u.netloc, u.path or "/", "?" + u.query if u.query else "")


def _patch_httpx(httpx):
    def wrap(cls):
        send = cls.send

        def patched(self, request, *args, **kwargs):
            to = _reroute(request.url)
            if to:
                request.url = httpx.URL(to)
                request.headers["host"] = request.url.netloc.decode("ascii")
            return send(self, request, *args, **kwargs)

        cls.send = patched

    wrap(httpx.Client)
    wrap(httpx.AsyncClient)


def _patch_requests(requests):
    session = requests.sessions.Session
    request = session.request

    def patched(self, method, url, *args, **kwargs):
        return request(self, method, _reroute(url) or url, *args, **kwargs)

    session.request = patched


def _patch_aiohttp(aiohttp):
    request = aiohttp.ClientSession._request

    def patched(self, method, str_or_url, *args, **kwargs):
        return request(self, method, _reroute(str_or_url) or str_or_url, *args, **kwargs)

    aiohttp.ClientSession._request = patched


def _patch_urllib(module):
    opener = module.OpenerDirector.open

    def patched(self, fullurl, *args, **kwargs):
        if isinstance(fullurl, str):
            fullurl = _reroute(fullurl) or fullurl
        else:
            to = _reroute(getattr(fullurl, "full_url", ""))
            if to:
                fullurl.full_url = to
        return opener(self, fullurl, *args, **kwargs)

    module.OpenerDirector.open = patched


# httpx2 is the client the Anthropic SDK moved to; it has the same shape as httpx.
_PATCHES = {"httpx": _patch_httpx, "httpx2": _patch_httpx, "requests": _patch_requests, "aiohttp": _patch_aiohttp, "urllib.request": _patch_urllib}


def _apply(name, module):
    try:
        _PATCHES.pop(name)(module)
    except Exception:
        pass  # a library that changed shape is left as it is; the program must still run


class _Finder:
    """Runs a patch right after its library's own code has run."""

    def find_spec(self, name, path=None, target=None):
        if name not in _PATCHES:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
                continue
            run = spec.loader.exec_module

            def exec_module(module, _run=run, _name=name):
                _run(module)
                _apply(_name, module)

            try:
                spec.loader.exec_module = exec_module
            except Exception:
                return None
            return spec
        return None


if _PROXY and _HOSTS:
    for _name in list(_PATCHES):
        if _name in sys.modules:
            _apply(_name, sys.modules[_name])
    sys.meta_path.insert(0, _Finder())

# This file takes the place of any sitecustomize the environment already had: run that one too.
_here = os.path.dirname(os.path.abspath(__file__))
for _entry in sys.path:
    _file = os.path.join(_entry or ".", "sitecustomize.py")
    if os.path.abspath(os.path.dirname(_file)) != _here and os.path.isfile(_file):
        with open(_file) as _handle:
            exec(compile(_handle.read(), _file, "exec"), {"__name__": "sitecustomize", "__file__": _file})
        break
