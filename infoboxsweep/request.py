"""Taking an infobox request off a talk page.

A talk page asks for an infobox in one of three ways, and the bot takes out
each it finds:

- **A WikiProject banner's parameter**, the usual way:
  ``{{WikiProject Film|class=Stub|needs-infobox=yes}}``.  Banners name it
  differently (``needs-infobox``, ``needs_infobox``, ``infobox``, ...: see
  REQUEST_PARAMS), and any value Module:Yesno reads as yes asks for one.
  The parameter is removed, with the rest of the banner left as it was.
  A parameter that doesn't say yes asks for nothing, and is left alone.
- **{{Infobox requested}}**, or one of its redirects, on its own.  The
  call is removed, and its line too if nothing else was on it.
- **The category itself**, added by hand: ``[[Category:Wikipedia articles
  with an infobox request]]``, or any category in its tree.

The bot then checks the result with MediaWiki (see Bot._verify): if the page
would still be in one of the tree's categories, it is left for a human.
"""

import re
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field

import mwparserfromhell
from mwparserfromhell.nodes import Node, Template, Wikilink
from mwparserfromhell.nodes.extras import Parameter
from mwparserfromhell.wikicode import Wikicode

from .wikitext import is_yes, normalize_param, normalize_template_name, normalize_title

__all__ = ['REQUEST_TEMPLATE', 'REQUEST_PARAMS', 'Removal', 'remove_requests']

REQUEST_TEMPLATE = 'Infobox requested'

# WikiProject banners' names for "this article needs an infobox", as
# normalize_param gives them (lower case, with hyphens).
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
    removed: list[str] = field(default_factory=list)   # what was taken out, described

    @property
    def changed(self) -> bool:
        return self.text != self.original


def remove_requests(text: str, request_templates: Iterable[str],
                    categories: Iterable[str] = ()) -> Removal:
    """text without its infobox requests.  request_templates are the names
    {{Infobox requested}} goes by (it and its redirects), without the
    Template: prefix; categories are the tree's, with Category:."""
    names = {normalize_template_name(name) for name in request_templates}
    cats = {normalize_title(c.split(':', 1)[1]) for c in categories}
    code = mwparserfromhell.parse(text)
    removed: list[str] = []
    for node in code.filter(recursive=True):
        if isinstance(node, Template):
            name = normalize_template_name(node.name)
            if name in names:
                _replace(code, node)
                removed.append(f'{{{{{name}}}}}')
            else:
                removed += _remove_params(node, name)
        elif isinstance(node, Wikilink) and _category_of(node) in cats:
            _replace(code, node)
            removed.append(f'[[{normalize_title(node.title).lstrip(":")}]]')
    new = _GONE_LINE_RE.sub('', str(code)).replace(_GONE, '')
    return Removal(text, new if removed else text, removed)


def _replace(code: Wikicode, node: Node) -> None:
    with suppress(ValueError):   # inside a node already replaced
        code.replace(node, _GONE)


def _remove_params(template: Template, name: str) -> list[str]:
    removed = []
    for param in list(template.params):
        if not param.showkey:
            continue
        key = normalize_param(param.name)
        if key in REQUEST_PARAMS and is_yes(param.value):
            shown = f'{str(param.name).strip()}={str(param.value).strip()}'
            _tidy_before_removing(template, param)
            template.remove(param, keep_field=False)
            removed.append(f'{shown} from {{{{{name}}}}}')
    return removed


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
