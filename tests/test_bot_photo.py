"""A whole run of the photograph task, against the fake wiki."""

from infoboxsweep import PHOTO_CATEGORY
from infoboxsweep.bot import Bot
from infoboxsweep.tasks import PHOTO
from infoboxsweep.wikireport import review_lines
from tests.fakes import OHIO_PHOTOS, PEOPLE_PHOTOS, FakePage, FakeWiki, options
from tests.test_bot import Clock

TALK = '{{WikiProject banner shell|\n{{WikiProject Ohio}}\n}}\n{{Image requested|in=Ohio}}\n'


def photo_wiki():
    wiki = FakeWiki()
    wiki.report_page = FakePage('User:ExampleBot/ImageReport', 'Placeholder.')
    wiki.add(wiki.report_page)
    wiki.tree(PHOTO_CATEGORY, subcats=[OHIO_PHOTOS, PEOPLE_PHOTOS, 'Category:Ohio'])
    for name in ('Statehouse', 'Lake', 'Flagged', 'Logo PNG', 'Pending', 'Interior'):
        wiki.add(FakePage(name, "'''Text'''"))
    wiki.add(FakePage('Talk:Statehouse', TALK), FakePage('Talk:Lake', TALK),
             FakePage('Talk:Flagged', TALK), FakePage('Talk:Logo PNG', TALK),
             FakePage('Talk:Pending', TALK),
             FakePage('Talk:Interior', '{{Image requested|in=Ohio|the dome inside}}'),
             FakePage('Talk:John Doe', '{{WikiProject Biography|needs-photo=yes}}'),
             FakePage('John Doe', "'''John Doe'''"))
    wiki.photo('Statehouse', 'File:Ohio Statehouse.jpg')
    wiki.photo('Flagged', 'File:Flag of Ohio.svg', mime='image/svg+xml')
    wiki.photo('Logo PNG', 'File:Lake Erie.png', mime='image/png')
    wiki.photo('John Doe', 'File:John Doe 2010.jpg')
    wiki.photo('Interior', 'File:Dome outside.jpg')
    wiki.tree(OHIO_PHOTOS, pages=['Talk:Statehouse', 'Talk:Lake', 'Talk:Flagged',
                                  'Talk:Logo PNG', 'Talk:Pending', 'Talk:Interior'])
    wiki.tree(PEOPLE_PHOTOS, pages=['Talk:John Doe', 'Talk:Statehouse'])
    wiki.tree('Category:Ohio', pages=['Talk:Should not be read'])
    return wiki


def run(wiki, tmp_path, **changes):
    bot = Bot(wiki, options(tmp_path, task=PHOTO, **changes), now=Clock())
    return bot, bot.run()


def test_dry_run(tmp_path):
    wiki = photo_wiki()
    bot, report = run(wiki, tmp_path)
    assert 'Category:Ohio' not in wiki.read
    assert report.categories == 3 and report.found == 7 and report.duplicates == 1
    assert report.checked == 7 and report.fulfilled == 3 and report.unfulfilled == 3
    assert [edit.talk for edit in report.edits] == ['Talk:Statehouse', 'Talk:John Doe']
    statehouse, doe = report.edits
    assert statehouse.removed == ['{{Image requested}}']
    assert statehouse.evidence == 'lead image [[:File:Ohio Statehouse.jpg]] (JPEG, 3000×2000)'
    assert doe.removed == ['needs-photo=yes from {{WikiProject Biography}}']
    reviews = {title: why for title, _, why in report.reviews}
    assert 'is a PNG: is it a photograph' in reviews['Talk:Logo PNG']
    assert reviews['Talk:Interior'] == (
        'the article has a photograph (lead image [[:File:Dome outside.jpg]] (JPEG, '
        '3000×2000)), but {{Image requested}} asks for something particular: the dome inside')
    assert 'without "photograph" or "photo" or "image" or "picture"' in reviews['Category:Ohio']
    assert wiki.saves == []
    text = bot.report_path.read_text()
    assert bot.report_path.name.startswith('dry-run-photograph-')
    assert 'article has a photograph: 3' in text


def test_live_run(tmp_path):
    wiki = photo_wiki()
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert wiki.page('Talk:Statehouse').saved == [
        '{{WikiProject banner shell|\n{{WikiProject Ohio}}\n}}\n']
    assert wiki.page('Talk:Statehouse').summaries == [
        'Removing photograph request ({{Image requested}}): [[Statehouse]] has a photograph, '
        '[[:File:Ohio Statehouse.jpg]] '
        '([[Wikipedia:Bots/Requests for approval/ZackBot 15|ZackBot 15]])']
    # Reported on its own page, not the infobox task's.
    page = wiki.report_page
    assert page.title() == 'User:ExampleBot/ImageReport'
    assert "task removing photograph requests" in page.text
    assert '[[:Category:Wikipedia requested photographs]]' in page.text
    assert '|| 3 || 7 || 7 || 2 || [[#Needs manual review|3]] || finished' in page.text
    assert sorted(review_lines(page.text)) == ['Category:Ohio', 'Talk:Interior', 'Talk:Logo PNG']
    assert wiki.page('User:ExampleBot/InfoboxReport').saved == []


def test_still_in_a_photo_category(tmp_path):
    wiki = photo_wiki()
    wiki.sticky['Talk:Statehouse'] = {OHIO_PHOTOS}
    _, report = run(wiki, tmp_path, pages=('Statehouse',))
    [(_, _, why)] = report.reviews
    assert why.startswith('the article has a photograph, but after removing')


MUSICIANS = 'Category:Wikipedia requested images of musicians'
WASHINGTON = 'Category:Wikipedia requested images of people of Washington'


def cobain_wiki(talk):
    """Kurt Cobain as he was on 8 November 2026: the lead image a free JPEG,
    260×346, of him at the 1992 MTV Video Music Awards."""
    wiki = FakeWiki()   # {{Photo requested}} is a template, {{Reqphoto}} its redirect
    wiki.tree(PHOTO_CATEGORY, subcats=[MUSICIANS, WASHINGTON])
    wiki.add(FakePage('Kurt Cobain', "'''Kurt Donald Cobain''' was an American musician."),
             FakePage('Talk:Kurt Cobain', talk))
    wiki.photo('Kurt Cobain', 'File:Nirvana around 1992 (cropped).jpg', size=(260, 346))
    wiki.tree(MUSICIANS, pages=['Talk:Kurt Cobain'])
    wiki.tree(WASHINGTON, pages=['Talk:Kurt Cobain'])
    return wiki


def test_kurt_cobain_asks_for_a_better_photo(tmp_path):
    talk = ('{{Talk header}}\n{{Photo requested|musicians|people of Washington|reason=Current '
            'image and all other alternatives are very blurry and low-quality.}}\n')
    _, report = run(cobain_wiki(talk), tmp_path)
    assert report.found == 1 and report.duplicates == 1 and report.fulfilled == 1
    assert report.edits == []
    [(title, article, why)] = report.reviews
    assert (title, article) == ('Talk:Kurt Cobain', 'Kurt Cobain')
    assert why == (
        'the article has a photograph (lead image [[:File:Nirvana around 1992 (cropped).jpg]] '
        '(JPEG, 260×346)), but {{Photo requested}} asks for something particular: '
        'reason=Current image and all other alternatives are very blurry and low-quality.')


def test_kurt_cobain_without_a_reason(tmp_path):
    _, report = run(cobain_wiki('{{Talk header}}\n{{Photo requested|musicians|people of '
                                'Washington}}\n'), tmp_path)
    [edit] = report.edits
    assert edit.removed == ['{{Photo requested}}'] and report.reviews == []
    assert '+{{Talk header}}' not in edit.diff and '-{{Photo requested|' in edit.diff
