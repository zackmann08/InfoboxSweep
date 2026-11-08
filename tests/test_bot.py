"""A whole run, against the fake wiki."""

from datetime import UTC, datetime, timedelta

import pytest

from infoboxsweep import ROOT_CATEGORY
from infoboxsweep.bot import Bot, edit_summary, next_mark
from infoboxsweep.tasks import INFOBOX
from infoboxsweep.wikireport import MARKER, REVIEW_START, review_lines
from tests.fakes import (
    BIO_CATEGORY,
    FILM_CATEGORY,
    FILM_TALK,
    INFOBOX_ARTICLE,
    PLAIN_ARTICLE,
    EditConflictError,
    FakePage,
    FakeWiki,
    SaveError,
    UserBlockedError,
    options,
)

START = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


class Clock:
    """A clock that moves on a minute each time it's read."""

    def __init__(self, start=START, step=timedelta(minutes=1)):
        self.time, self.step = start, step

    def __call__(self):
        now = self.time
        self.time += self.step
        return now


def run(wiki, tmp_path, clock=None, **changes):
    bot = Bot(wiki, options(tmp_path, **changes), now=clock or Clock())
    return bot, bot.run()


def film_wiki():
    """Three talk pages: one to fix, one whose article has no infobox, and
    one whose article doesn't exist."""
    wiki = FakeWiki()
    wiki.tree(ROOT_CATEGORY, subcats=[FILM_CATEGORY])
    wiki.request('Example', INFOBOX_ARTICLE, FILM_TALK, category=FILM_CATEGORY)
    wiki.request('Plain', PLAIN_ARTICLE, FILM_TALK, infobox=False, category=FILM_CATEGORY)
    wiki.add(FakePage('Talk:Gone', FILM_TALK))
    wiki.tree(FILM_CATEGORY, pages=['Talk:Gone', 'Talk:Example'])   # Example listed twice
    return wiki


# -- dry runs ------------------------------------------------------------------

def test_dry_run(tmp_path):
    wiki = film_wiki()
    bot, report = run(wiki, tmp_path)
    assert not wiki.logged_in and wiki.saves == []
    assert report.categories == 2 and report.found == 3 and report.duplicates == 1
    assert report.checked == 3 and report.fulfilled == 1 and report.unfulfilled == 1
    [edit] = report.edits
    assert edit.talk == 'Talk:Example' and not edit.saved
    assert edit.removed == ['needs-infobox=yes from {{WikiProject Film}}']
    assert edit.evidence == 'transcludes Template:Infobox'
    assert '-{{WikiProject Film|needs-infobox=yes}}' in edit.diff
    assert report.reviews == [('Talk:Gone', 'Gone', 'the article does not exist')]
    assert wiki.parsed == ['Talk:Example']   # checked with MediaWiki, even in a dry run
    text = bot.report_path.read_text()
    assert 'DRY RUN' in text and 'Would change:         1' in text
    assert '### Talk:Example' in text and 'Talk:Gone (Gone): the article does not exist' in text


def test_only_the_pages_asked_for(tmp_path):
    wiki = film_wiki()
    _, report = run(wiki, tmp_path, pages=('Example', 'Talk:Example', 'Talk:Plain'))
    assert wiki.read == []   # no walk
    assert report.source == 'only the pages asked for (--page)'
    assert report.checked == 2 and len(report.edits) == 1


def test_still_requested_another_way(tmp_path):
    wiki = film_wiki()
    wiki.sticky['Talk:Example'] = {FILM_CATEGORY, 'Category:Films'}
    _, report = run(wiki, tmp_path)
    assert report.edits == []
    [(title, article, why)] = [r for r in report.reviews if r[0] == 'Talk:Example']
    assert why.endswith(f'the talk page would still be in {FILM_CATEGORY}')


def test_still_requested_by_name_with_pages(tmp_path):
    # With --page there's no tree, so request categories are known by name.
    wiki = film_wiki()
    wiki.sticky['Talk:Example'] = {'Category:Ship articles needing infoboxes'}
    _, report = run(wiki, tmp_path, pages=('Talk:Example',))
    assert report.edits == [] and len(report.reviews) == 1


def test_already_fixed_but_still_listed(tmp_path):
    # The category listing lags behind an edit: the page is skipped, not
    # left for review.
    wiki = FakeWiki().request('Example', INFOBOX_ARTICLE, '{{WikiProject Film}}')
    _, report = run(wiki, tmp_path)
    assert report.reviews == [] and report.edits == []
    assert report.skipped == [('Talk:Example', 'no longer asks for an infobox (the category '
                                               'listing was out of date)')]


@pytest.mark.parametrize(('talk_text', 'article_text', 'transcludes', 'why'), [
    ('{{WikiProject Film|needs-infobox=}}', INFOBOX_ARTICLE, True,
     'could not find the request on the talk page, which is in Category:Wikipedia articles'),
    (FILM_TALK, '{{Infobox film}}', False, 'does not transclude Template:Infobox'),
])
def test_left_for_review(tmp_path, talk_text, article_text, transcludes, why):
    wiki = FakeWiki().request('Example', article_text, talk_text, infobox=transcludes)
    # Put there some way the bot doesn't know.
    wiki.sticky['Talk:Example'] = {ROOT_CATEGORY}
    _, report = run(wiki, tmp_path)
    assert report.edits == []
    [(_, _, reason)] = report.reviews
    assert why in reason


def test_pages_that_are_not_checked(tmp_path):
    wiki = FakeWiki()
    wiki.add(FakePage('Talk:Redirect', '#REDIRECT [[Talk:X]]', redirect=True),
             FakePage('Article', '{{Infobox film}}'),
             FakePage('User talk:Someone', FILM_TALK),
             FakePage('Talk:Moved', FILM_TALK), FakePage('Moved', '#REDIRECT', redirect=True))
    wiki.request('Excluded', INFOBOX_ARTICLE, FILM_TALK, may_edit=False)
    wiki.tree(ROOT_CATEGORY, pages=['Talk:Missing', 'Talk:Redirect', 'Article',
                                    'User talk:Someone', 'Talk:Moved'])
    _, report = run(wiki, tmp_path)
    assert report.edits == []
    assert dict(report.skipped) == {
        'Talk:Missing': 'the page does not exist (any more)',
        'Talk:Redirect': 'the page is a redirect',
        'User talk:Someone': 'not in namespace 1',
        'Talk:Excluded': 'excludes the bot with {{bots}} or {{nobots}}'}
    reviews = {title: why for title, _, why in report.reviews}
    assert reviews['Article'].startswith('not a talk page')
    assert reviews['Talk:Moved'].startswith('the article is a redirect')


def test_other_namespaces_in_a_dry_run(tmp_path):
    wiki = FakeWiki().add(FakePage('Draft talk:X', FILM_TALK), FakePage('Draft:X', PLAIN_ARTICLE))
    wiki.tree(ROOT_CATEGORY, pages=['Draft talk:X'])
    _, report = run(wiki, tmp_path, namespaces=(1, 119))
    assert report.checked == 1 and report.unfulfilled == 1


def test_limit_and_max_edits(tmp_path):
    wiki = FakeWiki()
    for i in range(60):   # more than a batch
        wiki.request(f'Film {i}', INFOBOX_ARTICLE, FILM_TALK)
    _, report = run(wiki, tmp_path, limit=55)
    assert report.checked == 55 and report.ended_early == 'checked 55 pages (--limit)'
    _, report = run(wiki, tmp_path, max_edits=3)
    assert len(report.edits) == 3 and report.ended_early == '3 edits (--max-edits)'
    _, report = run(wiki, tmp_path, limit=50)   # exactly one batch
    assert report.checked == 50 and report.ended_early


# -- live runs -----------------------------------------------------------------

def test_live_run(tmp_path):
    wiki = film_wiki()
    talk = wiki.page('Talk:Example')
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert wiki.logged_in and report.account == 'ExampleBot'
    assert talk.saved == ['{{WikiProject banner shell|class=Start|\n{{WikiProject Film}}\n}}\n'
                          '== Plot ==\nNeeds work.']
    assert talk.summaries == [
        'Removing infobox request (needs-infobox=yes from {{WikiProject Film}}): [[Example]] '
        'has an infobox ([[Wikipedia:Bots/Requests for approval/ZackBot 10|ZackBot 10]])']
    assert report.edits[0].saved
    # The report page: when the run started, after the walk, and at the end.
    page = wiki.report_page
    assert len(page.saved) == 3
    assert page.summaries[0] == 'Starting a run'
    assert page.saved[0].count('|| started') == 1 and REVIEW_START in page.saved[0]
    assert '|| 2 || 3 || 0 || 0 || 0 || running' in page.saved[1]
    assert page.summaries[2] == 'Report of a run: 3 talk pages checked, 1 changed'
    final = page.text
    assert ('| 2026-11-07 12:00 || 2026-11-07 12:0' in final
            and '|| 2 || 3 || 3 || 1 || [[#Needs manual review|1]] || finished' in final)
    assert review_lines(final) == {
        'Talk:Gone': '| [[:Talk:Gone]] || [[Gone]] || <nowiki>the article does not exist</nowiki>'}
    assert 'Updated 2026-11-07' in final and '1 page needs manual review.' in final
    assert report.wiki_report == 'saved to User:ExampleBot/InfoboxReport'


def test_live_run_needs_the_bot_flag(tmp_path):
    wiki = film_wiki()
    wiki.rights = set()
    _, report = run(wiki, tmp_path, live=True)
    assert 'does not have the bot flag' in report.stopped and wiki.saves == []
    _, report = run(wiki, tmp_path, live=True, trial=True, progress_minutes=0)
    assert not report.stopped
    assert wiki.page('Talk:Example').summaries[0].startswith('BRFA trial: Removing')


@pytest.mark.parametrize(('run_text', 'why'), [(None, 'does not exist'),
                                               ('no', 'does not say "yes"')])
def test_the_run_page_must_say_yes(tmp_path, run_text, why):
    wiki = film_wiki()
    if run_text is None:
        del wiki.pages[wiki.run_page.title()]
    else:
        wiki.run_page.text = run_text
    bot, report = run(wiki, tmp_path, live=True)
    assert why in report.stopped and wiki.saves == [] and not bot.started_live


def test_stopped_by_the_run_page_part_way(tmp_path):
    wiki = film_wiki()
    wiki.report_page.text = None   # replaced below, once the run has started
    wiki.report_page._exists = False

    def stop():
        wiki.run_page.text = 'no'
    wiki.page('Talk:Gone').toggleTalkPage = lambda: (stop(), wiki.page('Gone'))[1]
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert 'does not say "yes"' in report.stopped
    assert wiki.page('Talk:Example').saved == []
    final = wiki.report_page.text
    assert ('at 2026-11-07 04:58 [[User:ExampleBot/Run]] was changed by '
            '[[User:Example|Example]], and the run aborted') in final
    assert review_lines(final) == {}   # the review list is left as the walk's report left it
    assert 'stopped by [[User:ExampleBot/Run]]' in wiki.report_page.summaries[-1]


def test_stopped_by_the_run_page_with_its_history_hidden(tmp_path):
    wiki = film_wiki()
    wiki.run_page.text = 'no'
    bot = Bot(wiki, options(tmp_path, live=True), now=Clock())
    bot.run_page = 'User:ExampleBot/Run'
    wiki.last_change = lambda title: None
    assert bot._abort_note() == '[[User:ExampleBot/Run]] was changed, and the run aborted'

    def broken(title):
        raise ConnectionError('timed out')
    wiki.last_change = broken
    assert bot._abort_note() == '[[User:ExampleBot/Run]] was changed, and the run aborted'


def test_run_page_changed_after_the_last_edit(tmp_path):
    # The run finishes, but the Run page says no by the end: the row says
    # so, and the review list is left alone.
    wiki = film_wiki()
    wiki.tree(FILM_CATEGORY, pages=['Talk:Plain'])

    original = wiki.page('Talk:Example').save

    def save(**kwargs):
        original(**kwargs)
        wiki.run_page.text = 'off duty'
    wiki.page('Talk:Example').save = save
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert not report.stopped and len(report.edits) == 1
    # Talk:Gone was left for review, but the list isn't brought up to date.
    assert review_lines(wiki.report_page.text) == {}
    assert '|| finished' in wiki.report_page.text


def test_progress_reports_on_the_clock(tmp_path):
    wiki = FakeWiki()
    for i in range(120):   # three batches
        wiki.request(f'Film {i}', PLAIN_ARTICLE, FILM_TALK, infobox=False)
    clock = Clock(start=datetime(2026, 11, 7, 12, 50, tzinfo=UTC), step=timedelta(minutes=7))
    _, report = run(wiki, tmp_path, clock=clock, live=True)
    summaries = wiki.report_page.summaries
    assert summaries[0] == 'Starting a run'
    assert any(s.startswith('Progress of a run: 50 talk pages checked') for s in summaries)
    assert summaries[-1] == 'Report of a run: 120 talk pages checked, 0 changed'


def test_marks_runs_that_died(tmp_path):
    wiki = film_wiki()
    wiki.report_page.text = (
        'Intro\n\n== Runs ==\n{| class="wikitable"\n! headings\n' + MARKER + '\n'
        '|- data-run="20261101T000000.000000"\n| 2026-11-01 00:00 || — || 1 h || 1 || 1 || 1 '
        '|| 0 || 0 || running (last updated 2026-11-01 01:00)\n'
        '|- data-run="20261102T000000.000000"\n| 2026-11-02 00:00 || — || — || — || — || 0 '
        '|| 0 || 0 || started\n|}\n')
    run(wiki, tmp_path, live=True, progress_minutes=0)
    assert wiki.report_page.summaries[0] == ('Starting a run; marked 2 earlier runs that '
                                             'stopped reporting as interrupted')
    assert 'interrupted (last updated 2026-11-01 01:00)' in wiki.report_page.text
    assert 'interrupted (before its first progress report)' in wiki.report_page.text
    assert wiki.report_page.text.startswith('Intro\n')   # kept as it was


def test_a_partial_run_keeps_the_others_on_the_review_list(tmp_path):
    wiki = film_wiki()
    wiki.report_page.text = (
        'Intro\n' + MARKER + '\n|}\n' + REVIEW_START + '\nUpdated.\n'
        '{| class="wikitable sortable"\n! Page !! Article !! Why\n'
        '|-\n| [[:Talk:Elsewhere]] || [[Elsewhere]] || <nowiki>old</nowiki>\n'
        '|-\n| [[:Talk:Example]] || [[Example]] || <nowiki>fixed since</nowiki>\n'
        '|}\n<!-- InfoboxSweep review end -->\n')
    run(wiki, tmp_path, live=True, progress_minutes=0, pages=('Talk:Example', 'Talk:Gone'))
    assert sorted(review_lines(wiki.report_page.text)) == ['Talk:Elsewhere', 'Talk:Gone']
    # A complete run replaces the list.
    run(wiki, tmp_path, live=True, progress_minutes=0)
    assert sorted(review_lines(wiki.report_page.text)) == ['Talk:Gone']


def test_no_report_page(tmp_path):
    wiki = film_wiki()
    run(wiki, tmp_path, live=True, report_page='')
    assert wiki.saves == ['Talk:Example']


# -- errors --------------------------------------------------------------------

def test_an_error_on_one_page(tmp_path):
    wiki = film_wiki()
    wiki.page('Talk:Example')._save_errors = [SaveError('Protected')]
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert report.errors == [('Talk:Example', 'SaveError: Protected')]
    assert not report.stopped and report.checked == 3
    assert '|| finished (1 error)' in wiki.report_page.text
    assert '[[:Talk:Example]] || — || <nowiki>error: SaveError: Protected' in (
        wiki.report_page.text)


def test_five_failures_in_a_row_stop_the_run(tmp_path):
    wiki = FakeWiki()
    for i in range(8):
        wiki.request(f'Film {i}', INFOBOX_ARTICLE, FILM_TALK, save_errors=[SaveError('x')])
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert report.stopped == '5 pages in a row failed' and len(report.errors) == 5
    assert '2 errors' not in wiki.report_page.text and '(5 errors)' in wiki.report_page.text


def test_a_fatal_error_stops_the_run_at_once(tmp_path):
    wiki = FakeWiki()
    for i in range(3):
        wiki.request(f'Film {i}', INFOBOX_ARTICLE, FILM_TALK, save_errors=[UserBlockedError()])
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert 'failed in a way every save would: UserBlockedError' in report.stopped
    assert len(report.errors) == 1


def test_a_batch_that_will_not_load(tmp_path):
    wiki = film_wiki()
    wiki.broken_loads = 1
    _, report = run(wiki, tmp_path)
    assert len(report.errors) == 3 and report.checked == 0 and not report.stopped


def test_an_error_outside_the_page_loop(tmp_path):
    wiki = film_wiki()

    def login():
        raise RuntimeError('Could not log in')
    wiki.login = login
    _, report = run(wiki, tmp_path, live=True)
    assert report.stopped == 'RuntimeError: Could not log in'
    assert report.errors == [('(the run)', 'RuntimeError: Could not log in')]


def test_the_report_page_cannot_be_saved(tmp_path):
    wiki = film_wiki()
    wiki.report_page._save_errors = [SaveError('a'), SaveError('b'), SaveError('c')]
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert report.wiki_report == 'not saved to User:ExampleBot/InfoboxReport: SaveError'
    assert ('User:ExampleBot/InfoboxReport', 'SaveError: c') in report.errors


def test_an_edit_conflict_is_tried_again(tmp_path):
    wiki = film_wiki()
    wiki.report_page._save_errors = [EditConflictError()]
    _, report = run(wiki, tmp_path, live=True, progress_minutes=0)
    assert len(wiki.report_page.saved) == 3 and not report.errors


def test_a_report_with_nothing_new_is_not_saved(tmp_path):
    wiki = film_wiki()
    bot = Bot(wiki, options(tmp_path), now=Clock())
    assert bot._save_bot_page('User:ExampleBot/Run', lambda old: old, 'x',
                              final=True) == 'User:ExampleBot/Run already up to date'


# -- stopping on purpose -----------------------------------------------------

def test_the_stop_file(tmp_path):
    wiki = film_wiki()
    stop = tmp_path / 'stop'
    stop.write_text('')   # left from before: removed
    bot = Bot(wiki, options(tmp_path, live=True, stop_file=stop, progress_minutes=0),
              now=Clock())
    original = wiki.category_pages

    def pages(category):
        stop.write_text('')
        return original(category)
    wiki.category_pages = pages
    report = bot.run()
    assert report.stopped == 'manually stopped by the bot operator' and report.stopped_by_operator
    assert not stop.exists()
    assert 'manually stopped by the bot operator at 2026-11-07' in wiki.report_page.text
    assert 'manually stopped by the bot operator' in wiki.report_page.summaries[-1]


def test_sigterm(tmp_path):
    import os
    import signal
    wiki = film_wiki()
    bot = Bot(wiki, options(tmp_path), now=Clock())
    original = wiki.category_pages

    def pages(category):
        os.kill(os.getpid(), signal.SIGTERM)
        return original(category)
    wiki.category_pages = pages
    before = signal.getsignal(signal.SIGTERM)
    report = bot.run()
    assert report.stopped_by_operator
    assert signal.getsignal(signal.SIGTERM) == before


def test_not_in_the_main_thread(tmp_path):
    import threading
    reports = []
    thread = threading.Thread(target=lambda: reports.append(run(film_wiki(), tmp_path)[1]))
    thread.start()
    thread.join()
    assert len(reports[0].edits) == 1


# -- the tree, on the report ---------------------------------------------------

def test_categories_not_followed_and_a_tree_too_big(tmp_path, monkeypatch):
    wiki = film_wiki()
    wiki.tree(ROOT_CATEGORY, subcats=['Category:Films', BIO_CATEGORY])
    _, report = run(wiki, tmp_path)
    assert report.not_followed == [('Category:Films', ROOT_CATEGORY)]
    assert ('Category:Films', '', 'a subcategory of Category:Wikipedia articles with an '
            'infobox request without "infobox" in its name: not followed. Is it in the right '
            'place?') in report.reviews
    from infoboxsweep import tree
    monkeypatch.setattr(tree, 'MAX_CATEGORIES', 1)
    monkeypatch.setattr(tree.walk, '__kwdefaults__', {'max_categories': 1,
                                                       'check': lambda: None})
    _, report = run(wiki, tmp_path)
    assert report.errors[0][1].startswith('the tree has more categories than the bot reads')


# -- small parts ---------------------------------------------------------------

def test_edit_summary():
    assert edit_summary('Foo', ['{{Infobox requested}}'], brfa='') == (
        'Removing infobox request ({{Infobox requested}}): [[Foo]] has an infobox')
    assert edit_summary('Foo', ['x'], 'thanks', brfa='', trial=True) == (
        'BRFA trial: Removing infobox request (x): [[Foo]] has an infobox thanks')
    long = edit_summary('Foo', [f'needs-infobox=yes from {{{{WikiProject {i}}}}}'
                                for i in range(40)])
    assert len(long) <= 400 and '; …)' in long


def test_next_mark():
    assert next_mark(datetime(2026, 1, 1, 2, 49), 30) == datetime(2026, 1, 1, 3, 0)
    assert next_mark(datetime(2026, 1, 1, 3, 0), 30) == datetime(2026, 1, 1, 3, 30)


def test_is_request_category():
    assert INFOBOX.is_request_category('Category:Wikipedia articles with an infobox request')
    assert INFOBOX.is_request_category('Category:Film articles needing infoboxes')
    assert not INFOBOX.is_request_category('Category:Infobox templates')
