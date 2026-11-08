"""The tasks' settings, and how they check a batch of articles."""

from infoboxsweep.request import remove_requests
from infoboxsweep.tasks import INFOBOX, PHOTO, TASKS
from tests.fakes import INFOBOX_ARTICLE, FakePage, FakeWiki


def test_tasks():
    assert TASKS == {'infoboxsweep': INFOBOX, 'imagesweep': PHOTO}
    assert PHOTO.root == 'Category:Wikipedia requested photographs'
    assert PHOTO.report == 'ImageReport' and INFOBOX.report == 'InfoboxReport'


def test_which_categories_are_followed():
    for name in ('Category:Wikipedia requested photographs in Ohio',
                 'Category:Wikipedia requested images of people',
                 'Category:Wikipedia requested pictures of buildings'):
        assert PHOTO.follows(name) and PHOTO.is_request_category(name)
    assert not PHOTO.follows('Category:Buildings in Ohio')
    assert not PHOTO.is_request_category('Category:Photographers from Ohio')
    assert PHOTO.keyword_text() == '"photograph" or "photo" or "image" or "picture"'


def test_check_infoboxes():
    wiki = FakeWiki(FakePage('A', INFOBOX_ARTICLE), FakePage('B', 'Text.'))
    wiki.transclusions['A'] = {'Template:Infobox'}
    found = INFOBOX.check(wiki, [wiki.page('A'), wiki.page('B')], ['Infobox requested'])
    assert found['A'].found and not found['B'].found


def test_check_photos():
    wiki = FakeWiki(FakePage('A'), FakePage('B'), FakePage('C'))
    wiki.photo('A').photo('B', 'File:Flag of B.jpg')
    found = PHOTO.check(wiki, [wiki.page(t) for t in 'ABC'], ['Image requested'])
    assert found['A'].found
    assert not found['B'].found and 'has "flag"' in found['B'].evidence
    assert found['C'].evidence == 'no lead image'
    assert INFOBOX.check(wiki, [], []) == {} and PHOTO.check(wiki, [], []) == {}


def remove(text):
    return remove_requests(text, ['Image requested', 'Reqphoto'],
                           ['Category:Wikipedia requested photographs'],
                           params=PHOTO.request_params, template_params=PHOTO.template_params,
                           details=PHOTO.details)


def test_photo_requests_removed():
    for before, after in [
        ('{{WikiProject Ohio|needs-photo=yes}}', '{{WikiProject Ohio}}'),
        ('{{WikiProject Ohio|class=B|image-needed=y|importance=low}}',
         '{{WikiProject Ohio|class=B|importance=low}}'),
        ('{{Talk header}}\n{{Image requested|in=Ohio}}\n== A ==', '{{Talk header}}\n== A =='),
        ('{{reqphoto|in=Ohio|in2=Kentucky|date=May 2020}}\nText', 'Text'),
        ('{{Image requested|}}\nText', 'Text'),
        ('[[Category:Wikipedia requested photographs]]\nText', 'Text'),
    ]:
        result = remove(before)
        assert result.text == after and result.specific == [], before


def test_particular_requests_are_left_for_a_human():
    for text, particular in [
        ('{{Image requested|the interior}}',
         '{{Image requested}} asks for something particular: the interior'),
        ('{{Image requested|in=Ohio|of=the dam at night}}',
         '{{Image requested}} asks for something particular: of=the dam at night'),
        ('{{WikiProject Ohio|needs-photo=yes|photo-details=the interior}}',
         '{{WikiProject Ohio}} asks for something particular: photo-details=the interior'),
    ]:
        result = remove(text)
        assert not result.changed and result.specific == [particular]
    # An empty details parameter asks for nothing in particular.
    assert remove('{{WikiProject Ohio|needs-photo=yes|photo-details=}}').changed
