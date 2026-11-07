"""Taking infobox requests off talk pages."""

import pytest

from infoboxsweep.request import remove_requests

NAMES = ['Infobox requested', 'Infobox request', 'Needs infobox']
ROOT = 'Category:Wikipedia articles with an infobox request'


def remove(text, categories=(ROOT,)):
    return remove_requests(text, NAMES, categories)


@pytest.mark.parametrize(('before', 'after'), [
    # A banner in the banner shell, on one line.
    ('{{WikiProject banner shell|class=C|\n{{WikiProject Film|needs-infobox=yes}}\n}}',
     '{{WikiProject banner shell|class=C|\n{{WikiProject Film}}\n}}'),
    # In the middle of a banner's parameters.
    ('{{WikiProject Biography|living=no|needs-infobox=y|listas=Doe, John}}',
     '{{WikiProject Biography|living=no|listas=Doe, John}}'),
    # A banner over several lines.
    ('{{WikiProject Film\n|class=C\n|needs-infobox=yes\n}}\nText',
     '{{WikiProject Film\n|class=C\n}}\nText'),
    # The last parameter, with }} on its line: }} goes on its own line.
    ('{{WikiProject Film\n| class = C\n| needs-infobox = yes}}',
     '{{WikiProject Film\n| class = C\n}}'),
    ('{{WikiProject Film\n| class = C |needs-infobox=yes\n}}',
     '{{WikiProject Film\n| class = C\n}}'),
    # Other names for the parameter, and other ways of saying yes.
    ('{{WikiProject X|Needs_Infobox=Yes<!-- asked -->|importance=low}}',
     '{{WikiProject X|importance=low}}'),
    ('{{WikiProject Ships|infobox=TRUE}}', '{{WikiProject Ships}}'),
    ('{{WP Albums|infobox-needed=1}}', '{{WP Albums}}'),
    # {{Infobox requested}} on its own line: the line goes too.
    ('{{Talk header}}\n{{Infobox requested|date=May 2020}}\n{{WikiProject Ships}}',
     '{{Talk header}}\n{{WikiProject Ships}}'),
    # ... by a redirect, with odd spacing and underscores.
    ('{{talk header}}\n  {{ needs_infobox }}  \n== A ==', '{{talk header}}\n== A =='),
    ('Text {{Infobox request}} more', 'Text  more'),
    ('Last line\n{{Template:Infobox requested}}', 'Last line\n'),
    # The category, added by hand.
    ('[[Category:Wikipedia articles with an infobox request]]\nfoo', 'foo'),
    ('foo [[category: Wikipedia_articles with an infobox request|Sort]]', 'foo '),
])
def test_removes(before, after):
    result = remove(before)
    assert result.text == after
    assert result.changed and result.removed


@pytest.mark.parametrize('text', [
    '{{WikiProject Film|needs-infobox=no}}',
    '{{WikiProject Film|needs-infobox=}}',
    '{{WikiProject Film|needs-photo=yes}}',
    '{{WikiProject Film|yes}}',   # unnamed parameters are never removed
    '<!-- {{Infobox requested}} -->',
    '<nowiki>{{Infobox requested}}</nowiki>',
    # A link to the category isn't in it.
    'See [[:Category:Wikipedia articles with an infobox request]].',
    '[[Category:Some other category]]',
    '[[Category:]]',
])
def test_leaves_alone(text):
    result = remove(text)
    assert result.text == text
    assert not result.changed and result.removed == []


def test_describes_what_it_removed():
    result = remove('{{Infobox requested}}\n{{WikiProject Film|needs-infobox = yes }}\n'
                    '[[Category:Wikipedia articles with an infobox request]]')
    assert result.removed == ['{{Infobox requested}}',
                              'needs-infobox=yes from {{WikiProject Film}}',
                              '[[Category:Wikipedia articles with an infobox request]]']
    assert result.text == '{{WikiProject Film}}\n'


def test_a_request_inside_another_removed_call():
    # Nested in a call that is itself removed: removed once, with it.
    result = remove('{{Infobox requested|note={{Needs infobox}}}}\nText')
    assert result.text == 'Text'


def test_subcategories_of_the_tree():
    sub = 'Category:Film articles needing infoboxes'
    result = remove('[[Category:Film articles needing infoboxes]]', [ROOT, sub])
    assert result.text == ''
    assert not remove('[[Category:Film articles needing infoboxes]]').changed
