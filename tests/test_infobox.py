"""Does an article have an infobox?"""

from infoboxsweep.infobox import infobox_calls, verdict


def test_transcluding_an_infobox_is_having_one():
    found = verdict("'''Text'''", {'Template:Infobox', 'Module:Infobox'})
    assert found.found and found.review is None
    assert found.evidence == 'transcludes Module:Infobox, Template:Infobox'


def test_nothing_is_no_infobox():
    found = verdict("'''Text''' {{Cite web|url=x}}", set())
    assert not found.found and found.review is None


def test_a_call_without_the_transclusion_goes_to_a_human():
    found = verdict('{{infobox_person\n|name=X}}', set())
    assert not found.found
    assert '{{Infobox person}}' in found.review


def test_calls():
    text = ('{{Infobox film}}\n<!-- {{Infobox person}} -->\n{{Infobox requested}}\n'
            '{{Template:Infobox film}}\n{{Infobox album|cover={{Infobox song}}}}')
    assert infobox_calls(text, ignore=['Infobox requested']) == [
        'Infobox film', 'Infobox album', 'Infobox song']
    assert verdict('{{Infobox requested}}', set(), ignore=['Infobox requested']).review is None
