"""Tests for the cookie pool: rotation, runtime refresh, and building from settings."""
from __future__ import annotations

from app.config import Settings
from app.session import Cookie, SessionPool, build_pool


def test_cookie_csrf_strips_quotes():
    assert Cookie("li", '"ajax:99"').csrf_token == "ajax:99"
    assert Cookie("li", "ajax:99").csrf_token == "ajax:99"


def test_pool_current_and_status():
    pool = SessionPool([Cookie("li1", "js1"), Cookie("li2", "js2")])
    assert pool.configured
    assert pool.current().li_at == "li1"
    assert pool.status() == {"total": 2, "alive": 2, "dead": 0}


def test_empty_pool():
    pool = SessionPool([])
    assert not pool.configured
    assert pool.current() is None


async def test_pool_rotates_on_death():
    pool = SessionPool([Cookie("li1", "js1"), Cookie("li2", "js2")])
    await pool.mark_dead(pool.current())
    assert pool.current().li_at == "li2"
    assert pool.status() == {"total": 2, "alive": 1, "dead": 1}
    await pool.mark_dead(pool.current())
    assert pool.current() is None  # all dead


async def test_pool_upsert_prefers_new_and_revives():
    pool = SessionPool([Cookie("li1", "js1")])
    await pool.mark_dead(pool.current())
    assert pool.current() is None
    await pool.upsert("li2", '"ajax:2"')
    current = pool.current()
    assert current.li_at == "li2"
    assert current.csrf_token == "ajax:2"
    assert pool.status()["alive"] == 1


def test_build_pool_merges_primary_and_json():
    s = Settings(
        linkedin_li_at="A",
        linkedin_jsessionid='"ajax:1"',
        linkedin_cookies='[{"li_at":"B","jsessionid":"\\"ajax:2\\""}]',
    )
    pool = build_pool(s)
    assert pool.status()["total"] == 2


def test_build_pool_tolerates_bad_json():
    s = Settings(linkedin_li_at="A", linkedin_jsessionid='"ajax:1"', linkedin_cookies="not-json")
    pool = build_pool(s)
    assert pool.status()["total"] == 1
