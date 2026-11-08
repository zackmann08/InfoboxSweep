"""The report page's text."""

from datetime import UTC, datetime, timedelta

from infoboxsweep.report import Report
from infoboxsweep.wikireport import (
    HEADINGS,
    MARKER,
    MAX_REVIEWS,
    MAX_ROWS,
    REVIEW_END,
    REVIEW_START,
    duration,
    mark_interrupted,
    review_lines,
    review_section,
    review_starting,
    run_id,
    run_row,
    updated_page,
)

START = datetime(2026, 11, 7, 4, 23, 5, 123456, tzinfo=UTC)


def report(**changes):
    r = Report(live=True, started=START)
    for name, value in changes.items():
        setattr(r, name, value)
    return r


def page(rows=(), review='No pages yet.'):
    return (f'Intro, by hand.\n\n== Runs ==\n{{| class="wikitable"\n{HEADINGS}\n{MARKER}\n'
            + ''.join(rows) + f'|}}\n\n== Needs manual review ==\n{REVIEW_START}\n{review}\n'
            f'{REVIEW_END}\nFooter.\n')


def test_rows():
    assert run_id(report()) == '20261107T042305.123456'
    assert run_row(report(), starting=True) == (
        '|- data-run="20261107T042305.123456"\n'
        '| 2026-11-07 04:23 || — || — || — || — || 0 || 0 || 0 || started\n')
    running = run_row(report(categories=412, found=38120, checked=1200),
                      now=START + timedelta(hours=1))
    assert running.endswith('|| 412 || 38,120 || 1,200 || 0 || 0 || running (last updated '
                            '2026-11-07 05:23)\n')
    done = run_row(report(categories=2, found=3, checked=3, finished=START + timedelta(minutes=5),
                          reviews=[('Talk:A', 'A', 'x')], errors=[('Talk:B', 'e'), ('C', 'f')]))
    assert done.endswith('| 2026-11-07 04:23 || 2026-11-07 04:28 || 5 min || 2 || 3 || 3 || 0 '
                         '|| [[#Needs manual review|3]] || finished (2 errors)\n')
    finished = START + timedelta(seconds=40)
    assert run_row(report(finished=finished, stopped='5 pages in a row failed')).endswith(
        '|| stopped: <nowiki>5 pages in a row failed</nowiki>\n')
    assert run_row(report(finished=finished, ended_early='3 edits (--max-edits)',
                          errors=[('x', 'y')])).endswith(
        '|| finished early: <nowiki>3 edits (--max-edits)</nowiki> (1 error)\n')
    assert run_row(report(finished=finished), result='aborted').endswith('|| aborted\n')


def test_a_new_page():
    text = updated_page(None, 'ROW\n', review=None, header='{{H}}', intro='Intro.')
    assert text == (f'{{{{H}}}}\nIntro.\n\n== Runs ==\n{{| class="wikitable"\n{HEADINGS}\n'
                    f'{MARKER}\nROW\n|}}\n\n== Needs manual review ==\n{REVIEW_START}\n'
                    f'No pages yet.\n{REVIEW_END}\n')
    # A page edited by hand, without the table, is started again.
    assert updated_page('Some text', 'ROW\n', review=None, header='{{H}}',
                        intro='Intro.') == text


def test_rows_go_at_the_top_and_replace_their_own():
    old = page(['|- data-run="a"\n| A\n', '|- data-run="b"\n| B\n'])
    text = updated_page(old, '|- data-run="c"\n| C\n', review=None, header='', intro='')
    assert text == page(['|- data-run="c"\n| C\n', '|- data-run="a"\n| A\n',
                         '|- data-run="b"\n| B\n'])
    text = updated_page(old, '|- data-run="b"\n| B2\n', review='New list.', header='', intro='')
    assert text == page(['|- data-run="a"\n| A\n', '|- data-run="b"\n| B2\n'], 'New list.')


def test_old_rows_go():
    old = page([f'|- data-run="{i}"\n| {i}\n' for i in range(MAX_ROWS)])
    text = updated_page(old, '|- data-run="new"\n| new\n', review=None, header='', intro='')
    assert text.count('data-run=') == MAX_ROWS
    assert f'data-run="{MAX_ROWS - 1}"' not in text and 'data-run="new"' in text


def test_a_page_without_the_review_section_gets_one():
    old = page().split('\n== Needs manual review')[0] + '\n'
    text = updated_page(old, '|- data-run="x"\n| X\n', review='List.', header='', intro='')
    assert text.endswith(f'|}}\n\n== Needs manual review ==\n{REVIEW_START}\nList.\n'
                         f'{REVIEW_END}\n')


def test_mark_interrupted():
    rows = ['|- data-run="old"\n| 2026-11-01 00:00 || — || 1 h || 1 || 1 || 1 || 0 || 0 '
            '|| running (last updated 2026-11-01 01:00)\n',
            '|- data-run="fresh"\n| 2026-11-07 03:00 || — || 1 h || 1 || 1 || 1 || 0 || 0 '
            '|| running (last updated 2026-11-07 04:00)\n',
            '|- data-run="never"\n| 2026-11-01 00:00 || — || — || — || — || 0 || 0 || 0 '
            '|| started\n',
            '|- data-run="young"\n| 2026-11-07 04:00 || — || — || — || — || 0 || 0 || 0 '
            '|| started\n',
            '|- data-run="mine"\n| 2026-11-01 00:00 || — || — || — || — || 0 || 0 || 0 '
            '|| started\n']
    text, marked = mark_interrupted(page(rows), run='mine', stale_before=START - timedelta(hours=2))
    assert marked == 2
    assert 'interrupted (last updated 2026-11-01 01:00)' in text
    assert 'running (last updated 2026-11-07 04:00)' in text
    assert text.count('interrupted (before its first progress report)') == 1
    assert text.count('|| started') == 2
    assert mark_interrupted(None, run='x', stale_before=START) == (None, 0)
    assert mark_interrupted('No table', run='x', stale_before=START) == ('No table', 0)


def test_review_section():
    when = START + timedelta(hours=1)
    found = {'Talk:B': ('B', 'the article <i>is</i> a redirect'), 'Category:X': ('', 'odd')}
    text = review_section(found=found, when=when, started=START)
    assert text == (
        'Updated 2026-11-07 05:23 (UTC), by the run that started 2026-11-07 04:23. 2 pages need '
        'manual review.\n{| class="wikitable sortable"\n! Page !! Article !! Why\n'
        '|-\n| [[:Category:X]] || — || <nowiki>odd</nowiki>\n'
        '|-\n| [[:Talk:B]] || [[B]] || <nowiki>the article &lt;i>is&lt;/i> a redirect</nowiki>\n'
        '|}')
    assert set(review_lines(page(review=text))) == {'Category:X', 'Talk:B'}
    one = review_section(found={'Talk:C': ('C', 'new')}, when=when, started=START, final=False)
    assert '1 page needs, so far, manual review.' in one
    none = review_section(found={}, when=when, started=START)
    assert none.endswith('No pages need manual review.')
    assert 'so far' in review_section(found={}, when=when, started=START, final=False)
    assert review_lines(None) == {} and review_lines('no markers') == {}
    assert review_starting(START) == (
        'The run that started 2026-11-07 04:23 (UTC) is going. The pages it leaves for manual '
        'review will be listed here as it finds them.')


def test_a_long_review_list_is_cut_short():
    found = {f'Talk:{i:05}': (f'{i}', 'x') for i in range(MAX_REVIEWS + 5)}
    text = review_section(found=found, when=START, started=START)
    assert text.count('|-\n') == MAX_REVIEWS
    assert f'{MAX_REVIEWS + 5:,} pages need manual review.' in text
    assert "the bot's local report has the rest" in text


ROW = '|- data-run="x"\n| X\n'


def section_count(text):
    return text.count('== Needs manual review ==')


def test_a_section_whose_markers_were_deleted_by_hand():
    # As on User:ZackBot/InfoboxReport: someone cleared the old list with a
    # section edit, markers and all.  The bot must use that section, not add
    # a second.
    old = page().replace(f'{REVIEW_START}\nNo pages yet.\n{REVIEW_END}\n', 'Cleared by hand.\n')
    assert REVIEW_START not in old and section_count(old) == 1
    text = updated_page(old, ROW, review='New list.', header='', intro='')
    assert section_count(text) == 1
    assert f'== Needs manual review ==\n{REVIEW_START}\nNew list.\n{REVIEW_END}\n' in text
    # Without its markers, the bot can't tell the old list from anything else
    # in the section, so the section is replaced up to the next heading.
    assert 'Cleared by hand.' not in text and 'Footer.' not in text


def test_duplicate_sections_are_merged_into_one():
    # A page that already has the duplicate, as the bug left it.
    old = page(review='Old list.') + (f'\n== Needs manual review ==\n{REVIEW_START}\n'
                                      f'Another old list.\n{REVIEW_END}\n')
    assert section_count(old) == 2
    text = updated_page(old, ROW, review='New list.', header='', intro='')
    assert section_count(text) == 1 and text.count(REVIEW_START) == 1
    assert 'New list.' in text and 'Old list.' not in text and 'Another old' not in text


def test_markers_without_their_heading():
    old = page().replace('== Needs manual review ==\n', '')
    text = updated_page(old, ROW, review='New list.', header='', intro='')
    assert section_count(text) == 1 and text.count(REVIEW_START) == 1
    assert f'== Needs manual review ==\n{REVIEW_START}\nNew list.' in text


def test_the_section_keeps_what_follows_it():
    old = page() + '\n== Notes ==\nKept.\n'
    text = updated_page(old, ROW, review='New list.', header='', intro='')
    assert text.endswith(f'{REVIEW_START}\nNew list.\n{REVIEW_END}\nFooter.\n\n== Notes ==\n'
                         'Kept.\n')


def test_duration():
    assert duration(timedelta(seconds=45)) == '45 s'
    assert duration(timedelta(minutes=12, seconds=5)) == '12 min'
    assert duration(timedelta(hours=1, minutes=38)) == '1 h 38 min'
    assert duration(timedelta(days=2, hours=3, minutes=1)) == '2 d 3 h'
