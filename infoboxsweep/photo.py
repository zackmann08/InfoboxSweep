"""Does an article have a photograph of its subject?

Not every image will do: an icon such as {{Commons category}}'s, a map, a
flag or a logo isn't a photograph of the subject.  The bot decides from the
article's **lead image**, and only from that:

1. **Which image.**  MediaWiki's PageImages extension picks each article's
   lead image: on the English Wikipedia, only from the images in the lead
   section (above the first heading, which is where infoboxes are), never
   from those marked ``notpageimage`` (as icons in navboxes and maintenance
   templates are), scoring them by size and position.  It is the image
   that represents the article in search results, link previews and the
   apps.  The bot reads it from the page's properties: ``page_image_free``
   for a free image, ``page_image`` for a non-free one.  An image further
   down the article never counts.  No lead image: no photograph.
2. **Is it a photograph?**  Then it reads the file's type and size:

   - its name says it isn't one: ``map``, ``locator``, ``flag``, ``logo``,
     ``icon``, ``coat of arms``, ``seal``, ``signature``, ``diagram``,
     ``placeholder``, ``replace this image`` and the like (NOT_PHOTO_WORDS):
     no photograph;
   - SVG, or not an image at all (a video, a PDF, a sound file): no
     photograph, as photographs aren't SVGs;
   - under 200 pixels on its longer side: an icon, so no photograph;
   - PNG or GIF, which are mostly screenshots, scans and drawings but are
     sometimes photographs: left for a human;
   - JPEG (or TIFF, WebP, HEIF): a photograph.
3. **Free or not.**  A photograph request almost always wants a free photo.
   A photograph that's non-free (fair use) is left for a human, who can
   tell whether the request still stands.

So the bot takes a request off only for a free, full-size JPEG-type image,
picked by MediaWiki as the article's lead image, whose name doesn't say it's
a map, flag, logo or the like.  Whether it shows the subject itself is
taken on trust from it being the lead image: what an editor put at the top
of the article, or in its infobox, to show what the article is about.
"""

import re
from dataclasses import dataclass

from .infobox import Verdict

__all__ = ['LeadImage', 'FileInfo', 'NOT_PHOTO_WORDS', 'NOT_PHOTO_PHRASES', 'MIN_SIZE',
           'photo_verdict', 'not_a_photo']

# Words in a file's name that say it isn't a photograph of the subject.
NOT_PHOTO_WORDS = frozenset({
    'map', 'maps', 'locator', 'location', 'locmap', 'flag', 'flags', 'logo', 'logos', 'logotype',
    'wordmark', 'icon', 'icons', 'seal', 'emblem', 'insignia', 'crest', 'coa', 'blason',
    'signature', 'autograph', 'symbol', 'pictogram', 'diagram', 'chart', 'graph', 'plan',
    'schematic', 'blank', 'placeholder', 'silhouette', 'banner', 'screenshot', 'cover',
    'poster', 'stub', 'nopic', 'noimage',
})
NOT_PHOTO_PHRASES = ('coat of arms', 'arms of', 'no image', 'replace this image',
                     'image needed', 'question mark', 'commons logo')

PHOTO_MIMES = frozenset({'image/jpeg', 'image/tiff', 'image/webp', 'image/heic', 'image/heif'})
MAYBE_PHOTO_MIMES = frozenset({'image/png', 'image/gif'})
MIN_SIZE = 200   # pixels, on the longer side


@dataclass(frozen=True)
class LeadImage:
    file: str     # with File:
    free: bool


@dataclass(frozen=True)
class FileInfo:
    mime: str
    width: int
    height: int


def _words(file: str) -> tuple[set[str], str]:
    """The words of a file's name, without File: and its extension, and the
    name as words joined by spaces."""
    name = file.split(':', 1)[-1].rsplit('.', 1)[0].lower()
    words = [w for w in re.split(r'[^a-z0-9]+', name) if w]
    return set(words), ' '.join(words)


def not_a_photo(file: str) -> str | None:
    """Why a file's name says it isn't a photograph, or None."""
    words, joined = _words(file)
    hit = sorted(words & NOT_PHOTO_WORDS)
    if hit:
        return f'its name has "{hit[0]}"'
    for phrase in NOT_PHOTO_PHRASES:
        if f' {phrase} ' in f' {joined} ':
            return f'its name has "{phrase}"'
    return None


def photo_verdict(lead: LeadImage | None, info: FileInfo | None) -> Verdict:
    """Whether an article whose lead image is lead, a file like info, has a
    photograph of its subject."""
    if lead is None:
        return Verdict(False, 'no lead image')
    link = f'[[:{lead.file}]]'
    if info is None:
        return Verdict(False, review=f'the lead image, {link}, could not be found: is it '
                                     'still there?')
    why = not_a_photo(lead.file)
    if why:
        return Verdict(False, f'the lead image, {link}, is not a photograph: {why}')
    kind = info.mime.split('/', 1)[-1].upper()
    if info.mime not in PHOTO_MIMES | MAYBE_PHOTO_MIMES:
        return Verdict(False, f'the lead image, {link}, is {kind}, not a photograph')
    if max(info.width, info.height) < MIN_SIZE:
        return Verdict(False, f'the lead image, {link}, is {info.width}×{info.height}: an '
                              'icon, not a photograph')
    if info.mime in MAYBE_PHOTO_MIMES:
        return Verdict(False, review=f'the lead image, {link}, is a {kind}: is it a photograph '
                                     'of the subject?')
    if not lead.free:
        return Verdict(False, review=f'the lead image, {link}, is non-free: does the request, '
                                     'for a free photograph, still stand?')
    return Verdict(True, f'lead image {link} ({kind}, {info.width}×{info.height})', shown=link)
