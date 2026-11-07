"""Walking the category tree."""

import pytest

from infoboxsweep.tree import follows, walk
from tests.fakes import FakeWiki

ROOT = 'Category:Wikipedia articles with an infobox request'
FILM = 'Category:Film articles needing infoboxes'
SF = 'Category:Science fiction film articles needing infoboxes'
BIO = 'Category:Biography articles needing infoboxes'


def deep_wiki():
    return (FakeWiki()
            .tree(ROOT, pages=['Talk:A'], subcats=[FILM, BIO])
            .tree(FILM, pages=['Talk:B', 'Talk:A'], subcats=[SF])
            .tree(BIO, pages=['Talk:C', 'Talk:B'], subcats=[SF])   # SF has two parents
            .tree(SF, pages=['Talk:D', 'Talk:C'], subcats=[FILM]))  # and a loop back


def test_walks_every_level_once_and_lists_each_page_once():
    wiki = deep_wiki()
    tree = walk(wiki, ROOT)
    assert tree.categories == [ROOT, FILM, BIO, SF]
    assert wiki.read == tree.categories   # each read once, loop or not
    assert tree.pages == ['Talk:A', 'Talk:B', 'Talk:C', 'Talk:D']
    assert tree.listings == 7 and tree.duplicates == 3
    assert tree.depth == 2
    assert not tree.truncated and tree.not_followed == []


def test_does_not_follow_categories_without_infobox_in_the_name():
    wiki = FakeWiki().tree(ROOT, pages=['Talk:A'], subcats=['Category:Films', FILM])
    wiki.tree('Category:Films', pages=['Talk:Z']).tree(FILM, pages=['Talk:B'])
    tree = walk(wiki, ROOT)
    assert tree.pages == ['Talk:A', 'Talk:B']
    assert tree.not_followed == [('Category:Films', ROOT)]
    assert follows('Category:Wikipedia requested INFOBOXES in Peru')


def test_stops_at_max_categories():
    tree = walk(deep_wiki(), ROOT, max_categories=2)
    assert tree.truncated and tree.categories == [ROOT, FILM]


def test_check_is_called_before_each_category():
    calls = []

    def check():
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('stop')

    with pytest.raises(RuntimeError):
        walk(deep_wiki(), ROOT, check=check)
    assert len(calls) == 3


def test_an_empty_tree():
    tree = walk(FakeWiki(), ROOT)
    assert tree.categories == [ROOT] and tree.pages == [] and tree.depth == 0
