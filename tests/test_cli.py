"""The command line, with the fake wiki in place of the real one."""

import subprocess
import sys

import pytest

from infoboxsweep import ROOT_CATEGORY, cli
from tests.fakes import (
    FILM_CATEGORY,
    FILM_TALK,
    INFOBOX_ARTICLE,
    FakePage,
    FakeWiki,
    SaveError,
)


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    wiki = FakeWiki()
    wiki.tree(ROOT_CATEGORY, subcats=[FILM_CATEGORY, 'Category:Films'])
    wiki.request('Example', INFOBOX_ARTICLE, FILM_TALK, category=FILM_CATEGORY)
    wiki.tree(ROOT_CATEGORY, pages=['Talk:Example'])
    monkeypatch.setattr(cli, '_connect', lambda args: wiki)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PYWIKIBOT_DIR', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    return wiki


def test_tree(wiki, capsys):
    assert cli.main(['tree', '--list']) == 0
    out = capsys.readouterr().out
    assert f'{ROOT_CATEGORY}: 2 categories, 1 levels deep' in out
    assert '1 distinct pages; 1 more listings' in out
    assert f'Not followed (no "infobox" in its name): Category:Films, in {ROOT_CATEGORY}' in out
    assert '  Talk:Example' in out and f'  {FILM_CATEGORY}' in out


def test_tree_too_big(wiki, capsys, monkeypatch):
    from infoboxsweep import tree
    real = tree.walk
    monkeypatch.setattr(tree, 'walk', lambda w, root, **kw: real(w, root, max_categories=1,
                                                                   **kw))
    assert cli.main(['tree', '--category', 'Wikipedia articles with an infobox request']) == 1
    assert 'stopped part way' in capsys.readouterr().err


def test_dry_run(wiki, capsys, tmp_path):
    assert cli.main(['run']) == 0
    out = capsys.readouterr().out
    assert ('Checked 1 talk page(s): 1 article(s) with an infobox, 0 without. Would change 1; '
            '1 for manual review; 0 skipped; 0 error(s).') in out
    assert 'Report: out/dry-run-' in out
    assert wiki.saves == []


def test_live_run(wiki, capsys, tmp_path):
    (tmp_path / 'user-config.py').write_text('')
    assert cli.main(['run', '--live', '--progress-minutes', '0', '--brfa', '']) == 0
    assert 'Changed 1' in capsys.readouterr().out
    assert wiki.page('Talk:Example').summaries == [
        'Removing infobox request (needs-infobox=yes from {{WikiProject Film}}): [[Example]] '
        'has an infobox']


def test_live_needs_a_user_config(wiki, capsys):
    with pytest.raises(SystemExit):
        cli.main(['run', '--live'])
    assert '--live needs a user-config.py' in capsys.readouterr().err


def test_live_is_for_talk_pages_of_articles(wiki, capsys, tmp_path):
    (tmp_path / 'user-config.py').write_text('')
    with pytest.raises(SystemExit):
        cli.main(['run', '--live', '--namespace', '119'])
    assert '--namespace is for dry runs only' in capsys.readouterr().err


def test_exit_codes(wiki, capsys, tmp_path):
    (tmp_path / 'user-config.py').write_text('')
    wiki.run_page.text = 'no'
    assert cli.main(['run', '--live']) == 2   # refused to start
    assert 'Stopped: User:ExampleBot/Run does not say "yes"' in capsys.readouterr().err
    wiki.run_page.text = 'yes'
    wiki.page('Talk:Example')._save_errors = [SaveError('x')]
    assert cli.main(['run', '--live', '--progress-minutes', '0']) == 1   # an error
    wiki.page('Talk:Example')._save_errors = [SaveError(str(i)) for i in range(5)]
    for i in range(4):
        wiki.request(f'Film {i}', INFOBOX_ARTICLE, FILM_TALK, save_errors=[SaveError('x')])
    assert cli.main(['run', '--live', '--progress-minutes', '0']) == 1   # stopped part way


def test_stopped_as_asked(wiki, capsys, tmp_path):
    stop = tmp_path / 'stop'
    original = wiki.category_pages

    def pages(category):
        stop.write_text('')
        return original(category)
    wiki.category_pages = pages
    assert cli.main(['run', '--stop-file', str(stop)]) == 0
    assert 'Stopped, as asked: manually stopped by the bot operator' in capsys.readouterr().out


def test_check(wiki, capsys):
    assert cli.main(['check', 'Example']) == 0
    out = capsys.readouterr().out
    assert out == ('Example: has an infobox (transcludes Template:Infobox)\n'
                   'Talk:Example: needs-infobox=yes from {{WikiProject Film}}\n'
                   'After removing it: in no infobox request category\n')
    wiki.sticky['Talk:Example'] = {FILM_CATEGORY}
    assert cli.main(['check', 'Talk:Example']) == 0
    assert f'After removing it: still in {FILM_CATEGORY}' in capsys.readouterr().out


def test_check_other_cases(wiki, capsys):
    wiki.add(FakePage('Lonely', "'''Lonely'''"), FakePage('Talk:Quiet', '{{WikiProject Film}}'),
             FakePage('Quiet', "'''Quiet'''"), FakePage('Moved', '#REDIRECT', redirect=True))
    assert cli.main(['check', 'Lonely']) == 0
    assert capsys.readouterr().out == 'Lonely: no infobox\nTalk:Lonely: does not exist\n'
    assert cli.main(['check', 'Quiet']) == 0
    assert capsys.readouterr().out == 'Quiet: no infobox\nTalk:Quiet: no infobox request found\n'
    assert cli.main(['check', 'Moved']) == 1
    assert capsys.readouterr().out == 'Moved: a redirect\n'
    assert cli.main(['check', 'Talk:Nothing']) == 1
    assert capsys.readouterr().out == 'Nothing: does not exist\n'


def test_user_config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('PYWIKIBOT_DIR', str(tmp_path / 'pwb'))
    assert cli.user_config_dir() is None
    (tmp_path / 'pwb').mkdir()
    (tmp_path / 'pwb' / 'user-config.py').write_text('')
    assert cli.user_config_dir() == (tmp_path / 'pwb').resolve()


def test_connect(monkeypatch, tmp_path):
    import pywikibot
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('PYWIKIBOT_DIR', raising=False)
    made = []
    monkeypatch.setattr(pywikibot, 'Site', lambda lang, family: made.append((lang, family)))
    wiki = cli._connect(cli._build_parser().parse_args(['--lang', 'de', 'tree']))
    assert made == [('de', 'wikipedia')] and wiki.site is None
    assert pywikibot.config.user_agent_format.startswith('InfoboxSweep/')


def test_python_dash_m():
    done = subprocess.run([sys.executable, '-m', 'infoboxsweep', '--help'], capture_output=True,
                          text=True)
    assert done.returncode == 0 and 'run --live' in done.stdout
    assert done.stdout.startswith('usage: infoboxsweep')


@pytest.fixture
def photo_wiki(monkeypatch, tmp_path):
    from tests.test_bot_photo import photo_wiki
    wiki = photo_wiki()
    monkeypatch.setattr(cli, '_connect', lambda args: wiki)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PYWIKIBOT_DIR', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    return wiki


def test_imagesweep_tree(photo_wiki, capsys):
    assert cli.images_main(['tree']) == 0
    out = capsys.readouterr().out
    assert 'Category:Wikipedia requested photographs: 3 categories, 1 levels deep' in out
    assert ('Not followed (no "photograph" or "photo" or "image" or "picture" in its name): '
            'Category:Ohio') in out


def test_imagesweep_run(photo_wiki, capsys, tmp_path):
    (tmp_path / 'user-config.py').write_text('')
    assert cli.images_main(['run', '--live', '--progress-minutes', '0']) == 0
    assert ('Checked 7 talk page(s): 3 article(s) with a photograph, 3 without. Changed 2; '
            '3 for manual review') in capsys.readouterr().out
    assert photo_wiki.page('User:ExampleBot/ImageReport').saved


def test_imagesweep_check(photo_wiki, capsys):
    assert cli.images_main(['check', 'Statehouse']) == 0
    assert capsys.readouterr().out == (
        'Statehouse: has a photograph (lead image [[:File:Ohio Statehouse.jpg]] (JPEG, '
        '3000×2000))\nTalk:Statehouse: {{Image requested}}\n'
        'After removing it: in no photograph request category\n')
    assert cli.images_main(['check', 'Flagged']) == 0
    assert capsys.readouterr().out.startswith(
        'Flagged: no photograph (the lead image, [[:File:Flag of Ohio.svg]], is not a '
        'photograph: its name has "flag")\n')
    assert cli.images_main(['check', 'Logo PNG']) == 0
    assert 'Logo PNG: for a human: the lead image' in capsys.readouterr().out
    assert cli.images_main(['check', 'Interior']) == 0
    assert ('Talk:Interior: for a human: {{Image requested}} asks for something particular: '
            'the dome inside\nTalk:Interior: no photograph request found\n'
            ) in capsys.readouterr().out
    assert cli.images_main(['check', 'Pending']) == 0
    assert capsys.readouterr().out.startswith('Pending: no photograph (no lead image)\n')


def test_imagesweep_help():
    done = subprocess.run([sys.executable, '-c', 'import sys; from infoboxsweep.cli import '
                           'images_main; sys.exit(images_main(["--help"]))'],
                          capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.startswith('usage: imagesweep')
    assert 'removing photograph requests' in done.stdout
