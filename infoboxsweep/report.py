"""The report of a run, written to a plain text file.

In a dry run it is the whole point: every edit the bot would have made, as
a unified diff, so they can be checked before the bot is let loose on the
wiki.  A live run writes the same report, of the edits it made.
"""

import difflib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

__all__ = ['Edit', 'Report', 'unified_diff']

RULE = '=' * 78


@dataclass
class Edit:
    talk: str
    article: str
    removed: list[str]      # what was taken off the talk page, described
    summary: str
    diff: str
    evidence: str           # why the bot thinks the article has an infobox
    saved: bool = False     # False in a dry run


@dataclass
class Report:
    live: bool
    started: datetime
    root: str = ''
    thing: str = 'an infobox'      # what was asked for
    finished: datetime | None = None
    account: str | None = None
    source: str = ''               # which pages the run went through
    categories: int | None = None  # in the tree, once walked
    found: int | None = None       # distinct pages in the tree, once walked
    duplicates: int = 0            # pages listed in more than one of its categories
    depth: int = 0
    not_followed: list[tuple[str, str]] = field(default_factory=list)   # (category, parent)
    excluded: list[tuple[str, str]] = field(default_factory=list)       # left out, as asked
    excluded_pages: int = 0        # pages left out with them
    checked: int = 0               # talk pages whose article was checked
    fulfilled: int = 0             # articles that have what was asked for
    unfulfilled: int = 0           # and those that haven't
    redirects: int = 0             # articles that are redirects: the request comes off
    edits: list[Edit] = field(default_factory=list)
    reviews: list[tuple[str, str, str]] = field(default_factory=list)   # (page, article, why)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    stopped: str | None = None       # why the run stopped, if something stopped it
    ended_early: str | None = None   # why it finished before the last page, as asked
    wiki_report: str | None = None   # whether the report page on the wiki was saved
    stopped_by_operator: bool = False

    def skip(self, title: str, reason: str) -> None:
        self.skipped.append((title, reason))

    def review(self, title: str, article: str, why: str) -> None:
        self.reviews.append((title, article, why))

    def text(self) -> str:
        mode = 'LIVE RUN: these edits were saved' if self.live else (
            'DRY RUN: nothing was saved; these are the edits the bot would have made')
        lines = [f'InfoboxSweep report: requests for {self.thing} on articles that have one',
                 mode, '']
        lines += [f'Started:  {self.started:%Y-%m-%d %H:%M:%S %Z}'.rstrip()]
        if self.finished:
            lines += [f'Finished: {self.finished:%Y-%m-%d %H:%M:%S %Z}'.rstrip()]
        if self.account:
            lines += [f'Account:  {self.account}']
        lines += [f'Pages: {self.source}']
        if self.categories is not None:
            lines += [f'Category tree: {self.categories} categories, {self.depth} levels below '
                      f'{self.root}; {self.found} distinct pages ({self.duplicates} more '
                      'listings of pages in more than one category)']
        verb = 'Changed:' if self.live else 'Would change:'
        lines += ['', f'Talk pages checked:   {self.checked}',
                  f'  article has {self.thing}: {self.fulfilled}',
                  f'  article has none: {self.unfulfilled}',
                  f'  article is a redirect: {self.redirects}',
                  f'{verb:<22}{len(self.edits)}',
                  f'Need manual review:   {len(self.reviews)}',
                  f'Skipped:              {len(self.skipped)}',
                  f'Errors:               {len(self.errors)}']
        lines += self._outcome()
        if self.excluded:
            lines += _section(f'Categories left out, as asked ({self.excluded_pages} pages in them '
                              'not checked)',
                              [f'{cat} (in {parent})' for cat, parent in self.excluded])
        if self.not_followed:
            lines += _section('Subcategories not followed (not named for these requests)',
                              [f'{cat} (in {parent})' for cat, parent in self.not_followed])
        if self.reviews:
            lines += _section('Need manual review (left as they are)',
                              [f'{title} ({article}): {why}'
                               for title, article, why in self.reviews])
        if self.errors:
            lines += _section('Errors', [f'{title}: {error}' for title, error in self.errors])
        if self.skipped:
            lines += _section('Skipped', [f'{title}: {reason}' for title, reason in self.skipped])
        lines += ['', RULE, f'{verb} {len(self.edits)} page(s)', RULE]
        for edit in self.edits:
            lines += ['', f'### {edit.talk}', f'Article: {edit.article} ({edit.evidence})',
                      f'Summary: {edit.summary}', 'Removed:']
            lines += [f'  - {item}' for item in edit.removed]
            lines += ['', edit.diff.rstrip('\n')]
        return '\n'.join(lines) + '\n'

    def _outcome(self) -> list[str]:
        lines = []
        if self.wiki_report:
            lines += [f'Report on the wiki: {self.wiki_report}']
        if self.ended_early:
            lines += ['', f'Finished early, as asked: {self.ended_early}']
        if self.stopped:
            lines += ['', f'STOPPED: {self.stopped}']
        return lines

    def write(self, out_dir: Path) -> Path:
        """Write the report to a new file in out_dir; return its path."""
        out_dir.mkdir(parents=True, exist_ok=True)
        kind = 'live' if self.live else 'dry-run'
        what = self.thing.split()[-1]
        path = out_dir / f'{kind}-{what}-{self.started:%Y%m%d-%H%M%S}.txt'
        path.write_text(self.text(), encoding='utf-8')
        return path


def _section(title: str, items: list[str]) -> list[str]:
    return ['', title, '-' * len(title)] + [f'* {item}' for item in items]


def unified_diff(title: str, old: str, new: str) -> str:
    """The change from old to new, as a unified diff."""
    return ''.join(difflib.unified_diff(
        (old + '\n').splitlines(keepends=True), (new + '\n').splitlines(keepends=True),
        fromfile=f'{title} (current)', tofile=f'{title} (after the bot)', n=2))
