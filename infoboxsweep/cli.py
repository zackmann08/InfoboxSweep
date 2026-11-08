"""Command line entry points: one command for each task.

    infoboxsweep ...    infobox requests (Category:Wikipedia articles with an
                        infobox request), reported on User:ZackBot/InfoboxReport
    imagesweep ...      photograph requests (Category:Wikipedia requested
                        photographs), reported on User:ZackBot/ImageReport

Both take the same commands:

    tree                walk the category tree and say what's in it: its
                        categories, how deep it goes, and how many distinct
                        pages it holds
    run                 a dry run over every page in the tree: reads the wiki,
                        saves nothing, and writes the edits it would make to a
                        report in out/
    run --limit 50      the same, for the first 50 talk pages only
    run --page "Talk:Joe Bloggs"
                        the same, for one page (an article's title works too)
    run --live          edit for real (needs user-config.py and an approved bot account)
    check "Joe Bloggs"  say whether an article has what was asked for, and what the
                        bot would take off its talk page

Every run is a dry run unless --live is given.
"""

import argparse
import io
import logging
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .tasks import INFOBOX, PHOTO, Task

log = logging.getLogger('infoboxsweep')

# Pywikibot's user_agent_format.  Pywikibot fills {script_comments} with the
# account's user page, such as "wikipedia:en; User:ZackBot", which is the
# contact Wikimedia's User-Agent policy asks for.
USER_AGENT = (f'InfoboxSweep/{__version__} ({{script_comments}}) {{pwb}} ({{revision}}) '
              '{http_backend} {python}')


def main(argv: list[str] | None = None, task: Task = INFOBOX) -> int:
    """infoboxsweep, or with task, the command for it."""
    _never_crash_printing()
    parser = _build_parser(task)
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
        return _tree(args, wiki, task)
    if args.command == 'check':
        return _check(args, wiki, task)
    return _run(args, wiki, task)


def images_main(argv: list[str] | None = None) -> int:
    """imagesweep: photograph requests."""
    return main(argv, PHOTO)


def _never_crash_printing() -> None:
    """Show a replacement for characters some consoles can't show, instead
    of crashing."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            encoding = stream.encoding if stream.isatty() else 'utf-8'
            stream.reconfigure(encoding=encoding, errors='replace')


def _build_parser(task: Task = INFOBOX) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=task.name, description=f'{task.name}: {task.doing}.\n\n{__doc__}',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # Not from user-config.py: without a mylang there, Pywikibot quietly
    # picks test.wikipedia.
    parser.add_argument('--lang', default='en')
    parser.add_argument('--family', default='wikipedia')
    parser.add_argument('-v', '--verbose', action='store_true')
    sub = parser.add_subparsers(dest='command', required=True)

    tree = sub.add_parser('tree', help='walk the category tree, and say what is in it')
    _add_category(tree, task)
    tree.add_argument('--list', action='store_true',
                      help='also print every category, and every page, one to a line')

    run = sub.add_parser('run', help=f'remove {task.request}s where the article has '
                                     f'{task.thing}; a dry run unless --live is given')
    _add_category(run, task)
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
                          f'(default: User:<account>/{task.report}); "" for none')
    run.add_argument('--stop-file', type=Path, metavar='PATH',
                     help='stop cleanly, still reporting on the wiki, once this file exists '
                          '(deploy/runibox.sh gives each job one)')
    run.add_argument('--progress-minutes', type=int, default=30, metavar='N',
                     help='during a live run, update the report page every N minutes, on the '
                          'clock from midnight UTC (default: 30, on the hour and the half '
                          'hour); 0 for only at the start and the end')
    run.add_argument('--brfa', metavar='TITLE',
                     help=f'the bot approval linked from every edit summary (default: '
                          f'{task.brfa}); "" for none')
    run.add_argument('--summary-suffix', default='', metavar='TEXT',
                     help='added to the end of every edit summary')
    run.add_argument('--out-dir', type=Path, default=Path('out'),
                     help='where the report is written (default: out)')

    check = sub.add_parser('check', help=f'say whether an article has {task.thing}, and what '
                                         'the bot would take off its talk page; saves nothing')
    check.add_argument('title', help='the article, or its talk page')
    return parser


def _add_category(parser: argparse.ArgumentParser, task: Task) -> None:
    parser.add_argument('--category', default=task.root, metavar='TITLE',
                        help=f'the root of the category tree (default: {task.root})')


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


def _tree(args: argparse.Namespace, wiki: Any, task: Task) -> int:
    from .tree import walk
    tree = walk(wiki, _category_title(args.category), follow=task.follows)
    print(f'{tree.root}: {len(tree.categories)} categories, {tree.depth} levels deep')
    print(f'{len(tree.pages)} distinct pages; {tree.duplicates} more listings of pages in '
          'more than one category')
    for category, parent in tree.not_followed:
        print(f'Not followed (no {task.keyword_text()} in its name): {category}, in {parent}')
    if tree.truncated:
        print('The walk stopped part way: the tree has too many categories', file=sys.stderr)
    if args.list:
        print('\nCategories:')
        print('\n'.join(f'  {c}' for c in tree.categories))
        print('\nPages:')
        print('\n'.join(f'  {p}' for p in tree.pages))
    return 1 if tree.truncated else 0


def _check(args: argparse.Namespace, wiki: Any, task: Task) -> int:
    from .request import remove_requests
    page = wiki.page(args.title)
    talk = page if page.isTalkPage() else page.toggleTalkPage()
    article = talk.toggleTalkPage()
    name = article.title()
    if not article.exists() or article.isRedirectPage():
        print(f'{name}: ' + ('a redirect' if article.exists() else 'does not exist'))
        return 1
    names = [task.request_template] + wiki.redirects_to(task.request_template)
    found = task.check(wiki, [article], names)[name]
    print(f'{name}: ' + (f'has {task.thing} ({found.evidence})' if found.found else
                         f'for a human: {found.review}' if found.review else
                         f'no {task.thing.split()[-1]}'
                         + (f' ({found.evidence})' if found.evidence else '')))
    if not talk.exists():
        print(f'{talk.title()}: does not exist')
        return 0
    removal = remove_requests(talk.text, names, params=task.request_params,
                              template_params=task.template_params, details=task.details)
    for particular in removal.specific:
        print(f'{talk.title()}: for a human: {particular}')
    print(f'{talk.title()}: ' + ('; '.join(removal.removed) or f'no {task.request} found'))
    if removal.changed:
        left = sorted(c for c in wiki.categories_with(talk.title(), removal.text)
                      if task.is_request_category(c))
        print('After removing it: ' + (f'still in {", ".join(left)}' if left
                                       else f'in no {task.request} category'))
    return 0


def _run(args: argparse.Namespace, wiki: Any, task: Task) -> int:
    from .bot import Bot, Options
    options = Options(
        task=task, live=args.live, trial=args.trial, category=_category_title(args.category),
        namespaces=tuple(args.namespace or (1,)), pages=tuple(args.page), limit=args.limit,
        max_edits=args.max_edits, run_page=args.run_page, report_page=args.report_page,
        stop_file=args.stop_file, progress_minutes=args.progress_minutes, brfa=args.brfa,
        summary_suffix=args.summary_suffix, out_dir=args.out_dir)
    bot = Bot(wiki, options)
    report = bot.run()
    verb = 'Changed' if report.live else 'Would change'
    print(f'Checked {report.checked} talk page(s): {report.fulfilled} article(s) with '
          f'{task.thing}, {report.unfulfilled} without. {verb} {len(report.edits)}; '
          f'{len(report.reviews)} for manual review; {len(report.skipped)} skipped; '
          f'{len(report.errors)} error(s).')
    print(f'Report: {bot.report_path}')
    if report.stopped and not report.stopped_by_operator:
        print(f'Stopped: {report.stopped}', file=sys.stderr)
        return 2 if not report.checked else 1
    if report.stopped:
        print(f'Stopped, as asked: {report.stopped}')
    return 1 if report.errors else 0
