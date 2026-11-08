"""The local text report."""

from datetime import UTC, datetime

from infoboxsweep.report import Edit, Report, unified_diff


def test_report(tmp_path):
    report = Report(live=False, started=datetime(2026, 11, 7, 12, 0, 1, tzinfo=UTC),
                    root='Category:R', finished=datetime(2026, 11, 7, 12, 5, tzinfo=UTC),
                    account='ExampleBot', source='every page in the tree', categories=3,
                    found=10, duplicates=2, depth=2, checked=9, fulfilled=4,
                    unfulfilled=3, not_followed=[('Category:Films', 'Category:R')],
                    wiki_report='saved', ended_early='checked 9 pages (--limit)',
                    stopped='5 pages in a row failed')
    report.edits.append(Edit('Talk:A', 'A', ['{{Infobox requested}}'], 'Summary',
                             unified_diff('Talk:A', 'x\n{{Infobox requested}}', 'x'),
                             'transcludes Template:Infobox'))
    report.review('Talk:B', 'B', 'odd')
    report.skip('Talk:C', 'nobots')
    report.errors.append(('Talk:D', 'SaveError: x'))
    path = report.write(tmp_path / 'out')
    assert path.name == 'dry-run-infobox-20261107-120001.txt'
    text = path.read_text()
    for line in ['DRY RUN: nothing was saved', 'Account:  ExampleBot',
                 'Category tree: 3 categories, 2 levels below Category:R; 10 distinct pages '
                 '(2 more listings', 'Would change:         1', 'Need manual review:   1',
                 '* Category:Films (in Category:R)', '* Talk:B (B): odd', '* Talk:C: nobots',
                 '* Talk:D: SaveError: x', 'Report on the wiki: saved',
                 'Finished early, as asked: checked 9 pages (--limit)',
                 'STOPPED: 5 pages in a row failed', '### Talk:A',
                 'Article: A (transcludes Template:Infobox)', '  - {{Infobox requested}}',
                 '-{{Infobox requested}}']:
        assert line in text, line


def test_a_live_report(tmp_path):
    report = Report(live=True, started=datetime(2026, 11, 7, tzinfo=UTC))
    text = report.text()
    assert 'LIVE RUN' in text and 'Changed:' in text and 'Category tree' not in text
    assert report.write(tmp_path).name.startswith('live-')
