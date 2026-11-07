"""Tests against the real English Wikipedia, to catch where it differs from
the fake one.  They only read, never edit, and only run when asked for:

    pytest -m live
"""

import pytest

from infoboxsweep import ROOT_CATEGORY
from infoboxsweep.bot import Bot, Options
from infoboxsweep.infobox import INFOBOX_PAGES
from infoboxsweep.request import REQUEST_TEMPLATE

pytestmark = pytest.mark.live


@pytest.fixture(scope='module')
def wiki():
    import pywikibot

    from infoboxsweep.cli import USER_AGENT
    from infoboxsweep.wiki import Wiki
    pywikibot.config.user_agent_format = USER_AGENT
    return Wiki(pywikibot.Site('en', 'wikipedia'))


def test_the_root_category_has_subcategories(wiki):
    subs = wiki.subcategories(ROOT_CATEGORY)
    assert subs and all(sub.startswith('Category:') for sub in subs)


def test_the_request_template_has_redirects(wiki):
    assert wiki.redirects_to(REQUEST_TEMPLATE)


def test_an_infobox_is_found(wiki):
    found = wiki.transcluding(['Paris', 'Albert Einstein'], INFOBOX_PAGES)
    assert 'Template:Infobox' in found['Paris'] or 'Module:Infobox' in found['Paris']
    assert found['Albert Einstein']


def test_parse_gives_the_request_category(wiki):
    categories = wiki.categories_with('Talk:Example', '{{Infobox requested}}')
    assert any('infobox' in c.lower() for c in categories)
    assert not any('infobox' in c.lower() for c in wiki.categories_with('Talk:Example', 'Hi.'))


def test_dry_run_over_a_few_pages(wiki, tmp_path):
    talk = next(iter(wiki.category_pages(wiki.subcategories(ROOT_CATEGORY)[0])))
    report = Bot(wiki, Options(pages=(talk,), out_dir=tmp_path)).run()
    assert report.checked == 1 and not report.errors and not report.stopped
    assert not any(edit.saved for edit in report.edits)
