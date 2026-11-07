"""The bot's report page on the wiki, User:ZackBot/InfoboxReport.

It has two sections.  "Runs" has a table with a row for each live run,
newest first.  The bot adds the row as soon as the run starts, updates it
as the run goes, and gives its final numbers when the run ends:

    == Runs ==
    {| class="wikitable"
    ! Started (UTC) !! Finished (UTC) !! Duration !! Categories !! Talk pages found
      !! Checked !! Changed !! Manual review !! Result
    <!-- InfoboxSweep: new runs go below this line -->
    |- data-run="20261107T042305.123456"
    | 2026-11-07 04:23 || 2026-11-07 06:01 || 1 h 38 min || 412 || 38,120 || 38,120
      || 2,904 || [[#Needs manual review|17]] || finished
    |}

(the row is one line on the page).  data-run says which run a row is, so a
run updates its own.  The oldest rows go once there are MAX_ROWS.

"Needs manual review" lists the pages the bot left for a human, and why,
with any errors:

    == Needs manual review ==
    <!-- InfoboxSweep review start -->
    Updated 2026-11-07 06:01 (UTC), by the run that started 2026-11-07 04:23. 17 pages.
    {| class="wikitable sortable"
    ! Page !! Article !! Why
    |-
    | [[Talk:Joe Bloggs]] || [[Joe Bloggs]] || <nowiki>the article does not exist</nowiki>
    ...
    |}
    <!-- InfoboxSweep review end -->

A run that went through every page replaces the list.  Any other (one with
--limit, say, or stopped part way), and every progress report, changes only
the pages it looked at, so the rest stay listed.

Everything above the Runs table's marker, and everything outside the review
markers, is kept as it is, so the introduction can be edited by hand.
"""

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta

from .report import Report

__all__ = ['MARKER', 'MAX_ROWS', 'MAX_REVIEWS', 'REVIEW_START', 'REVIEW_END', 'updated_page',
           'run_row', 'run_id', 'duration', 'mark_interrupted', 'review_section',
           'review_lines']

MARKER = '<!-- InfoboxSweep: new runs go below this line -->'
REVIEW_START = '<!-- InfoboxSweep review start -->'
REVIEW_END = '<!-- InfoboxSweep review end -->'
REVIEW_HEADING = '== Needs manual review =='
MAX_ROWS = 100
MAX_REVIEWS = 2000   # rows in the review table; the local report has every one
_TABLE_END = '|}'
HEADINGS = ('! Started (UTC) !! Finished (UTC) !! Duration !! Categories !! Talk pages found '
            '!! Checked !! Changed !! Manual review !! Result')


# -- the page ----------------------------------------------------------------

def updated_page(old: str | None, row: str, *, review: str | None, header: str,
                 intro: str) -> str:
    """The report page's text with row in the Runs table (in place of the
    same run's row, if there is one, or else at the top), and review, if
    given, as the review section's contents.  A page without the table (new,
    or edited by hand) is started afresh."""
    if old is None or not _has_table(old):
        old = _fresh(header, intro)
    head, rest = old.split(MARKER, 1)
    body, _, tail = rest.partition('\n' + _TABLE_END)
    rows = _rows(body)
    run = _run_of(row)
    if run is not None and any(_run_of(r) == run for r in rows):
        rows = [row if _run_of(r) == run else r for r in rows]
    else:
        rows = [row] + rows[:MAX_ROWS - 1]
    text = head + MARKER + '\n' + ''.join(r.rstrip('\n') + '\n' for r in rows) + _TABLE_END + tail
    if review is None:
        return text
    if REVIEW_START in text and REVIEW_END in text.split(REVIEW_START, 1)[1]:
        before, rest = text.split(REVIEW_START, 1)
        after = rest.split(REVIEW_END, 1)[1]
        return before + REVIEW_START + '\n' + review.strip('\n') + '\n' + REVIEW_END + after
    return (text.rstrip('\n') + f'\n\n{REVIEW_HEADING}\n{REVIEW_START}\n'
            + review.strip('\n') + f'\n{REVIEW_END}\n')


def _has_table(text: str) -> bool:
    return MARKER in text and _TABLE_END in text.split(MARKER, 1)[1]


def _fresh(header: str, intro: str) -> str:
    return (f'{header}\n{intro}\n\n== Runs ==\n{{| class="wikitable"\n{HEADINGS}\n'
            f'{MARKER}\n{_TABLE_END}\n\n{REVIEW_HEADING}\n{REVIEW_START}\n'
            f'No pages yet.\n{REVIEW_END}\n')


def _rows(body: str) -> list[str]:
    """The table's rows, each starting with its |- line."""
    rows: list[str] = []
    for line in body.strip('\n').split('\n'):
        if line.startswith('|-') or not rows:
            rows.append('')
        rows[-1] += line + '\n'
    return [row for row in rows if row.strip()]


def _run_of(row: str) -> str | None:
    m = re.match(r'\|-[^\n]*\bdata-run="([^"]*)"', row)
    return m.group(1) if m else None


# -- a run's row -------------------------------------------------------------

def run_id(report: Report) -> str:
    """What data-run says for a run: when it started."""
    return f'{report.started:%Y%m%dT%H%M%S.%f}'


def run_row(report: Report, *, now: datetime | None = None, result: str | None = None,
            starting: bool = False) -> str:
    """A run's row in the table.  A run that hasn't finished yet is shown as
    running, as of now, or as just started, if starting.  result, if given,
    says how the run ended."""
    def count(n: int | None) -> str:
        return '—' if n is None else f'{n:,}'

    if starting:
        cells = [_when(report.started), '—', '—', '—', '—', '0', '0', '0', 'started']
        return f'|- data-run="{run_id(report)}"\n| ' + ' || '.join(cells) + '\n'
    if report.finished is None:
        assert now is not None
        ended, elapsed = '—', now - report.started
        result = f'running (last updated {_when(now)})'
    else:
        ended, elapsed = _when(report.finished), report.finished - report.started
        result = result or _result(report)
    if report.errors:
        result += f' ({len(report.errors)} error' + ('s' if len(report.errors) > 1 else '') + ')'
    reviews = len(report.reviews) + len(report.errors)
    cells = [_when(report.started), ended, duration(elapsed), count(report.categories),
             count(report.found), count(report.checked), count(len(report.edits)),
             f'[[#Needs manual review|{reviews:,}]]' if reviews else '0', result]
    return f'|- data-run="{run_id(report)}"\n| ' + ' || '.join(cells) + '\n'


def _result(report: Report) -> str:
    if report.stopped:
        return f'stopped: <nowiki>{report.stopped}</nowiki>'
    if report.ended_early:
        return f'finished early: <nowiki>{report.ended_early}</nowiki>'
    return 'finished'


def _when(moment: datetime) -> str:
    return f'{moment:%Y-%m-%d %H:%M}'


def duration(elapsed: timedelta) -> str:
    """elapsed as "45 s", "12 min", "1 h 38 min" or "2 d 3 h"."""
    seconds = int(elapsed.total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f'{days} d {hours} h'
    if hours:
        return f'{hours} h {minutes} min'
    if minutes:
        return f'{minutes} min'
    return f'{seconds} s'


# -- runs that died ------------------------------------------------------------

_RUNNING_RE = re.compile(r'\|\| running \(last updated (\d{4}-\d\d-\d\d \d\d:\d\d)\)')
_STARTED_RE = re.compile(r'\|\| started\n?$')
_STARTED_AT_RE = re.compile(r'\n\| (\d{4}-\d\d-\d\d \d\d:\d\d) \|\|')


def mark_interrupted(old: str | None, *, run: str,
                     stale_before: datetime) -> tuple[str | None, int]:
    """old, with the rows of other runs that still say running, or started,
    but haven't been updated since stale_before, marked as interrupted:
    their job died without saying so.  Returns the text, and how many rows
    were marked."""
    if old is None or not _has_table(old):
        return old, 0
    head, rest = old.split(MARKER, 1)
    body, _, tail = rest.partition('\n' + _TABLE_END)
    rows, marked = [], 0
    for row in _rows(body):
        if _run_of(row) not in (None, run):
            new = _interrupted(row, stale_before)
            marked += new != row
            row = new
        rows.append(row)
    text = head + MARKER + '\n' + ''.join(r.rstrip('\n') + '\n' for r in rows) + _TABLE_END + tail
    return text, marked


def _interrupted(row: str, stale_before: datetime) -> str:
    running = _RUNNING_RE.search(row)
    if running:
        if _parse_when(running.group(1)) < stale_before:
            return _RUNNING_RE.sub(r'|| interrupted (last updated \1)', row, count=1)
        return row
    started = _STARTED_AT_RE.search(row)
    if _STARTED_RE.search(row) and started and _parse_when(started.group(1)) < stale_before:
        return _STARTED_RE.sub('|| interrupted (before its first progress report)\n', row)
    return row


def _parse_when(text: str) -> datetime:
    return datetime.strptime(text, '%Y-%m-%d %H:%M').replace(tzinfo=UTC)


# -- the review section -------------------------------------------------------

_REVIEW_ROW_RE = re.compile(r'^\| \[\[:?([^\]|]+)\]\] \|\| ', re.MULTILINE)


def review_lines(text: str | None) -> dict[str, str]:
    """{page: its row's cell line} for the pages listed in the review
    section of the report page's text."""
    if not text or REVIEW_START not in text or REVIEW_END not in text.split(REVIEW_START, 1)[1]:
        return {}
    section = text.split(REVIEW_START, 1)[1].split(REVIEW_END, 1)[0]
    return {m.group(1): line for line in section.split('\n')
            if (m := _REVIEW_ROW_RE.match(line))}


def _review_line(title: str, article: str, why: str) -> str:
    link = f'[[{article}]]' if article else '—'
    return f'| [[:{title}]] || {link} || <nowiki>{why.replace("<", "&lt;")}</nowiki>'


def review_section(old: str | None, *, found: Mapping[str, tuple[str, str]],
                   looked_at: Iterable[str], complete: bool, when: datetime,
                   started: datetime) -> str:
    """The review section's contents.  found is {page: (article, why)}, for
    the pages the run left for a human.  If complete, it is the whole list;
    otherwise it replaces only the pages in looked_at, and the old text's
    others stay listed."""
    lines = {} if complete else review_lines(old)
    for title in looked_at:
        lines.pop(title, None)
    for title, (article, why) in found.items():
        lines[title] = _review_line(title, article, why)
    count = len(lines)
    text = (f'Updated {_when(when)} (UTC), by the run that started {_when(started)}. '
            + ('No pages need manual review.' if not count else
               '1 page needs manual review.' if count == 1 else
               f'{count:,} pages need manual review.'))
    if not lines:
        return text
    shown = sorted(lines)[:MAX_REVIEWS]
    table = ('{| class="wikitable sortable"\n! Page !! Article !! Why\n'
             + ''.join(f'|-\n{lines[title]}\n' for title in shown) + '|}')
    more = (f"\nThe first {MAX_REVIEWS:,} are listed; the bot's local report has the rest."
            if count > MAX_REVIEWS else '')
    return f'{text}\n{table}{more}'
