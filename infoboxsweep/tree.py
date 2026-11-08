"""The maintenance category's whole tree: every subcategory, however deep,
and every page in any of them, each once.

The walk is breadth first, from the root category.  Each category is read
once, however many parents it has, so a loop in the tree (a category that
is, through others, its own subcategory) ends the walk there instead of
going round for ever.  A page in more than one category is listed once, in
the order first found.

Only subcategories with one of the task's keywords in their name are
followed: "infobox" for infobox requests, "photograph", "photo", "image" or
"picture" for photograph requests.  Every category in those trees has one
("Film articles needing infoboxes", "Wikipedia requested photographs in
Ohio"); a category without one was most likely put in the tree by mistake,
and following it could take the bot through thousands of pages that never
asked for anything.  Such categories are listed on the report, for a human,
and not followed.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .wiki import Wiki

log = logging.getLogger('infoboxsweep')

__all__ = ['Tree', 'walk']

# The most categories the walk reads: far more than the tree has, so that a
# category tree gone wrong can't keep the bot walking it for ever.
MAX_CATEGORIES = 10_000


@dataclass
class Tree:
    root: str
    categories: list[str] = field(default_factory=list)       # in the order read
    pages: list[str] = field(default_factory=list)            # each once, in the order found
    listings: int = 0            # pages found, counting each time a page was found again
    not_followed: list[tuple[str, str]] = field(default_factory=list)   # (category, parent)
    depth: int = 0               # how many levels below the root the tree goes
    truncated: bool = False      # stopped at MAX_CATEGORIES

    @property
    def duplicates(self) -> int:
        return self.listings - len(self.pages)


def follows(category: str) -> bool:
    """Whether the walk goes into a subcategory, by default: one about
    infoboxes."""
    return 'infobox' in category.lower()


def walk(wiki: Wiki, root: str, *, max_categories: int = MAX_CATEGORIES,
         check: Callable[[], None] = lambda: None,
         follow: Callable[[str], bool] = follows) -> Tree:
    """The tree under root.  check is called before reading each category,
    so that the run can be stopped as the walk goes; follow says which
    subcategories to go into."""
    tree = Tree(root)
    seen_pages: set[str] = set()
    seen = {root}
    level = [root]
    depth = 0
    while level:
        below: list[str] = []
        for category in level:
            if len(tree.categories) >= max_categories:
                log.warning('Read %d categories: stopping the walk there', max_categories)
                tree.truncated = True
                return tree
            check()
            tree.categories.append(category)
            for title in wiki.category_pages(category):
                tree.listings += 1
                if title not in seen_pages:
                    seen_pages.add(title)
                    tree.pages.append(title)
            for sub in wiki.subcategories(category):
                if sub in seen:
                    continue
                seen.add(sub)
                if follow(sub):
                    below.append(sub)
                else:
                    log.warning('Not following %s, in %s: not a category for these requests',
                                sub, category)
                    tree.not_followed.append((sub, category))
        if below:
            depth += 1
        tree.depth = depth
        level = below
    log.info('The tree: %d categories, %d levels deep, %d pages (%d listed more than once)',
             len(tree.categories), tree.depth, len(tree.pages), tree.duplicates)
    return tree
