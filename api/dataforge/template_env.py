#!/usr/bin/env python3
"""What these templates need from whatever renders them.

The templates are plain Jinja and know nothing about a web framework. They ask
for two things by name, and a host supplies both through `install()`:

  url(endpoint, **params) -> str
      Resolve a named route to a URL. Templates name endpoints rather than
      building paths, which is the same indirection `views.Redirect` uses, so
      neither the templates nor the view logic has to change when the host
      does. Under Flask this is `url_for`; under another host it is whatever
      that host's reverse-resolver is.

  base_template -> str
      The layout every page extends. It defaults to this package's own
      `base.html`, but a host application can point it at its own layout so
      these pages look native rather than bolted on.

This module imports no web framework on purpose, and a guard test enforces
that. Keeping the contract here rather than inline in the Flask app is what
makes it visible to a future host: the list of things to supply is the module,
not a diff.
"""

from typing import Callable

REQUIRED_GLOBALS = ("url", "base_template")
DEFAULT_BASE_TEMPLATE = "base.html"


def install(jinja_env, *, url: Callable[..., str],
            base_template: str = DEFAULT_BASE_TEMPLATE) -> None:
    """Give a Jinja environment everything these templates expect.

    Call once, after the environment exists and before rendering.
    """
    if not callable(url):
        raise TypeError("url must be callable as url(endpoint, **params)")
    jinja_env.globals["url"] = url
    jinja_env.globals["base_template"] = base_template
