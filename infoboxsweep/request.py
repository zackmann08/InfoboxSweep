"""Taking a request off a talk page: for an infobox, or for a photograph.

A talk page asks in one of three ways, and the bot takes out each it finds:

- **A WikiProject banner's parameter**, the usual way:
  ``{{WikiProject Film|class=Stub|needs-infobox=yes}}``, or
  ``|needs-photo=yes``.  Banners name it differently (``needs-infobox``,
  ``needs_infobox``, ``infobox``, ...: see the task's request_params), and
  any value Module:Yesno reads as yes asks for one.  The parameter is
  removed, with the rest of the banner left as it was.  A parameter that
  doesn't say yes asks for nothing, and is left alone.
- **The request template**, such as {{Infobox requested}} or {{Image
  requested}}, or one of its redirects, on its own.  The call is removed,
  and its line too if nothing else was on it.
- **The category itself**, added by hand: ``[[Category:Wikipedia articles
  with an infobox request]]``, or any category in its tree.

A request that asks for something in particular, such as ``{{Image
requested|reason=the current one is blurry}}``, or a banner with
``image-details=the interior`` next to its ``needs-image=yes``, isn't met by
just any infobox or photograph, so it's left alone, and noted in
Removal.specific: the bot then leaves the page for a human.

The request template's unnamed values are usually topics:
``{{Photo requested|musicians|people of Washington}}`` puts the page in
"Wikipedia requested images of musicians" and "... of people of
Washington".  So an unnamed value asks for nothing in particular if it's
one of the tree's topics (see topics_of): what comes after "of" or "in" in
the name of one of its categories.  One that isn't, such as ``{{Image
requested|the interior}}``, is taken as a description of what's wanted.

The bot then checks the result with MediaWiki (see Bot._still_requested): if
the page would still be in one of the tree's categories, it is left for a
human.
"""

import re
from collections.abc import Collection, Iterable
from contextlib import suppress
from dataclasses import dataclass, field

import mwparserfromhell
from mwparserfromhell.nodes import Node, Template, Wikilink
from mwparserfromhell.nodes.extras import Parameter
from mwparserfromhell.wikicode import Wikicode

from .wikitext import (
    is_blank,
    is_yes,
    normalize_param,
    normalize_template_name,
    normalize_title,
    strip_comments,
)

__all__ = ['REQUEST_TEMPLATE', 'REQUEST_PARAMS', 'Removal', 'remove_requests', 'topics_of']

REQUEST_TEMPLATE = 'Infobox requested'

# WikiProject banners' names for "this article needs an infobox", as
# normalize_param gives them (lower case, with hyphens).  The photograph
# task's are in infoboxsweep.tasks.
REQUEST_PARAMS = frozenset({
    'needs-infobox', 'needsinfobox', 'need-infobox', 'needinfobox',
    'infobox', 'infobox-needed', 'infoboxneeded', 'infobox-request', 'infoboxrequest',
    'infobox-requested', 'needs-ibox', 'ibox', 'ibox-needed',
})

# What a removed call becomes, until the lines are tidied.
# A private-use character, which no page has (mwparserfromhell drops NULs).
_GONE = '\ue000INFOBOXSWEEP-REMOVED\ue000'
_GONE_LINE_RE = re.compile(r'^[ \t]*' + re.escape(_GONE) + r'[ \t]*(?:\n|\Z)', re.MULTILINE)


@dataclass
class Removal:
    original: str
    text: str
    removed: list[str] = field(default_factory=list)    # what was taken out, described
    specific: list[str] = field(default_factory=list)   # requests for something particular

    @property
    def changed(self) -> bool:
        return self.text != self.original


def remove_requests(text: str, request_templates: Iterable[str],
                    categories: Iterable[str] = (), *,
                    params: Collection[str] = REQUEST_PARAMS,
                    template_params: Collection[str] | None = None,
                    topics: Collection[str] | None = None,
                    details: Iterable[str] = ()) -> Removal:
    """text without its requests.  request_templates are the names the
    request template goes by (it and its redirects), without the Template:
    prefix; categories are the tree's, with Category:; params are the
    banners' request parameters.

    template_params, if given, are the request template's named parameters
    that don't make it ask for anything in particular (such as where the
    subject is); a call with any other is left alone.  So is one with an
    unnamed value that isn't one of topics (see topics_of), lower case;
    with topics None, any unnamed value is taken as a topic.  details are words that, in
    the name of another parameter of a banner asking for one, with a value,
    make it ask for something in particular (image-details=the interior)."""
    names = {normalize_template_name(name) for name in request_templates}
    cats = {normalize_title(c.split(':', 1)[1]) for c in categories}
    code = mwparserfromhell.parse(text)
    removed: list[str] = []
    specific: list[str] = []
    for node in code.filter(recursive=True):
        if isinstance(node, Template):
            name = normalize_template_name(node.name)
            if name in names:
                extra = _particular(node, template_params, topics)
                if extra:
                    specific.append(f'{{{{{name}}}}} asks for something particular: {extra}')
                    continue
                _replace(code, node)
                removed.append(f'{{{{{name}}}}}')
            else:
                gone, particular = _remove_params(node, name, params, tuple(details))
                removed += gone
                specific += particular
        elif isinstance(node, Wikilink) and _category_of(node) in cats:
            _replace(code, node)
            removed.append(f'[[{normalize_title(node.title).lstrip(":")}]]')
    new = _GONE_LINE_RE.sub('', str(code)).replace(_GONE, '')
    return Removal(text, new if removed else text, removed, specific)


def topics_of(categories: Iterable[str]) -> set[str]:
    """The topics of request categories, lower case: what comes after the
    first " of ", or " in ", in their names.  "Category:Wikipedia requested
    images of people of Washington" gives "people of washington"."""
    found = set()
    for category in categories:
        name = ' '.join(category.split(':', 1)[-1].replace('_', ' ').split()).lower()
        for word in (' of ', ' in '):
            if word in name:
                found.add(name.split(word, 1)[1])
    return found


def _particular(template: Template, allowed: Collection[str] | None,
                topics: Collection[str] | None) -> str | None:
    """The first parameter, shown, of a request template's call that makes
    it ask for something in particular: a named one not in allowed, or an
    unnamed one not in topics, with a value."""
    if allowed is None:
        return None
    for param in template.params:
        if is_blank(param.value):
            continue
        if not param.showkey:
            value = ' '.join(strip_comments(param.value).split()).lower()
            if topics is None or value in topics:
                continue
        if not param.showkey or normalize_param(param.name) not in allowed:
            shown = str(param.value).strip() if not param.showkey else (
                f'{str(param.name).strip()}={str(param.value).strip()}')
            return shown
    return None


def _replace(code: Wikicode, node: Node) -> None:
    with suppress(ValueError):   # inside a node already replaced
        code.replace(node, _GONE)


def _remove_params(template: Template, name: str, params: Collection[str],
                   details: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Take a banner's request parameters out; return what was removed, and
    the requests left because the banner asks for something particular."""
    asking = [p for p in template.params if p.showkey
              and normalize_param(p.name) in params and is_yes(p.value)]
    if not asking:
        return [], []
    extra = [p for p in template.params if p.showkey and p not in asking
             and normalize_param(p.name) not in params and not is_blank(p.value)
             and any(word in normalize_param(p.name) for word in details)]
    if extra:
        shown = f'{str(extra[0].name).strip()}={str(extra[0].value).strip()}'
        return [], [f'{{{{{name}}}}} asks for something particular: {shown}']
    removed = []
    for param in asking:
        shown = f'{str(param.name).strip()}={str(param.value).strip()}'
        _tidy_before_removing(template, param)
        template.remove(param, keep_field=False)
        removed.append(f'{shown} from {{{{{name}}}}}')
    return removed, []


def _tidy_before_removing(template: Template, param: Parameter) -> None:
    """If param is the last one, and ends its line, while the one before it
    doesn't, move its line break onto the one before, so that the banner's
    closing }} stays on its own line."""
    params = template.params
    index = params.index(param)
    if index != len(params) - 1 or index == 0:
        return
    value = str(params[index].value)
    before = params[index - 1]
    if value.endswith('\n') and not str(before.value).endswith('\n'):
        before.value = str(before.value).rstrip(' \t') + '\n'


def _category_of(link: Wikilink) -> str | None:
    """The category a link puts the page in, without Category:, or None if
    it isn't a category link (a [[:Category:...]] link to one isn't)."""
    title = str(link.title).strip()
    prefix, _, rest = title.partition(':')
    if title.startswith(':') or prefix.strip().lower() != 'category' or not rest:
        return None
    return normalize_title(rest)
