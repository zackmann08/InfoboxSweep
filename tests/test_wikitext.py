from infoboxsweep.wikitext import (
    is_yes,
    normalize_param,
    normalize_template_name,
    normalize_title,
    strip_comments,
)


def test_helpers():
    assert strip_comments('a<!-- b -->c<!-- d') == 'ac'
    assert normalize_title('foo_bar  baz') == 'Foo bar baz'
    assert normalize_template_name(' template : infobox_requested ') == 'Infobox requested'
    assert normalize_param(' Needs_Infobox ') == 'needs-infobox'
    assert normalize_param('needs infobox<!-- x -->') == 'needs-infobox'
    assert all(is_yes(v) for v in ('yes', ' Y ', 'true', '1', 'on', 'yes<!-- c -->'))
    assert not any(is_yes(v) for v in ('', 'no', 'maybe', '0'))
