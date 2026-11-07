"""Command line entry point.

    infoboxsweep tree      walk the category tree and say what's in it: its
                        categories, how deep it goes, and how many distinct
                        pages it holds
    infoboxsweep run       a dry run over every page in the tree: reads the wiki,
                        saves nothing, and writes the edits it would make to a
                        report in out/
    infoboxsweep run --limit 50
                        the same, for the first 50 talk pages only
    infoboxsweep run --page "Talk:Joe Bloggs"
                        the same, for one page (an article's title works too)
    infoboxsweep run --live
                        edit for real (needs user-config.py and an approved bot account)
    infoboxsweep check "Joe Bloggs"
                        say whether an article has an infobox, and what the bot would
                        take off its talk page

Every run is a dry run unless --live is given.
"""

import argparse
import io
import logging
import os
import sys
from pathlib import Path
from typing import Any

from . import BRFA, ROOT_CATEGORY, __version__

log = logging.getLogger('infoboxsweep')

# Pywikibot's user_agent_format.  Pywikibot fills {script_comments} with the
# account's user page, such as "wikipedia:en; User:ZackBot", which is the
# contact Wikimedia's User-Agent policy asks for.
USER_AGENT = (f'InfoboxSweep/{__version__} ({{script_comments}}) {{pwb}} ({{revision}}) '
              '{http_backend} {python}')


def main(argv: list[str] | None = None) -> int:
    _never_crash_printing()
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(levelname)s %(message)s')
    if args.command == 'run' and args.live and not user_config_dir():
        parser.error('--live needs a user-config.py: see deploy/user-config.example.py')
    if args.command == 'run' and args.live and args.namespace:
        parser.error('--namespace is for dry runs only: the bot only edits talk pages of '
                     'articles')
    wiki = _connect(args)
    if args.command == 'tree':
        return _tree(args, wiki)
    if args.command == 'check':
        return _check(args, wiki)
    return _run(args, wiki)


def _never_crash_printing() -> None:
    """Show a replacement for characters some consoles can't show, instead
    of crashing."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            encoding = stream.encoding if stream.isatty() else 'utf-8'
            stream.reconfigure(encoding=encoding, errors='replace')


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='infoboxsweep', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Not from user-config.py: without a mylang there, Pywikibot quietly
    # picks test.wikipedia.
    parser.add_argument('--lang', default='en')
    parser.add_argument('--family', default='wikipedia')
    parser.add_argument('-v', '--verbose', action='store_true')
    sub = parser.add_subparsers(dest='command', required=True)

    tree = sub.add_parser('tree', help='walk the category tree, and say what is in it')
    _add_category(tree)
    tree.add_argument('--list', action='store_true',
                      help='also print every category, and every page, one to a line')

    run = sub.add_parser('run', help='remove infobox requests where the article has an '
                                     'infobox; a dry run unless --live is given')
    _add_category(run)
    run.add_argument('--live', action='store_true', help='edit for real')
    run.add_argument('--trial', action='store_true',
                     help='allow a live run without the bot flag, for approved BRFA trial '
                          'edits; edit summaries start with "BRFA trial"')
    run.add_argument('--page', action='append', default=[], metavar='TITLE',
                     help='only check this page (a talk page, or an article, for its talk '
                          'page), not the whole tree; repeatable')
    run.add_argument('--namespace', action='append', type=int, metavar='N',
                     help='check talk pages in this namespace (default: 1, talk pages of '
                          'articles); repeatable. Dry runs only')
    run.add_argument('--limit', type=int, default=0, metavar='N',
                     help='stop after checking this many talk pages (default: no limit)')
    run.add_argument('--max-edits', type=int, default=0, metavar='N',
                     help='stop after this many edits, such as for a BRFA trial '
                          '(default: no limit)')
    run.add_argument('--run-page', metavar='TITLE',
                     help='the page that must say "yes" for a live run (default: '
                          'User:<account>/Run)')
    run.add_argument('--report-page', metavar='TITLE',
                     help='where a live run keeps its row, and the pages for manual review '
                          '(default: User:<account>/InfoboxReport); "" for none')
    run.add_argument('--stop-file', type=Path, metavar='PATH',
                     help='stop cleanly, still reporting on the wiki, once this file exists '
                          '(deploy/runibox.sh gives each job one, for stopibox)')
    run.add_argument('--progress-minutes', type=int, default=30, metavar='N',
                     help='during a live run, update the report page every N minutes, on the '
                          'clock from midnight UTC (default: 30, on the hour and the half '
                          'hour); 0 for only at the start and the end')
    run.add_argument('--brfa', metavar='TITLE',
                     help=f'the bot approval linked from every edit summary (default: {BRFA}); '
                          '"" for none')
    run.add_argument('--summary-suffix', default='', metavar='TEXT',
                     help='added to the end of every edit summary')
    run.add_argument('--out-dir', type=Path, default=Path('out'),
                     help='where the report is written (default: out)')

    check = sub.add_parser('check', help='say whether an article has an infobox, and what the '
                                         'bot would take off its talk page; saves nothing')
    check.add_argument('title', help='the article, or its talk page')
    return parser


def _add_category(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--category', default=ROOT_CATEGORY, metavar='TITLE',
                        help=f'the root of the category tree (default: {ROOT_CATEGORY})')


def user_config_dir() -> Path | None:
    """Where Pywikibot will find user-config.py, or None if nowhere: in
    PYWIKIBOT_DIR, the current directory, or ~/.pywikibot."""
    candidates = [os.environ.get('PYWIKIBOT_DIR'), '.', '~/.pywikibot']
    for candidate in candidates:
        if candidate and (Path(candidate).expanduser() / 'user-config.py').is_file():
            return Path(candidate).expanduser().resolve()
    return None


def _connect(args: argparse.Namespace) -> Any:
    """The wiki, through Pywikibot.  A dry run needs no account, so without
    a user-config.py, Pywikibot is told to do without one."""
    if user_config_dir() is None:
        os.environ.setdefault('PYWIKIBOT_NO_USER_CONFIG', '2')
    import pywikibot

    from .wiki import Wiki
    pywikibot.config.user_agent_format = USER_AGENT
    return Wiki(pywikibot.Site(args.lang, args.family))


def _category_title(title: str) -> str:
    return title if title.lower().startswith('category:') else f'Category:{title}'


def _tree(args: argparse.Namespace, wiki: Any) -> int:
    from .tree import walk
    tree = walk(wiki, _category_title(args.category))
    print(f'{tree.root}: {len(tree.categories)} categories, {tree.depth} levels deep')
    print(f'{len(tree.pages)} distinct pages; {tree.duplicates} more listings of pages in '
          'more than one category')
    for category, parent in tree.not_followed:
        print(f'Not followed (no "infobox" in its name): {category}, in {parent}')
    if tree.truncated:
        print('The walk stopped part way: the tree has too many categories', file=sys.stderr)
    if args.list:
        print('\nCategories:')
        print('\n'.join(f'  {c}' for c in tree.categories))
        print('\nPages:')
        print('\n'.join(f'  {p}' for p in tree.pages))
    return 1 if tree.truncated else 0


def _check(args: argparse.Namespace, wiki: Any) -> int:
    from .bot import is_request_category
    from .infobox import INFOBOX_PAGES, verdict
    from .request import REQUEST_TEMPLATE, remove_requests
    page = wiki.page(args.title)
    talk = page if page.isTalkPage() else page.toggleTalkPage()
    article = talk.toggleTalkPage()
    name = article.title()
    if not article.exists() or article.isRedirectPage():
        print(f'{name}: ' + ('a redirect' if article.exists() else 'does not exist'))
        return 1
    found = verdict(article.text, wiki.transcluding([name], INFOBOX_PAGES).get(name, set()),
                    ignore=[REQUEST_TEMPLATE])
    print(f'{name}: ' + (f'has an infobox ({found.evidence})' if found.has_infobox else
                         found.review or 'no infobox'))
    if not talk.exists():
        print(f'{talk.title()}: does not exist')
        return 0
    names = [REQUEST_TEMPLATE] + wiki.redirects_to(REQUEST_TEMPLATE)
    removal = remove_requests(talk.text, names)
    print(f'{talk.title()}: ' + ('; '.join(removal.removed) or 'no infobox request found'))
    if removal.changed:
        left = sorted(c for c in wiki.categories_with(talk.title(), removal.text)
                      if is_request_category(c))
        print('After removing it: ' + (f'still in {", ".join(left)}' if left
                                       else 'in no infobox request category'))
    return 0


def _run(args: argparse.Namespace, wiki: Any) -> int:
    from .bot import Bot, Options
    options = Options(
        live=args.live, trial=args.trial, category=_category_title(args.category),
        namespaces=tuple(args.namespace or (1,)), pages=tuple(args.page), limit=args.limit,
        max_edits=args.max_edits, run_page=args.run_page, report_page=args.report_page,
        stop_file=args.stop_file, progress_minutes=args.progress_minutes,
        brfa=BRFA if args.brfa is None else args.brfa, summary_suffix=args.summary_suffix,
        out_dir=args.out_dir)
    bot = Bot(wiki, options)
    report = bot.run()
    verb = 'Changed' if report.live else 'Would change'
    print(f'Checked {report.checked} talk page(s): {report.with_infobox} article(s) with an '
          f'infobox, {report.without_infobox} without. {verb} {len(report.edits)}; '
          f'{len(report.reviews)} for manual review; {len(report.skipped)} skipped; '
          f'{len(report.errors)} error(s).')
    print(f'Report: {bot.report_path}')
    if report.stopped and not report.stopped_by_operator:
        print(f'Stopped: {report.stopped}', file=sys.stderr)
        return 2 if not report.checked else 1
    if report.stopped:
        print(f'Stopped, as asked: {report.stopped}')
    return 1 if report.errors else 0
