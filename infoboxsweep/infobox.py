"""Does an article have an infobox?

Transcluding Template:Infobox isn't enough: other templates are built on it
too, such as {{External media}}, some sidebars and side boxes, so an article
with one of those and no infobox at all transcludes it.  So the bot asks for
two things:

1. **An infobox call in the lead section**, the wikitext above the first
   heading, where an article's infobox goes: a call of a template whose name
   starts with "Infobox" ({{Infobox person}}, {{Infobox settlement}} ...),
   or that redirects to one ({{Film infobox}} -> {{Infobox film}}), or of
   one of the infobox families named otherwise (INFOBOX_FAMILIES: the
   taxoboxes, {{Chembox}} ...).  Calls in comments and <nowiki> don't count,
   nor does {{Infobox requested}}.
2. **That it renders**: the article transcludes Template:Infobox or
   Module:Infobox, which nearly every infobox is built on, or one of the
   families (INFOBOX_PAGES), as MediaWiki reports.

Some templates named "Infobox ..." aren't an article's infobox: {{Infobox
designation list}} (or {{Designation list}}) is a box listing a place's
heritage designations, as on Gosford House, which has no infobox.  Those in
NOT_INFOBOXES never count, wherever they are, called by any name: an
article whose only "infobox" is one of them has no infobox.

Both: an infobox.  Neither: no infobox, and the request stands, even if the
article transcludes Template:Infobox through something else.  Only one goes
to a human: an infobox call that doesn't render (the template may be broken
or missing), or one only further down the article (is it the article's
infobox, or one for a section?).
"""

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

import mwparserfromhell

from .wikitext import normalize_template_name

__all__ = ['INFOBOX_PAGES', 'INFOBOX_FAMILIES', 'NOT_INFOBOXES', 'Verdict', 'verdict',
           'infobox_calls', 'lead_section', 'template_calls', 'is_infobox_name']

# Infoboxes not named "Infobox ...", without Template:.
INFOBOX_FAMILIES = frozenset({
    'Taxobox', 'Automatic taxobox', 'Speciesbox', 'Subspeciesbox', 'Infraspeciesbox',
    'Hybridbox', 'Virusbox', 'Ichnobox', 'Oobox', 'Chembox', 'Drugbox',
})

# Templates named like infoboxes, or redirecting to one, that aren't an
# article's infobox, without Template:.
NOT_INFOBOXES = frozenset({'Infobox designation list', 'Designation list'})

INFOBOX_PAGES = ('Template:Infobox', 'Module:Infobox',
                 *sorted(f'Template:{name}' for name in INFOBOX_FAMILIES))

_HEADING_RE = re.compile(r'^=+[^=\n].*?=+[ \t]*(?:<!--.*?-->[ \t]*)*$', re.MULTILINE)


@dataclass(frozen=True)
class Verdict:
    """Whether an article has what its talk page asked for."""

    found: bool
    evidence: str = ''          # why the bot thinks it has it, or hasn't
    review: str | None = None   # why a human should look, instead
    shown: str = ''             # what it found, for the edit summary


def lead_section(text: str) -> str:
    """The wikitext above the first heading."""
    heading = _HEADING_RE.search(text)
    return text[:heading.start()] if heading else text


def template_calls(text: str, ignore: Iterable[str] = ()) -> list[str]:
    """The names of the templates called in text, without Template:, other
    than those in ignore, each once, in the order they come.  Calls in
    comments and <nowiki> are not calls."""
    skip = {normalize_template_name(name) for name in ignore}
    names: list[str] = []
    for template in mwparserfromhell.parse(text).filter_templates(recursive=True):
        name = normalize_template_name(template.name)
        if name and not name.startswith('#') and ':' not in name and name not in skip \
                and name not in names:
            names.append(name)
    return names


def is_infobox_name(name: str) -> bool:
    """Whether a template, by its name, is an infobox: not one of
    NOT_INFOBOXES."""
    if name in NOT_INFOBOXES:
        return False
    return name.lower().startswith('infobox') or name in INFOBOX_FAMILIES


def infobox_calls(text: str, ignore: Iterable[str] = (),
                  resolved: Mapping[str, str] | None = None) -> list[str]:
    """The names of the infobox templates called in text (see
    is_infobox_name), other than those in ignore, such as {{Infobox
    requested}}.  resolved maps a template to the one it redirects to."""
    resolved = resolved or {}
    skip = {normalize_template_name(name) for name in ignore}
    found = []
    for name in template_calls(text, ignore):
        target = resolved.get(name)
        if target is not None:   # a redirect: what it is depends on its target
            if is_infobox_name(target) and target not in skip:
                found.append(name)
        elif is_infobox_name(name):
            found.append(name)
    return found


def verdict(text: str, transcluded: Collection[str], ignore: Iterable[str] = (),
            resolved: Mapping[str, str] | None = None) -> Verdict:
    """Whether an article with this wikitext, which transcludes these of
    INFOBOX_PAGES, has an infobox.  resolved maps the templates the lead
    section calls to those they redirect to."""
    ignore = list(ignore)
    lead = infobox_calls(lead_section(text), ignore, resolved)
    if lead and transcluded:
        return Verdict(True, f'{{{{{lead[0]}}}}} in the lead section, which transcludes '
                             + ', '.join(sorted(transcluded)))
    if lead:
        return Verdict(False, review=(
            f'the article calls {{{{{lead[0]}}}}} but does not transclude Template:Infobox '
            'or Module:Infobox: check whether it shows an infobox'))
    further = infobox_calls(text, ignore, resolved)
    if further:
        return Verdict(False, review=(
            f'the article calls {{{{{further[0]}}}}}, but only below its lead section: is it '
            "the article's infobox, or one for a section?"))
    if transcluded:
        return Verdict(False, 'no infobox in the lead section (it transcludes '
                              + ', '.join(sorted(transcluded))
                              + ' through something else, such as {{External media}} or a '
                              'sidebar)')
    return Verdict(False)
