"""Does an article have an infobox?"""

from infoboxsweep.infobox import (
    infobox_calls,
    is_infobox_name,
    lead_section,
    template_calls,
    verdict,
)
from infoboxsweep.tasks import INFOBOX
from tests.fakes import FakePage, FakeWiki

RENDERS = {'Template:Infobox', 'Module:Infobox'}

# The leads of three articles that transclude Template:Infobox and Module:
# Infobox without having an infobox, as they were on 8 November 2026: the
# transclusions come from templates further down, such as side boxes,
# {{External media}} and navboxes.
BEAT_GENERATION = """{{short description|Literary movement}}
{{for-multi|the subculture surrounding the literary movement|Beatnik}}
{{Use American English|date=October 2026}}
{{Use mdy dates|date=May 2014}}
{{multiple image
| footer = Burroughs, Ginsberg and Kerouac
| image1 = Burroughs1983 crop b.jpg
}}
The '''Beat Generation''' was a literary subculture movement.

==Etymology==
{{Side box|text=...}}
"""
SAYFO = """{{Short description|Genocide of Assyrians (1914–1924)}}
{{pp-extended|small=yes}}
{{Featured article}}
{{Use American English|date=October 2022}}
{{Use dmy dates|date=November 2020}}
{{TOC limit|3}}
The '''Sayfo''' was the mass murder of Assyrian Christians.

== Terminology ==
{{Genocide navbox}}
"""
VIRGIL_FOX = """{{Short description|American organist (1912–1980)}}
{{Use American English|date=March 2026}}
{{Use mdy dates|date=March 2026}}
[[File:fox virgil.jpg|260px|thumb|Virgil Fox]]
'''Virgil Keel Fox''' was an American organist.

==Birth and studies==
{{External media|video1=...}}
"""


def test_transcluding_is_not_enough():
    for text in (BEAT_GENERATION, SAYFO, VIRGIL_FOX):
        found = verdict(text, RENDERS, ignore=['Infobox requested'])
        assert not found.found and found.review is None
        assert found.evidence.startswith('no infobox in the lead section (it transcludes')


def test_an_infobox_in_the_lead_that_renders():
    found = verdict("{{Short description|x}}\n{{Infobox person\n|name=X}}\n'''X'''\n== A ==\n",
                    {'Template:Infobox'})
    assert found.found and found.review is None
    assert found.evidence == ('{{Infobox person}} in the lead section, which transcludes '
                              'Template:Infobox')
    # Taxoboxes and chemboxes are named their own way.
    assert verdict('{{Automatic taxobox|taxon=Felis}}', {'Template:Automatic taxobox'}).found
    # A template that redirects to an infobox.
    assert verdict('{{Film infobox|name=X}}', RENDERS,
                   resolved={'Film infobox': 'Infobox film'}).found


def test_left_for_a_human():
    found = verdict('{{infobox_person\n|name=X}}', set())
    assert not found.found and '{{Infobox person}}' in found.review
    assert 'does not transclude' in found.review
    found = verdict("'''X'''\n== Career ==\n{{Infobox album|name=Y}}\n", RENDERS)
    assert not found.found
    assert found.review == ('the article calls {{Infobox album}}, but only below its lead '
                            "section: is it the article's infobox, or one for a section?")


def test_nothing_is_no_infobox():
    found = verdict("'''Text''' {{Cite web|url=x}}", set())
    assert not found.found and found.review is None and found.evidence == ''
    assert verdict('{{Infobox requested}}', set(), ignore=['Infobox requested']).review is None


def test_lead_section():
    assert lead_section("Lead\n{{Infobox x}}\n==A==\nBody\n== B ==\n") == "Lead\n{{Infobox x}}\n"
    assert lead_section('Lead\n==A== <!-- c -->\nBody') == 'Lead\n'
    assert lead_section('Lead, x == y, no heading') == 'Lead, x == y, no heading'


def test_calls():
    text = ('{{Infobox film}}\n<!-- {{Infobox person}} -->\n{{Infobox requested}}\n'
            '{{Template:Infobox film}}\n{{Infobox album|cover={{Infobox song}}}}\n'
            '{{#if:x|y}}{{User:X/box}}<nowiki>{{Infobox ship}}</nowiki>{{Chembox}}')
    assert template_calls(text, ignore=['Infobox requested']) == [
        'Infobox film', 'Infobox album', 'Infobox song', 'Chembox']
    assert infobox_calls(text, ignore=['Infobox requested']) == [
        'Infobox film', 'Infobox album', 'Infobox song', 'Chembox']
    # A redirect to the request template is not an infobox.
    assert infobox_calls('{{Needs infobox}}', ['Infobox requested'],
                         {'Needs infobox': 'Infobox requested'}) == []
    assert is_infobox_name('Infobox settlement') and is_infobox_name('Speciesbox')
    assert not is_infobox_name('Sidebar') and not is_infobox_name('External media')


def test_check_infoboxes_resolves_only_what_it_must():
    asked = []
    wiki = FakeWiki(FakePage('Named', '{{Infobox film}}\nText'),
                    FakePage('Renamed', '{{Film infobox}}\n{{Use dmy dates}}\nText'),
                    FakePage('Beat Generation', BEAT_GENERATION), FakePage('Plain', 'Text'))
    for title in ('Named', 'Renamed', 'Beat Generation'):
        wiki.transclusions[title] = RENDERS
    wiki.template_redirects = {'Film infobox': 'Infobox film'}
    real = wiki.redirect_targets
    wiki.redirect_targets = lambda names: asked.append(list(names)) or real(names)
    found = INFOBOX.check(wiki, [wiki.page(t) for t in ('Named', 'Renamed', 'Beat Generation',
                                                        'Plain')], ['Infobox requested'])
    assert found['Named'].found and found['Renamed'].found
    assert not found['Beat Generation'].found and not found['Plain'].found
    # Only the templates of the articles that render an infobox without
    # naming one, each once.
    [names] = asked
    assert names[:2] == ['Film infobox', 'Use dmy dates']
    assert 'Infobox film' not in names and 'Short description' in names
