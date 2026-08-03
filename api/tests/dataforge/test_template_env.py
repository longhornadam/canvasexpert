"""Tests for the framework-neutral Jinja environment contract."""

import jinja2
import pytest

from api.dataforge import template_env


def test_install_populates_what_templates_need():
    env = jinja2.Environment()
    template_env.install(env, url=lambda e, **kw: "/x")
    for name in template_env.REQUIRED_GLOBALS:
        assert name in env.globals
    assert env.globals["base_template"] == template_env.DEFAULT_BASE_TEMPLATE


def test_base_template_can_be_overridden():
    env = jinja2.Environment()
    template_env.install(env, url=lambda e, **kw: "/x", base_template="host_layout.html")
    assert env.globals["base_template"] == "host_layout.html"


def test_install_rejects_a_non_callable_url():
    env = jinja2.Environment()
    with pytest.raises(TypeError):
        template_env.install(env, url="not callable")
