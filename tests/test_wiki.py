"""infoboxsweep.wiki, with stand-ins for Pywikibot's Site, Page and Category, to
check it asks Pywikibot for the right things."""

import pytest

from infoboxsweep import wiki as wiki_module
from infoboxsweep.wiki import BATCH, Wiki


class StubRevision:
    def __init__(self, timestamp, user):
        self.timestamp, self.user = timestamp, user


class StubPage:
    def __init__(self, site, title, ns=0):
        if ns == 10 and ':' not in title:
            title = 'Template:' + title
        self.site, self._title = site, title
        self.text = site.texts.get(title, '')
        self.latest_revision = site.revisions.get(title)

    def title(self, *, with_ns=True):
        return self._title.split(':', 1)[1] if not with_ns and ':' in self._title else self._title

    def exists(self):
        return self._title in self.site.texts

    def isRedirectPage(self):
        return self._title in self.site.redirect_targets

    def getRedirectTarget(self):
        return StubPage(self.site, self.site.redirect_targets[self._title])

    def redirects(self, *, namespaces):
        self.site.calls.append(('redirects', self._title, namespaces))
        return [StubPage(self.site, t) for t, target in self.site.redirect_targets.items()
                if target == self._title]


class StubCategory(StubPage):
    def members(self, *, member_type):
        self.site.calls.append(('members', self._title, member_type))
        return [StubPage(self.site, t) for t in self.site.members[self._title][member_type[0]]]


class StubRequest:
    def __init__(self, site, params):
        self.site, self.params = site, params

    def submit(self):
        self.site.calls.append(('request', dict(self.params)))
        return self.site.responses.pop(0)


class StubSite:
    def __init__(self, texts=None, logs_in=True):
        self.texts = texts or {}
        self.revisions, self.redirect_targets, self.members = {}, {}, {}
        self.responses = []
        self.logs_in, self._logged_in = logs_in, False
        self.calls = []

    def login(self):
        self._logged_in = self.logs_in

    def logged_in(self):
        return self._logged_in

    def username(self):
        return 'ExampleBot'

    def has_right(self, right):
        return right == 'bot'

    def preloadpages(self, pages, groupsize):
        pages = list(pages)
        self.calls.append(('preload', [p.title() for p in pages], groupsize))
        # Like Pywikibot's, as the API gives them: not in the order asked,
        # and without the missing ones.
        return [p for p in reversed(pages) if p.exists()]

    def simple_request(self, **params):
        return StubRequest(self, params)


@pytest.fixture(autouse=True)
def stub_pywikibot(monkeypatch):
    monkeypatch.setattr(wiki_module.pywikibot, 'Page', StubPage)
    monkeypatch.setattr(wiki_module.pywikibot, 'Category', StubCategory)


def test_login():
    assert Wiki(StubSite()).login() == 'ExampleBot'
    with pytest.raises(RuntimeError, match='Could not log in'):
        Wiki(StubSite(logs_in=False)).login()
    assert Wiki(StubSite()).has_right('bot')


def test_load_keeps_the_order_and_the_missing_pages():
    site = StubSite({'Talk:A': 'a', 'Talk:C': 'c'})
    pages = list(Wiki(site).load(['Talk:A', 'Talk:B', 'Talk:C']))
    assert [p.title() for p in pages] == ['Talk:A', 'Talk:B', 'Talk:C']
    assert [p.exists() for p in pages] == [True, False, True]
    assert site.calls == [('preload', ['Talk:A', 'Talk:B', 'Talk:C'], BATCH)]


def test_text_of_and_last_change():
    site = StubSite({'User:X/Run': 'yes'})
    site.revisions['User:X/Run'] = StubRevision('when', '')
    wiki = Wiki(site)
    assert wiki.text_of('User:X/Run') == 'yes' and wiki.text_of('Nope') is None
    assert wiki.last_change('User:X/Run') == ('when', None)
    assert wiki.last_change('Nope') is None


def test_redirects_to():
    site = StubSite()
    site.redirect_targets = {'Template:Infobox request': 'Template:Infobox requested'}
    assert Wiki(site).redirects_to('Infobox requested') == ['Infobox request']
    assert site.calls == [('redirects', 'Template:Infobox requested', [10])]


def test_redirects_to_a_redirect():
    # Asked about a redirect: the template it redirects to, and its other
    # redirects.
    site = StubSite({'Template:Reqphoto': '#REDIRECT', 'Template:Photo requested': 'x'})
    site.redirect_targets = {'Template:Reqphoto': 'Template:Photo requested',
                             'Template:Needs photo': 'Template:Photo requested'}
    assert Wiki(site).redirects_to('Reqphoto') == ['Photo requested', 'Needs photo']


def test_category_members():
    site = StubSite()
    site.members['Category:R'] = {'subcat': ['Category:S'], 'page': ['Talk:A', 'Talk:B']}
    wiki = Wiki(site)
    assert wiki.subcategories('Category:R') == ['Category:S']
    assert list(wiki.category_pages('Category:R')) == ['Talk:A', 'Talk:B']
    assert site.calls == [('members', 'Category:R', ['subcat']),
                          ('members', 'Category:R', ['page'])]


def test_transcluding_in_batches_with_continuation():
    site = StubSite()
    titles = [f'A{i}' for i in range(BATCH + 1)]
    site.responses = [
        {'query': {'pages': [{'title': 'A0', 'templates': [{'title': 'Template:Infobox'}]},
                             {'title': 'A1'}]},
         'continue': {'tlcontinue': '5|10|Infobox', 'continue': '||'}},
        {'query': {'pages': [{'title': 'A0', 'templates': [{'title': 'Module:Infobox'}]}]}},
        {'query': {'pages': [{'title': f'A{BATCH}',
                              'templates': [{'title': 'Template:Infobox'}]}]}},
    ]
    found = Wiki(site).transcluding(titles, ['Template:Infobox', 'Module:Infobox'])
    assert found == {'A0': {'Template:Infobox', 'Module:Infobox'},
                     f'A{BATCH}': {'Template:Infobox'}}
    requests = [call[1] for call in site.calls]
    assert requests[0]['titles'] == '|'.join(titles[:BATCH])
    assert requests[0]['tltemplates'] == 'Template:Infobox|Module:Infobox'
    assert requests[1]['tlcontinue'] == '5|10|Infobox'
    assert requests[2]['titles'] == f'A{BATCH}'


def test_categories_with():
    site = StubSite()
    site.responses = [{'parse': {'categories': [
        {'category': 'Film_articles_needing_infoboxes', 'hidden': True}]}}]
    assert Wiki(site).categories_with('Talk:A', 'text') == {
        'Category:Film articles needing infoboxes'}
    [(_, params)] = site.calls
    assert params == {'action': 'parse', 'title': 'Talk:A', 'text': 'text',
                      'prop': 'categories', 'contentmodel': 'wikitext', 'formatversion': 2}


def test_page():
    page = Wiki(StubSite({'Template:X': 'x'})).page('X', ns=10)
    assert page.title() == 'Template:X' and page.text == 'x'


def test_lead_images():
    from infoboxsweep.photo import LeadImage
    site = StubSite()
    site.responses = [{'query': {'pages': [
        {'title': 'A', 'pageprops': {'page_image_free': 'Ohio_Statehouse.jpg',
                                     'page_image': 'Ohio_Statehouse.jpg'}},
        {'title': 'B', 'pageprops': {'page_image': 'Poster.jpg'}},
        {'title': 'C', 'pageprops': {}}, {'title': 'D'}]}}]
    assert Wiki(site).lead_images(['A', 'B', 'C', 'D']) == {
        'A': LeadImage('File:Ohio Statehouse.jpg', True), 'B': LeadImage('File:Poster.jpg', False)}
    [(_, params)] = site.calls
    assert params['prop'] == 'pageprops' and params['ppprop'] == 'page_image_free|page_image'


def test_file_info():
    from infoboxsweep.photo import FileInfo
    site = StubSite()
    site.responses = [{'query': {'pages': [
        {'title': 'File:A.jpg', 'imagerepository': 'shared',
         'imageinfo': [{'mime': 'image/jpeg', 'width': 3000, 'height': 2000}]},
        {'title': 'File:Gone.jpg', 'missing': True}]}}]
    assert Wiki(site).file_info(['File:A.jpg', 'File:Gone.jpg']) == {
        'File:A.jpg': FileInfo('image/jpeg', 3000, 2000)}
    [(_, params)] = site.calls
    assert params['prop'] == 'imageinfo' and params['iiprop'] == 'mime|size'


def test_redirect_targets():
    site = StubSite()
    site.responses = [{'query': {
        'normalized': [{'from': 'Template:Film_infobox', 'to': 'Template:Film infobox'}],
        'redirects': [{'from': 'Template:Film infobox', 'to': 'Template:Infobox film'}],
        'pages': [{'title': 'Template:Infobox film'}, {'title': 'Template:Use dmy dates'}]}}]
    assert Wiki(site).redirect_targets(['Film_infobox', 'Use dmy dates']) == {
        'Film_infobox': 'Infobox film'}
    [(_, params)] = site.calls
    assert params['redirects'] == 1
    assert params['titles'] == 'Template:Film_infobox|Template:Use dmy dates'
