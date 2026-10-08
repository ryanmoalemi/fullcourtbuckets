"""Block ESPN and the stats feed for the whole test process.

Unit tests inject fixtures. A forgotten mock must fail before any socket opens,
including when those hosts are down.
"""
from __future__ import annotations

import sys
import urllib.request
from urllib.parse import urlsplit

class OfflineFeedError(RuntimeError):
    """A test tried to reach ESPN or the stats feed."""


_BLOCKED_HOSTS = (
    'espn.com',
    'balldontlie.io',
)
_installed = False
_real_urlopen = urllib.request.urlopen
_real_open = urllib.request.OpenerDirector.open


def _url_text(url) -> str:
    if hasattr(url, 'full_url'):
        return str(url.full_url)
    return str(url)


def blocked_feed(url) -> bool:
    host = (urlsplit(_url_text(url)).hostname or '').lower().rstrip('.')
    return any(host == name or host.endswith('.' + name) for name in _BLOCKED_HOSTS)


def _reject(url):
    raise OfflineFeedError('Refusing live feed access during tests: ' + _url_text(url))


def install() -> None:
    """Replace urllib openers. Safe to call more than once."""
    global _installed
    if _installed:
        return

    def guarded_urlopen(url, *args, **kwargs):
        if blocked_feed(url):
            _reject(url)
        return _real_urlopen(url, *args, **kwargs)

    def guarded_open(self, fullurl, *args, **kwargs):
        if blocked_feed(fullurl):
            _reject(fullurl)
        return _real_open(self, fullurl, *args, **kwargs)

    urllib.request.urlopen = guarded_urlopen
    urllib.request.OpenerDirector.open = guarded_open
    for name in ('homepage_rail', 'build_standings', 'season_teams', 'game_stats', 'wnba_sync'):
        module = sys.modules.get(name)
        if module is not None and getattr(module, 'urlopen', None) is _real_urlopen:
            module.urlopen = guarded_urlopen
    _installed = True


install()
