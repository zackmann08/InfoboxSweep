"""The bot's tasks: what each asks the wiki, and how it reports.

Each task works the same way (see infoboxsweep.bot): walk a maintenance
category's tree, check the article each talk page belongs to, and take the
request off the talk page if the article has what was asked for.  A Task
says which category, which request template and banner parameters, how to
check the article, and where and how to report.

- INFOBOX (``infoboxsweep``): Category:Wikipedia articles with an infobox
  request; the article must have an infobox (infoboxsweep.infobox).
- PHOTO (``imagesweep``): Category:Wikipedia requested photographs; the
  article must have a photograph of its subject (infoboxsweep.photo).
"""

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass

from . import BRFA, PHOTO_BRFA, PHOTO_CATEGORY, ROOT_CATEGORY
from .infobox import INFOBOX_PAGES, Verdict, verdict
from .photo import photo_verdict
from .request import REQUEST_PARAMS, REQUEST_TEMPLATE
from .wiki import Wiki, WikiPage

__all__ = ['Task', 'INFOBOX', 'PHOTO', 'TASKS']

# How a task checks a batch of articles: {title: Verdict}.  Each is loaded,
# exists and isn't a redirect; ignore are the request template's names.
Checker = Callable[[Wiki, list[WikiPage], list[str]], dict[str, Verdict]]


@dataclass(frozen=True)
class Task:
    name: str                       # the command's name, such as infoboxsweep
    root: str                       # the category whose tree the run goes through
    request_templates: tuple[str, ...]   # without Template:; their redirects too
    request_params: Collection[str]   # banners' parameters asking for it, as normalize_param
    keywords: tuple[str, ...]       # one is in the name of every category in the tree
    thing: str                      # what's asked for: "an infobox"
    request: str                    # "infobox request"
    doing: str                      # for the report page: "removing infobox requests ..."
    report: str                     # the report page, after User:<account>/
    brfa: str                       # linked from every edit summary
    check: Checker
    template_params: Collection[str] | None = None   # see request.remove_requests
    details: tuple[str, ...] = ()                    # see request.remove_requests

    def follows(self, category: str) -> bool:
        """Whether the walk goes into a subcategory: one with a keyword in
        its name."""
        name = category.lower()
        return any(word in name for word in self.keywords)

    def is_request_category(self, category: str) -> bool:
        """Whether a category, with Category:, is one for this task's
        requests, by its name: for checking a talk page leaves them when
        the bot hasn't walked the tree (with --page)."""
        name = category.lower()
        return self.follows(category) and any(w in name for w in ('request', 'need'))

    def request_names(self, wiki: Wiki) -> list[str]:
        """Every name the request templates go by: each, and each of the
        templates that redirect to it, read from the wiki."""
        names: list[str] = []
        for template in self.request_templates:
            for name in [template] + sorted(wiki.redirects_to(template)):
                if name not in names:
                    names.append(name)
        return names

    def keyword_text(self) -> str:
        return ' or '.join(f'"{word}"' for word in self.keywords)


def check_infoboxes(wiki: Wiki, articles: list[WikiPage],
                    ignore: list[str]) -> dict[str, Verdict]:
    """Which articles have an infobox: by what they transclude, in one
    request a batch."""
    titles = [article.title() for article in articles]
    transcluded = wiki.transcluding(titles, INFOBOX_PAGES) if titles else {}
    return {article.title(): verdict(article.text, transcluded.get(article.title(), set()),
                                     ignore=ignore)
            for article in articles}


def check_photos(wiki: Wiki, articles: list[WikiPage],
                 ignore: Iterable[str]) -> dict[str, Verdict]:
    """Which articles have a photograph of their subject: by their lead
    images and what those files are, in two requests a batch."""
    titles = [article.title() for article in articles]
    leads = wiki.lead_images(titles) if titles else {}
    files = wiki.file_info(sorted({lead.file for lead in leads.values()})) if leads else {}
    found = {}
    for title in titles:
        lead = leads.get(title)
        found[title] = photo_verdict(lead, files.get(lead.file) if lead else None)
    return found


INFOBOX = Task(
    name='infoboxsweep',
    root=ROOT_CATEGORY,
    request_templates=(REQUEST_TEMPLATE,),
    request_params=REQUEST_PARAMS,
    keywords=('infobox',),
    thing='an infobox',
    request='infobox request',
    doing='removing infobox requests from the talk pages of articles that already have an '
          'infobox',
    report='InfoboxReport',
    brfa=BRFA,
    check=check_infoboxes,
)

PHOTO = Task(
    name='imagesweep',
    root=PHOTO_CATEGORY,
    # {{Photo requested}} (with {{Reqphoto}}, {{Needs photo}} and its other
    # redirects) is the usual one; {{Image requested}} is a separate template.
    request_templates=('Photo requested', 'Image requested'),
    # WikiProject banners' names for "this article needs a photograph".
    request_params=frozenset({
        'needs-photo', 'needsphoto', 'need-photo', 'needs-photograph', 'needs-photos',
        'needs-image', 'needsimage', 'need-image', 'needs-picture', 'needs-pic',
        'image-needed', 'imageneeded', 'photo-needed', 'photoneeded', 'picture-needed',
        'image-requested', 'photo-requested', 'image-request', 'imagerequest',
        'photo-request', 'photorequest', 'reqphoto', 'req-photo', 'reqimage', 'photo',
    }),
    keywords=('photograph', 'photo', 'image', 'picture'),
    thing='a photograph',
    request='photograph request',
    doing='removing photograph requests from the talk pages of articles whose lead image is '
          'a free photograph',
    report='ImageReport',
    brfa=PHOTO_BRFA,
    check=check_photos,
    # The request template's named parameters that ask for nothing in
    # particular: where the subject is ({{Photo requested|in=Ohio}}, in1= ...
    # in21=), topic categories (1o=, 1r= ...), that the photo must be free
    # (a free lead photo is), and how the box is shown.  Others, such as
    # reason= and of=, say what's wanted.
    template_params=frozenset({f'in{n}' for n in ('', *map(str, range(1, 22)))}
                              | {f'{n}{kind}' for n in range(1, 4) for kind in 'or'}
                              | {'free', 'date', 'small', 'collapsed', 'nocat', 'category'}),
    details=('photo', 'image', 'picture'),
)

TASKS = {task.name: task for task in (INFOBOX, PHOTO)}
