"""A run of one of the bot's tasks (see infoboxsweep.tasks).

1. In a live run: log in, check the account has the bot flag (unless it's a
   trial), check the Run page says yes, and add the run's row to the task's
   report page on the wiki (User:<account>/InfoboxReport, or ImageReport).
2. Walk the whole tree under the task's category, such as
   Category:Wikipedia articles with an infobox request, every subcategory
   however deep, and list every page in it once (see infoboxsweep.tree).
   Or, with --page, take only the pages given.
3. For each talk page, BATCH at a time, check the article it belongs to.
   If the article has what was asked for (an infobox, see
   infoboxsweep.infobox, or a photograph, see infoboxsweep.photo), take the
   request off the talk page (see infoboxsweep.request), check with
   MediaWiki that the talk page leaves the tree's categories, and save it,
   or in a dry run, record the edit it would have made.  Anything odd is
   left for a human.
4. Write the report to a text file.  In a live run, the bot also brings its
   row on the report page up to date as it goes, on the hour and the half
   hour, and at the end, with the pages left for manual review.
"""

import logging
import signal
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .infobox import Verdict
from .report import Edit, Report, unified_diff
from .request import Removal, remove_requests, topics_of
from .tasks import INFOBOX, Task
from .tree import Tree, walk
from .wiki import BATCH, Wiki, WikiPage
from .wikireport import mark_interrupted, review_section, run_id, run_row, updated_page

log = logging.getLogger('infoboxsweep')

__all__ = ['Options', 'Bot', 'Stopped', 'edit_summary', 'RUN_WORDS']

# What the Run page must say for a live run to start, or carry on.
RUN_WORDS = ('yes', 'true', 'run', 'on')
SUMMARY_LIMIT = 400   # characters; MediaWiki cuts summaries at 500 bytes

# Errors that will happen on every save, so the run stops at the first.
FATAL_SAVE_ERRORS = ('UserBlockedError', 'NoUsernameError', 'ReadOnlyError')

TALK_NS = 1


@dataclass(frozen=True)
class Options:
    task: Task = INFOBOX
    live: bool = False
    trial: bool = False                     # live without the bot flag, for a BRFA trial
    category: str | None = None             # the root of the tree; default: the task's
    namespaces: tuple[int, ...] = (TALK_NS,)   # talk pages of articles only
    pages: tuple[str, ...] = ()             # only these pages, instead of the tree
    limit: int = 0                          # stop after checking this many pages; 0: no limit
    max_edits: int = 0                      # stop after this many edits; 0: no limit
    run_page: str | None = None             # default: User:<account>/Run
    report_page: str | None = None          # default: User:<account>/<task's>; '' for none
    stop_file: Path | None = None           # the run stops, cleanly, once this exists
    progress_minutes: int = 30              # update the report page on these marks; 0: at the end
    brfa: str | None = None                 # linked from every edit summary; default: the
                                            # task's; '' for none
    summary_suffix: str = ''                # added to every edit summary
    out_dir: Path = field(default_factory=lambda: Path('out'))
    failures_in_a_row: int = 5


class Stopped(Exception):
    """The run can't start, or must not carry on."""


class RunPageStopped(Stopped):
    """The Run page doesn't say yes: someone has stopped the bot."""


class OperatorStopped(Stopped):
    """The bot's operator has asked the run to stop, with its stop file or
    SIGTERM (toolforge jobs delete)."""


OPERATOR_STOP = 'manually stopped by the bot operator'


def _now() -> datetime:
    return datetime.now(UTC)


def next_mark(after: datetime, minutes: int) -> datetime:
    """The first time after after that is a whole number of minutes from
    that day's midnight: for 30, the next hour or half hour."""
    midnight = after.replace(hour=0, minute=0, second=0, microsecond=0)
    step = timedelta(minutes=minutes)
    return midnight + ((after - midnight) // step + 1) * step


class Bot:
    def __init__(self, wiki: Wiki, options: Options,
                 now: Callable[[], datetime] = _now) -> None:
        self.wiki = wiki
        self.options = options
        self.task = options.task
        self.category = options.category or self.task.root
        self.brfa = self.task.brfa if options.brfa is None else options.brfa
        self.now = now
        self.report = Report(options.live, now(), root=self.category, thing=self.task.thing)
        self.request_names: list[str] = list(self.task.request_templates)
        self.tree_categories: set[str] = set()
        self._topic_cache: set[str] | None = None
        self.run_page: str | None = None
        self.started_live = False   # logged in, and the Run page said yes
        self.next_progress: datetime | None = None
        self.looked_at: set[str] = set()   # the pages checked, for the review list
        self.report_path: Path | None = None
        self.stopped_by: Stopped | None = None
        self.stop_requested = False   # SIGTERM
        self.failures = 0

    def run(self) -> Report:
        """Do the run, and write the report.  Never raises: why the run
        stopped, if it did, is on the report instead.  The operator can stop
        it cleanly, still reporting on the wiki, by creating the stop file
        or with SIGTERM; when it has finished, it deletes the stop file."""
        stop_file = self.options.stop_file
        if stop_file and stop_file.exists():
            log.warning('Removing %s, left from an earlier run', stop_file)
            stop_file.unlink()
        previous = self._catch(signal.SIGTERM)
        try:
            self._run()
        except Stopped as reason:
            log.error('Stopped: %s', reason)
            self.report.stopped = str(reason)
            self.stopped_by = reason
        except Exception as error:   # noqa: BLE001 - such as failing to log in
            log.exception('Stopped by an error outside the page loop')
            self.report.stopped = f'{type(error).__name__}: {error}'
            self.report.errors.append(('(the run)', self.report.stopped))
        self.report.finished = self.now()
        if self.started_live:
            self._report_on_wiki(final=True, now=self.report.finished)
        self.report.stopped_by_operator = isinstance(self.stopped_by, OperatorStopped)
        path = self.report.write(self.options.out_dir)
        log.info('Report written to %s', path)
        self.report_path = path
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
        if stop_file:
            stop_file.unlink(missing_ok=True)
        return self.report

    def _catch(self, signum: int) -> Any:
        """Stop cleanly on signum, rather than die; returns the handler it
        replaced, or None if it couldn't (only the main thread can)."""
        def stop(signum: int, frame: object) -> None:
            log.warning('Got %s: stopping after this batch', signal.Signals(signum).name)
            self.stop_requested = True
        try:
            return signal.signal(signum, stop)
        except ValueError:
            return None

    def _check_operator_stop(self) -> None:
        if self.stop_requested or (self.options.stop_file and self.options.stop_file.exists()):
            raise OperatorStopped(OPERATOR_STOP)

    # -- the run -----------------------------------------------------------

    def _run(self) -> None:
        if self.options.live:
            self._preflight()
        self.request_names = self.task.request_names(self.wiki)
        titles = self._titles()
        done = 0
        for start in range(0, len(titles), BATCH):
            self._check_operator_stop()
            if self._limit_reached():
                break
            done += self._process_batch(titles[start:start + BATCH])
            self._maybe_report_progress()
        if done < len(titles) and self._limit_reached():
            log.info('Finished early: %s', self.report.ended_early)

    def _limit_reached(self) -> bool:
        """Whether --limit or --max-edits has been reached; if so, the
        report says so."""
        if self.options.limit and self.report.checked >= self.options.limit:
            self.report.ended_early = f'checked {self.report.checked} pages (--limit)'
        elif self.options.max_edits and len(self.report.edits) >= self.options.max_edits:
            self.report.ended_early = f'{len(self.report.edits)} edits (--max-edits)'
        return self.report.ended_early is not None

    def _preflight(self) -> None:
        account = self.wiki.login()
        self.report.account = account
        log.info('Logged in as %s', account)
        if not self.options.trial and not self.wiki.has_right('bot'):
            raise Stopped(f'{account} does not have the bot flag. Use --trial for '
                          'approved trial edits, or a dry run until the bot is approved')
        self.run_page = self.options.run_page or f'User:{account}/Run'
        self._check_run_page()
        self.started_live = True
        if self.options.progress_minutes:
            self.next_progress = next_mark(self.now(), self.options.progress_minutes)
        self._report_start()

    def _check_run_page(self) -> None:
        """Stop unless the Run page says to run: anyone can stop the bot by
        editing it."""
        assert self.run_page is not None
        text = self.wiki.text_of(self.run_page)
        if text is None:
            raise RunPageStopped(f'{self.run_page} does not exist. Create it, saying "yes", '
                                 'so that anyone can stop the bot by changing it')
        if text.strip().lower() not in RUN_WORDS:
            raise RunPageStopped(f'{self.run_page} does not say "yes"')

    def _titles(self) -> list[str]:
        """The pages to go through: the tree's, or those given."""
        if self.options.pages:
            self.report.source = 'only the pages asked for (--page)'
            return list(dict.fromkeys(self._talk_title(t) for t in self.options.pages))
        self.report.source = f'every page in the tree under [[:{self.category}]]'
        tree = walk(self.wiki, self.category, check=self._check_operator_stop,
                    follow=self.task.follows)
        self._note_tree(tree)
        if self.started_live:
            self._report_on_wiki(final=False, now=self.now())
        return tree.pages

    def _talk_title(self, title: str) -> str:
        """A page given with --page, as its talk page."""
        page = self.wiki.page(title)
        if page.isTalkPage():
            return page.title()
        talk = page.toggleTalkPage()
        return talk.title() if talk is not None else page.title()

    def _note_tree(self, tree: Tree) -> None:
        self.tree_categories = set(tree.categories)
        self.report.categories = len(tree.categories)
        self.report.found = len(tree.pages)
        self.report.duplicates = tree.duplicates
        self.report.depth = tree.depth
        self.report.not_followed = tree.not_followed
        for category, parent in tree.not_followed:
            self.report.review(category, '', f'a subcategory of {parent} without '
                               f'{self.task.keyword_text()} in its name: not followed. Is it in '
                               'the right place?')
        if tree.truncated:
            self.report.errors.append((self.category, 'the tree has more categories '
                                       'than the bot reads: only part of it was gone through'))

    # -- each batch of pages -----------------------------------------------

    def _process_batch(self, titles: list[str]) -> int:
        """Check BATCH talk pages: their text, their articles' text, and
        whether the articles have what was asked for, in a few requests.
        Returns how many of the titles it went through, which is fewer than
        all of them if --limit or --max-edits was reached."""
        try:
            pairs = list(self._pairs(titles))
            articles = [article for _, article in pairs
                        if article.exists() and not article.isRedirectPage()]
            verdicts = self.task.check(self.wiki, articles, self.request_names) if articles else {}
        except Exception as error:   # noqa: BLE001 - the next batch may do better
            log.exception('Could not load the batch starting %s', titles[0])
            for title in titles:
                self.report.errors.append((title, f'{type(error).__name__}: {error}'))
            self._failed(error, titles[0])
            return len(titles)
        index = {title: i for i, title in enumerate(titles)}
        for talk, article in pairs:
            if self._limit_reached():
                return index.get(talk.title(), 0)
            self._process_safely(talk, article, verdicts.get(article.title()))
        return len(titles)

    def _pairs(self, titles: list[str]) -> Iterator[tuple[WikiPage, WikiPage]]:
        """(talk page, its article) for the titles that are talk pages to
        check; the others are skipped, or left for a human, here."""
        talks: list[tuple[WikiPage, str]] = []
        for talk in self.wiki.load(titles):
            title = talk.title()
            if not talk.exists():
                self.report.skip(title, 'the page does not exist (any more)')
            elif talk.isRedirectPage():
                self.report.skip(title, 'the page is a redirect')
            elif not talk.isTalkPage():
                self.report.review(title, '', 'not a talk page: the request is on the page '
                                              'itself, where the bot does not edit')
            elif int(talk.namespace()) not in self.options.namespaces:
                self.report.skip(title, f'not in namespace {self._namespaces()}')
            else:
                subject = talk.toggleTalkPage()
                assert subject is not None
                talks.append((talk, subject.title()))
        articles = {page.title(): page for page in self.wiki.load(s for _, s in talks)}
        for talk, name in talks:
            yield talk, articles[name]

    def _process_safely(self, talk: WikiPage, article: WikiPage,
                        found: Verdict | None) -> None:
        title = talk.title()
        try:
            self._process(talk, article, found)
        except Stopped:
            raise
        except Exception as error:   # noqa: BLE001 - one bad page mustn't stop the run
            log.exception('%s: %s', title, error)
            self.report.errors.append((title, f'{type(error).__name__}: {error}'))
            self._failed(error, title)
        else:
            self.failures = 0

    def _failed(self, error: Exception, title: str) -> None:
        if type(error).__name__ in FATAL_SAVE_ERRORS:
            raise Stopped(f'saving {title} failed in a way every save would: '
                          f'{type(error).__name__}') from error
        self.failures += 1
        if self.failures >= self.options.failures_in_a_row:
            raise Stopped(f'{self.failures} pages in a row failed') from error

    def _process(self, talk: WikiPage, article: WikiPage, found: Verdict | None) -> None:
        title, name = talk.title(), article.title()
        self.report.checked += 1
        self.looked_at.add(title)
        if not article.exists():
            self.report.review(title, name, 'the article does not exist')
            return
        if article.isRedirectPage():
            self.report.review(title, name, 'the article is a redirect: should the talk page '
                                            'be one too?')
            return
        assert found is not None
        if found.review:
            self.report.review(title, name, found.review)
            return
        if not found.found:
            self.report.unfulfilled += 1
            log.debug('%s: not yet (%s)', name, found.evidence)
            return
        self.report.fulfilled += 1
        task = self.task
        removal = remove_requests(talk.text, self.request_names, self.tree_categories,
                                  params=task.request_params,
                                  template_params=task.template_params,
                                  topics=self._topics(), details=task.details)
        if removal.specific:
            self.report.review(title, name, f'the article has {task.thing} ({found.evidence}), '
                               'but ' + '; '.join(removal.specific))
        elif not removal.changed:
            self._request_not_found(talk, name)
        elif not talk.botMayEdit():
            self.report.skip(title, 'excludes the bot with {{bots}} or {{nobots}}')
        elif self._still_requested(title, name, removal):
            return
        else:
            self._edit(talk, name, removal, found)

    def _topics(self) -> set[str] | None:
        """The tree's topics, for telling a topic from a description in the
        request template's unnamed values; None, to take them all as topics,
        when the tree wasn't walked (with --page)."""
        if not self.tree_categories:
            return None
        if self._topic_cache is None:
            self._topic_cache = topics_of(self.tree_categories)
        return self._topic_cache

    def _request_categories(self, title: str, text: str) -> list[str]:
        """The request categories the page title would be in with text, as
        MediaWiki parses it."""
        return sorted(c for c in self.wiki.categories_with(title, text)
                      if c in self.tree_categories or self.task.is_request_category(c))

    def _request_not_found(self, talk: WikiPage, article: str) -> None:
        """The bot can't see a request on the talk page.  If MediaWiki says
        the page is in no request category now, it was fixed since the
        category was listed (MediaWiki updates category listings a little
        after an edit); otherwise the request comes some way the bot doesn't
        know, so it's left for a human."""
        title = talk.title()
        left = self._request_categories(title, talk.text)
        if not left:
            self.report.skip(title, f'no longer asks for {self.task.thing} (the category '
                                    'listing was out of date)')
            return
        self.report.review(title, article, f'the article has {self.task.thing}, but the bot '
                           'could not find the request on the talk page, which is in '
                           + ', '.join(left))

    def _still_requested(self, title: str, article: str, removal: Removal) -> bool:
        """Check with MediaWiki that the talk page would leave the request
        categories once the bot's change is saved; if it wouldn't, the
        request comes some other way, so leave it for a human."""
        left = self._request_categories(title, removal.text)
        if not left:
            return False
        self.report.review(title, article, f'the article has {self.task.thing}, but after '
                           'removing ' + ', '.join(removal.removed) + ' the talk page would '
                           'still be in ' + ', '.join(left))
        return True

    def _edit(self, talk: WikiPage, article: str, removal: Removal, found: Verdict) -> None:
        title = talk.title()
        summary = edit_summary(article, removal.removed, self.options.summary_suffix,
                               brfa=self.brfa, trial=self.options.trial, task=self.task,
                               shown=found.shown)
        edit = Edit(title, article, removal.removed, summary,
                    unified_diff(title, removal.original, removal.text), found.evidence)
        if self.options.live:
            self._check_run_page()
            talk.text = removal.text
            talk.save(summary=summary, minor=True, bot=True, quiet=True)
            edit.saved = True
            log.info('Saved %s: %s', title, summary)
        else:
            log.info('Would edit %s: %s', title, summary)
        self.report.edits.append(edit)

    def _namespaces(self) -> str:
        return ', '.join(map(str, self.options.namespaces))

    # -- the report page on the wiki -----------------------------------------

    def _report_page(self) -> str | None:
        if self.options.report_page == '':
            return None
        return self.options.report_page or f'User:{self.report.account}/{self.task.report}'

    def _report_start(self) -> None:
        """Add this run's row to the report page as soon as it starts.  Rows
        of earlier runs that still say running, but haven't reported for two
        progress intervals (at least two hours), died without saying so (a
        Toolforge job killed, say): they're marked as interrupted."""
        report_page = self._report_page()
        if not report_page:
            return
        quiet = timedelta(minutes=2 * max(self.options.progress_minutes, 60))
        stale_before = self.report.started - quiet
        row = run_row(self.report, starting=True)
        marked = 0

        def text(old: str | None) -> str:
            nonlocal marked
            old, marked = mark_interrupted(old, run=run_id(self.report),
                                           stale_before=stale_before)
            return updated_page(old, row, review=None, header=self._header(),
                                intro=self._intro())

        def summary() -> str:
            earlier = (f'; marked {marked} earlier run' + ('s' if marked > 1 else '')
                       + ' that stopped reporting as interrupted') if marked else ''
            return f'Starting a run{earlier}'

        self._save_bot_page(report_page, text, summary, final=False)

    def _header(self) -> str:
        return f'{{{{User:{self.report.account}/Header}}}}'

    def _intro(self) -> str:
        account = self.report.account
        return (f"Runs of [[User:{account}|{account}]]'s task {self.task.doing}"
                f'{_approval(self.brfa)}, newest first. It goes through every page in '
                f'[[:{self.category}]] and all its subcategories. The bot adds a row '
                'when a live run starts, updates it as the run goes, and gives the final '
                'numbers when the run ends. Pages it could not deal with on its own are listed '
                'under [[#Needs manual review|Needs manual review]].')

    def _maybe_report_progress(self) -> None:
        """During a live run, bring the report page up to date on the clock,
        every progress_minutes from midnight UTC, so a long run shows how it's
        going.  Checks the Run page too, which stops the run if it says to."""
        if not self.started_live or self.next_progress is None:
            return
        now = self.now()
        if now >= self.next_progress:
            self.next_progress = next_mark(now, self.options.progress_minutes)
            self._check_run_page()
            log.info('Reporting progress: %d pages checked, %d changed',
                     self.report.checked, len(self.report.edits))
            self._report_on_wiki(final=False, now=now)

    def _report_on_wiki(self, *, final: bool, now: datetime) -> None:
        """Bring this run's row, and the review list, up to date.  Never
        raises.  Once someone has stopped the bot with the Run page, only
        the row is updated, saying when the Run page was changed."""
        report_page = self._report_page()
        if not report_page:
            return
        aborted = isinstance(self.stopped_by, RunPageStopped)
        stop = self.stopped_by if aborted else (self._run_page_stop() if final else None)
        by_operator = isinstance(self.stopped_by, OperatorStopped)
        result = (self._abort_note() if aborted else
                  f'{OPERATOR_STOP} at {now:%Y-%m-%d %H:%M}' if by_operator else None)
        row = run_row(self.report, now=now, result=result)
        complete = (final and not self.report.stopped and not self.report.ended_early
                    and not self.options.pages)
        found = self._review_entries()

        def text(old: str | None) -> str:
            review = None if stop is not None else review_section(
                old, found=found, looked_at=self.looked_at, complete=complete, when=now,
                started=self.report.started)
            return updated_page(old, row, review=review, header=self._header(),
                                intro=self._intro())

        summary = (('Report' if final else 'Progress') + ' of a run'
                   + (f', stopped by [[{self.run_page}]]' if aborted else '')
                   + (f', {OPERATOR_STOP}' if by_operator else '')
                   + f': {self.report.checked:,} talk pages checked, '
                   + f'{len(self.report.edits):,} changed'
                   + ('' if final else ' so far'))
        self.report.wiki_report = self._save_bot_page(report_page, text, summary, final)

    def _review_entries(self) -> dict[str, tuple[str, str]]:
        """{page: (article, why)} for the pages to list for a human: those
        left for review, and those that had errors."""
        entries: dict[str, tuple[str, str]] = {}
        for title, article, why in self.report.reviews:
            entries[title] = (article, why)
        for title, error in self.report.errors:
            entries.setdefault(title, ('', f'error: {error}'))
        return entries

    def _run_page_stop(self) -> Stopped | None:
        try:
            self._check_run_page()
        except RunPageStopped as reason:
            return reason
        return None

    def _abort_note(self) -> str:
        """The Result of a run someone stopped with the Run page: when the
        page was changed, by whom."""
        page = f'[[{self.run_page}]]'
        try:
            change = self.wiki.last_change(self.run_page or '')
        except Exception as error:   # noqa: BLE001 - the note can do without it
            log.warning('Could not read when %s was changed: %s', self.run_page, error)
            change = None
        if change is None:
            return f'{page} was changed, and the run aborted'
        when, user = change
        by = f' by [[User:{user}|{user}]]' if user else ''
        return f'at {when:%Y-%m-%d %H:%M} {page} was changed{by}, and the run aborted'

    def _save_bot_page(self, title: str, make_text: Callable[[str | None], str],
                       summary: str | Callable[[], str], final: bool, attempts: int = 5) -> str:
        """Save make_text(the page's text, or None if it's missing) to the
        report page, unless that's no change; return what happened.  An
        edit conflict is tried again, from the new text."""
        for attempt in range(1, attempts + 1):
            page = self.wiki.page(title)
            current: str | None = None
            try:
                current = page.text if page.exists() else None
                new = make_text(current)
                if new == current:
                    return f'{title} already up to date'
                page.text = new
                page.save(summary=summary if isinstance(summary, str) else summary(),
                          minor=True, bot=True, quiet=True)
            except Exception as error:   # noqa: BLE001 - never stops the run
                page.text = current or ''   # as it was, for the next try
                if 'EditConflict' in type(error).__name__ and attempt < attempts:
                    log.info('Edit conflict saving %s: trying again', title)
                    continue
                if final:
                    log.exception('Could not save %s', title)
                    self.report.errors.append((title, f'{type(error).__name__}: {error}'))
                else:
                    log.warning('Could not save %s: %s: %s', title, type(error).__name__, error)
                return f'not saved to {title}: {type(error).__name__}'
            log.info('Saved %s', title)
            return f'saved to {title}'
        raise AssertionError('unreachable')   # pragma: no cover


def _approval(brfa: str) -> str:
    return f' ([[{brfa}|{brfa.rsplit("/", 1)[-1]}]])' if brfa else ''


def edit_summary(article: str, removed: Iterable[str], suffix: str = '', *,
                 brfa: str | None = None, trial: bool = False, task: Task = INFOBOX,
                 shown: str = '') -> str:
    """The edit summary: "Removing infobox request ({{Infobox requested}}):
    [[Foo]] has an infobox (ZackBot 15)", with what was removed, cut short
    if there's too much, and what the article has, if shown."""
    brfa = task.brfa if brfa is None else brfa
    head = 'BRFA trial: ' if trial else ''
    tail = f'{_approval(brfa)}' + (f' {suffix}' if suffix else '')
    body = f': [[{article}]] has {task.thing}' + (f', {shown}' if shown else '')
    action = f'Removing {task.request}'
    listed = '; '.join(removed)
    room = SUMMARY_LIMIT - len(head) - len(body) - len(tail) - len(action) - len(' ()')
    if len(listed) > room:
        listed = listed[:max(0, room - 1)].rsplit('; ', 1)[0] + '; …'
    return f'{head}{action} ({listed}){body}{tail}'
