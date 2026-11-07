"""A fake wiki and its pages, so no test touches a real wiki.

FakeWiki has the same methods as infoboxsweep.wiki.Wiki, and FakePage has the
parts of a Pywikibot Page listed in infoboxsweep.wiki.WikiPage.
"""

import re
from datetime import UTC, datetime

import mwparserfromhell

from infoboxsweep import ROOT_CATEGORY
from infoboxsweep.bot import Options
from infoboxsweep.wikitext import is_yes, normalize_param, normalize_template_name

BOT = 'ExampleBot'
FILM_CATEGORY = 'Category:Film articles needing infoboxes'
BIO_CATEGORY = 'Category:Biography articles needing infoboxes'
# Which category each banner's needs-infobox=yes puts a talk page in.
BANNERS = {'WikiProject Film': FILM_CATEGORY, 'WikiProject Biography': BIO_CATEGORY}
NAMESPACES = {'Talk': 1, 'User': 2, 'User talk': 3, 'Template': 10, 'Template talk': 11,
              'Category': 14, 'Category talk': 15, 'Draft': 118, 'Draft talk': 119}
SUBJECTS = {1: 0, 3: 2, 11: 10, 15: 14, 119: 118}

INFOBOX_ARTICLE = """{{Short description|American film}}
{{Infobox film
| name = Example
}}
'''Example''' is a film."""
PLAIN_ARTICLE = "'''Example''' is a film."
FILM_TALK = """{{WikiProject banner shell|class=Start|
{{WikiProject Film|needs-infobox=yes}}
}}
== Plot ==
Needs work."""


class SaveError(Exception):
    pass


class UserBlockedError(Exception):
    """Named like Pywikibot's, which the bot treats as fatal."""


class EditConflictError(Exception):
    """Named like Pywikibot's."""


class Revision:
    def __init__(self, timestamp, user):
        self.timestamp, self.user = timestamp, user


class FakePage:
    def __init__(self, title, text='', *, exists=True, redirect=False, may_edit=True,
                 save_errors=(), broken=False, wiki=None):
        self._title, self.text = title, text
        self._exists, self._redirect, self._may_edit = exists, redirect, may_edit
        self._save_errors = list(save_errors)   # raised by the saves in turn
        self._broken = broken
        self.wiki = wiki
        self.saved = []       # the text of each save
        self.summaries = []   # the summary of each save
        self.latest_revision = Revision(datetime(2026, 11, 7, 4, 58, tzinfo=UTC), 'Example')

    def title(self, *, with_ns=True):
        prefix, _, rest = self._title.partition(':')
        return rest if not with_ns and prefix in NAMESPACES else self._title

    def namespace(self):
        prefix, _, _ = self._title.partition(':')
        return NAMESPACES.get(prefix, 0)

    def exists(self):
        if self._broken:
            raise ConnectionError('API timed out')
        return self._exists

    def isRedirectPage(self):
        return self._redirect

    def isTalkPage(self):
        return self.namespace() % 2 == 1

    def toggleTalkPage(self):
        ns = self.namespace()
        name = self.title(with_ns=False)
        if ns % 2:
            subject = SUBJECTS[ns]
            prefix = next((p for p, n in NAMESPACES.items() if n == subject), '')
        else:
            prefix = next((p for p, n in NAMESPACES.items() if n == ns + 1))
        title = f'{prefix}:{name}' if prefix else name
        return self.wiki.page(title) if self.wiki else FakePage(title, exists=False)

    def botMayEdit(self):
        return self._may_edit

    def save(self, *, summary, minor, bot, quiet):
        assert minor and bot
        if self._save_errors:
            raise self._save_errors.pop(0)
        self._exists = True
        self.saved.append(self.text)
        self.summaries.append(summary)
        if self.wiki is not None:
            self.wiki.saves.append(self._title)


class FakeWiki:
    """A wiki for tests.  Pages are looked up by title; any page not added
    is missing."""

    def __init__(self, *pages, user=BOT, rights=('bot',), request_redirects=('Infobox request',)):
        self.pages = {}
        self.run_page = FakePage(f'User:{user}/Run', 'yes')
        self.report_page = FakePage(f'User:{user}/InfoboxReport', 'Placeholder.')
        self.add(self.run_page, self.report_page, *pages)
        self.user, self.rights = user, set(rights)
        self.request_redirects = list(request_redirects)
        self.logged_in = False
        self.members = {}        # category -> [page titles]
        self.subcats = {}        # category -> [subcategory titles]
        self.transclusions = {}  # article title -> {Template:Infobox, ...}
        self.sticky = {}         # talk title -> categories it stays in, whatever the text
        self.read = []           # the categories read, in order
        self.parsed = []         # the titles parsed with categories_with
        self.saves = []          # the titles saved, in order
        self.broken_loads = 0    # this many load() calls fail
        self.loads = 0

    def add(self, *pages):
        for page in pages:
            page.wiki = self
            self.pages[page.title()] = page
        return self

    # Building the wiki.

    def tree(self, category, *, pages=(), subcats=()):
        self.members.setdefault(category, []).extend(pages)
        self.subcats.setdefault(category, []).extend(subcats)
        return self

    def request(self, article, article_text, talk_text, *, infobox=True,
                category=ROOT_CATEGORY, **talk_options):
        """An article and its talk page, the talk page in category."""
        self.add(FakePage(article, article_text),
                 FakePage(f'Talk:{article}', talk_text, **talk_options))
        if infobox:
            self.transclusions[article] = {'Template:Infobox'}
        self.tree(category, pages=[f'Talk:{article}'])
        return self

    # The Wiki interface.

    def login(self):
        self.logged_in = True
        return self.user

    def has_right(self, right):
        return right in self.rights

    def page(self, title, ns=0):
        return self.pages.get(title) or FakePage(title, exists=False, wiki=self)

    def load(self, titles):
        self.loads += 1
        if self.broken_loads:
            self.broken_loads -= 1
            raise ConnectionError('API timed out')
        for title in list(titles):
            yield self.page(title)

    def text_of(self, title):
        page = self.page(title)
        return page.text if page.exists() else None

    def last_change(self, title):
        page = self.page(title)
        if not page.exists():
            return None
        return page.latest_revision.timestamp, page.latest_revision.user

    def redirects_to(self, title):
        return list(self.request_redirects)

    def subcategories(self, category):
        return list(self.subcats.get(category, []))

    def category_pages(self, category):
        self.read.append(category)
        yield from self.members.get(category, [])

    def transcluding(self, titles, candidates):
        candidates = set(candidates)
        return {title: self.transclusions[title] & candidates for title in titles
                if self.transclusions.get(title, set()) & candidates}

    def categories_with(self, title, text):
        """As MediaWiki would categorise the talk page: [[Category:...]]
        links, {{Infobox requested}}, and the banners' needs-infobox."""
        self.parsed.append(title)
        found = set(self.sticky.get(title, ()))
        found |= {'Category:' + m.strip() for m in re.findall(r'\[\[\s*Category\s*:([^\]|]+)',
                                                              text)}
        for template in mwparserfromhell.parse(text).filter_templates():
            name = normalize_template_name(template.name)
            if name in ('Infobox requested', *self.request_redirects):
                found.add(ROOT_CATEGORY)
            for param in template.params:
                if normalize_param(param.name) == 'needs-infobox' and is_yes(param.value):
                    found.add(BANNERS.get(name, ROOT_CATEGORY))
        return found


def options(tmp_path, **changes):
    return Options(**{'out_dir': tmp_path / 'out', **changes})
