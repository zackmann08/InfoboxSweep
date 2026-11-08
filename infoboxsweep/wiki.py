"""Everything the bot asks of the wiki, in one place.

The rest of the bot reaches the wiki only through a Wiki object, which makes
it easy to see what the bot does there, and lets the tests use a fake wiki.
Pages are Pywikibot Page objects; the WikiPage protocol lists the parts of
them the bot relies on.
"""

import logging
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any, Protocol

import pywikibot

from .photo import FileInfo, LeadImage

log = logging.getLogger('infoboxsweep')

# Pages whose text is loaded in one API request.  The API cuts off any
# response over 12 MB, which 50 pages' text stays well under.  It's also
# the most titles a request may name without the bot flag.
BATCH = 50
TEMPLATE_NS = 10
CATEGORY_NS = 14


class WikiPage(Protocol):
    """The parts of a Pywikibot Page the bot uses (with Pywikibot's names,
    camelCase included)."""

    text: str
    latest_revision: Any   # a Pywikibot Revision: .timestamp and .user

    def title(self, *, with_ns: bool = True) -> str: ...
    def namespace(self) -> Any: ...
    def exists(self) -> bool: ...
    def isRedirectPage(self) -> bool: ...
    def isTalkPage(self) -> bool: ...
    def toggleTalkPage(self) -> 'WikiPage | None': ...
    def botMayEdit(self) -> bool: ...
    def save(self, *, summary: str, minor: bool, bot: bool, quiet: bool) -> None: ...


class Wiki:
    """A wiki, through Pywikibot."""

    def __init__(self, site: Any) -> None:
        self.site = site

    # -- the account -------------------------------------------------------

    def login(self) -> str:
        """Log in with the account in user-config.py; return its name."""
        self.site.login()
        if not self.site.logged_in():
            raise RuntimeError('Could not log in: check the account name in user-config.py, '
                               'and the bot password in user-password.py')
        return str(self.site.username())

    def has_right(self, right: str) -> bool:
        return bool(self.site.has_right(right))

    # -- pages -------------------------------------------------------------

    def page(self, title: str, ns: int = 0) -> WikiPage:
        """A page, not yet loaded.  ns is the namespace for titles without a
        prefix: 10 for templates."""
        page: WikiPage = pywikibot.Page(self.site, title, ns=ns)
        return page

    def load(self, titles: Iterable[str]) -> Iterator[WikiPage]:
        """The pages with these titles, their text loaded BATCH to a request,
        in the order given."""
        pages = [self.page(title) for title in titles]
        loaded = {page.title(): page
                  for page in self.site.preloadpages(pages, groupsize=BATCH)}
        # preloadpages leaves out pages that don't exist; give them as they are.
        for page in pages:
            yield loaded.get(page.title(), page)

    def text_of(self, title: str) -> str | None:
        """A page's text, or None if it doesn't exist."""
        page = self.page(title)
        return page.text if page.exists() else None

    def last_change(self, title: str) -> tuple[datetime, str | None] | None:
        """When a page was last changed, and by whom (None if hidden); None
        if the page doesn't exist."""
        page = self.page(title)
        if not page.exists():
            return None
        revision = page.latest_revision
        return revision.timestamp, revision.user or None

    def redirects_to(self, title: str) -> list[str]:
        """The other names, without the Template: prefix, of the template
        called title: the templates that redirect to it.  If title is itself
        a redirect, the template it redirects to, and those that redirect to
        that."""
        page = pywikibot.Page(self.site, title, ns=TEMPLATE_NS)
        names = []
        if page.exists() and page.isRedirectPage():
            page = page.getRedirectTarget()
            names.append(page.title(with_ns=False))
        names += [p.title(with_ns=False) for p in page.redirects(namespaces=[TEMPLATE_NS])]
        return [name for name in dict.fromkeys(names) if name != title]

    # -- categories --------------------------------------------------------

    def subcategories(self, category: str) -> list[str]:
        """The titles of the category's subcategories, one level down."""
        cat = pywikibot.Category(self.site, category)
        return [sub.title() for sub in cat.members(member_type=['subcat'])]

    def category_pages(self, category: str) -> Iterator[str]:
        """The titles of the pages in the category, not counting its
        subcategories and files: titles only, 5,000 to a request with the
        bot flag."""
        cat = pywikibot.Category(self.site, category)
        for page in cat.members(member_type=['page']):
            yield page.title()

    # -- what pages transclude, and how they'd be categorised -------------

    def transcluding(self, titles: list[str], candidates: Iterable[str]) -> dict[str, set[str]]:
        """{title: which of candidates it transcludes} for titles, BATCH to
        a request, through the API's prop=templates, asked only about the
        candidates.  Titles that transclude none are left out."""
        found: dict[str, set[str]] = {}
        for page in self._query_pages(titles, prop='templates', tllimit='max',
                                      tltemplates='|'.join(candidates)):
            used = {t['title'] for t in page.get('templates', [])}
            if used:
                found.setdefault(page['title'], set()).update(used)
        return found

    def _query_pages(self, titles: list[str], **params: Any) -> Iterator[dict[str, Any]]:
        """The pages of a query about titles, BATCH to a request, following
        continuation: each page as many times as the API gives it."""
        for start in range(0, len(titles), BATCH):
            request: dict[str, Any] = {'action': 'query', 'formatversion': 2,
                                       'titles': '|'.join(titles[start:start + BATCH]), **params}
            while True:
                data = self.site.simple_request(**request).submit()
                yield from data.get('query', {}).get('pages', [])
                if 'continue' not in data:
                    break
                request.update(data['continue'])

    def lead_images(self, titles: list[str]) -> dict[str, LeadImage]:
        """{title: its lead image} for those of titles that have one, as the
        PageImages extension chose it from the lead section: the free one
        (page_image_free) if there is one, or else the non-free one
        (page_image)."""
        found: dict[str, LeadImage] = {}
        for page in self._query_pages(titles, prop='pageprops',
                                      ppprop='page_image_free|page_image'):
            props = page.get('pageprops', {})
            free = props.get('page_image_free')
            name = free or props.get('page_image')
            if name:
                found[page['title']] = LeadImage('File:' + name.replace('_', ' '), bool(free))
        return found

    def file_info(self, files: list[str]) -> dict[str, FileInfo]:
        """{file: its type and size} for those of files (with File:) that
        exist, here or on Commons."""
        found: dict[str, FileInfo] = {}
        for page in self._query_pages(files, prop='imageinfo', iiprop='mime|size'):
            for info in page.get('imageinfo', [])[:1]:
                found[page['title']] = FileInfo(str(info.get('mime', '')),
                                                int(info.get('width', 0)),
                                                int(info.get('height', 0)))
        return found

    def categories_with(self, title: str, text: str) -> set[str]:
        """The categories, with Category:, the page title would be in with
        text, as MediaWiki parses it, without saving anything."""
        data = self.site.simple_request(
            action='parse', title=title, text=text, prop='categories',
            contentmodel='wikitext', formatversion=2).submit()
        return {'Category:' + c['category'].replace('_', ' ')
                for c in data['parse'].get('categories', [])}
