"""Small helpers for reading wikitext the way MediaWiki does.

Functions that take wikitext accept a str or any mwparserfromhell node, since
both turn into the wikitext with str().
"""

import re

_COMMENT_RE = re.compile(r'<!--.*?(?:-->|\Z)', re.DOTALL)
_TEMPLATE_PREFIX_RE = re.compile(r'^:?\s*template\s*:\s*', re.IGNORECASE)

# The values Module:Yesno, which WikiProject banners use, reads as yes.
YES = frozenset({'yes', 'y', 'true', 't', 'on', '1'})


def strip_comments(text: object) -> str:
    return _COMMENT_RE.sub('', str(text))


def normalize_title(name: object) -> str:
    """A page title as MediaWiki sees it: comments and underscores gone,
    whitespace collapsed, first letter upper-cased."""
    title = ' '.join(strip_comments(name).replace('_', ' ').split())
    return title[:1].upper() + title[1:]


def normalize_template_name(name: object) -> str:
    """The name part of a {{template call}} as a title without the Template:
    prefix, e.g. ``infobox_requested`` -> ``Infobox requested``."""
    title = ' '.join(strip_comments(name).replace('_', ' ').split())
    return normalize_title(_TEMPLATE_PREFIX_RE.sub('', title))


def normalize_param(name: object) -> str:
    """A parameter name for comparing: comments gone, lower case, and
    spaces and underscores read as hyphens, so ``Needs_infobox`` and
    ``needs-infobox`` are the same."""
    return re.sub(r'[\s_]+', '-', strip_comments(name).strip().lower())


def is_yes(value: object) -> bool:
    """True if a parameter value reads as yes, as Module:Yesno would."""
    return strip_comments(value).strip().lower() in YES


def is_blank(value: object) -> bool:
    """True if a parameter value is nothing but whitespace and comments."""
    return not strip_comments(value).strip()
