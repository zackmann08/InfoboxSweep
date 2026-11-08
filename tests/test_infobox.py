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


def test_designation_lists_are_not_infoboxes():
    # As on Gosford House: a box of heritage designations in the lead, and
    # no infobox.
    gosford = ("{{Use British English|date=May 2015}}\n{{Infobox designation list\n"
               "| embed = \n| designation1 = Listed building\n}}\n"
               "'''Gosford House''' is a neo-classical house.\n== History ==\n")
    for text in (gosford, gosford.replace('Infobox designation list', 'designation list')):
        found = verdict(text, RENDERS)
        assert not found.found and found.review is None
        assert found.evidence.startswith('no infobox in the lead section')
    # Another name for it, by redirect.
    found = verdict('{{Infobox heritage designations}}\nText', RENDERS,
                    resolved={'Infobox heritage designations': 'Infobox designation list'})
    assert not found.found and found.review is None
    # Below the lead, it isn't an infobox for a section either.
    assert verdict("Text\n== A ==\n{{Infobox designation list}}", RENDERS).review is None
    # With a real infobox, the article has one.
    found = verdict('{{Infobox building\n|name=X}}\n{{Infobox designation list}}\nText',
                    RENDERS)
    assert found.found and found.evidence.startswith('{{Infobox building}}')
    assert not is_infobox_name('Infobox designation list')
    assert not is_infobox_name('Designation list')


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
    # Only the lead templates of the articles that render an infobox, each
    # once, in one request.
    [names] = asked
    assert names[:3] == ['Infobox film', 'Film infobox', 'Use dmy dates']
    assert 'Short description' in names and len(names) == len(set(names))


def test_infobox_chinese_is_not_an_infobox():
    # Pages with only {{Chinese}} at the top: a box of a name's Chinese
    # forms, not the article's infobox.
    lead = ("{{Chinese\n| t = 紫禁城\n| p = Zǐjìnchéng\n}}\n"
            "'''Example''' is a place.\n== A ==\n")
    for text in (lead, lead.replace('{{Chinese', '{{Infobox Chinese'),
                 lead.replace('{{Chinese', '{{chinese')):
        found = verdict(text, RENDERS)
        assert not found.found and found.review is None, text
    # By another name for it, a redirect.
    found = verdict(lead.replace('{{Chinese', '{{Chinese name'), RENDERS,
                    resolved={'Chinese name': 'Infobox Chinese'})
    assert not found.found
    # With a real infobox too, the article has one.
    assert verdict('{{Infobox settlement|name=X}}\n' + lead, RENDERS).found
    assert not is_infobox_name('Infobox Chinese') and not is_infobox_name('Chinese')
