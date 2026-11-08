"""Does an article have an infobox?

Two kinds of evidence:

- **What the article transcludes.**  Nearly every infobox on the English
  Wikipedia is built on Template:Infobox, or on Module:Infobox, which it
  invokes; the taxobox and chembox families are built their own way, so
  they are named too.  If the article transcludes any of INFOBOX_PAGES, by
  any route (an {{Infobox settlement}}, or a template that wraps one), it
  shows an infobox.  This is the evidence the bot acts on: it's what
  MediaWiki rendered, not a guess from the wikitext.
- **What the wikitext calls.**  A call of a template whose name starts with
  "Infobox", without the transclusion, is odd: the template may not exist,
  or may be broken.  The page goes to a human instead.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

import mwparserfromhell

from .wikitext import normalize_template_name

__all__ = ['INFOBOX_PAGES', 'Verdict', 'verdict', 'infobox_calls']

INFOBOX_PAGES = (
    'Template:Infobox',
    'Module:Infobox',
    'Template:Taxobox',
    'Template:Automatic taxobox',
    'Template:Speciesbox',
    'Template:Subspeciesbox',
    'Template:Infraspeciesbox',
    'Template:Hybridbox',
    'Template:Virusbox',
    'Template:Chembox',
)


@dataclass(frozen=True)
class Verdict:
    """Whether an article has what its talk page asked for."""

    found: bool
    evidence: str = ''          # why the bot thinks it has it, or hasn't
    review: str | None = None   # why a human should look, instead
    shown: str = ''             # what it found, for the edit summary


def infobox_calls(text: str, ignore: Iterable[str] = ()) -> list[str]:
    """The names of the templates called in text whose names start with
    "Infobox", other than those in ignore (such as {{Infobox requested}}),
    in the order they come.  Calls in comments and <nowiki> are not
    calls."""
    skip = {normalize_template_name(name) for name in ignore}
    names = []
    for template in mwparserfromhell.parse(text).filter_templates(recursive=True):
        name = normalize_template_name(template.name)
        if name.lower().startswith('infobox') and name not in skip and name not in names:
            names.append(name)
    return names


def verdict(text: str, transcluded: Collection[str], ignore: Iterable[str] = ()) -> Verdict:
    """Whether an article with this wikitext, which transcludes these of
    INFOBOX_PAGES, has an infobox."""
    if transcluded:
        return Verdict(True, 'transcludes ' + ', '.join(sorted(transcluded)))
    calls = infobox_calls(text, ignore)
    if calls:
        return Verdict(False, review=(
            f'the article calls {{{{{calls[0]}}}}} but does not transclude Template:Infobox '
            'or Module:Infobox: check whether it shows an infobox'))
    return Verdict(False)
