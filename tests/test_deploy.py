"""The Toolforge files in deploy/: runibox.sh, and the example jobs.yaml.

runibox.sh is run with bash, with a stand-in for the toolforge command that
records what it was asked; the job's command is then run as Toolforge
would, with a stand-in for the bot that records its arguments.
"""

import json
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
import yaml

from infoboxsweep import cli
from infoboxsweep.tasks import INFOBOX, PHOTO

DEPLOY = Path(__file__).parent.parent / 'deploy'
RUNIBOX = DEPLOY / 'runibox.sh'

needs_bash = pytest.mark.skipif(shutil.which('bash') is None, reason='needs bash')

STAND_IN = '''#!/usr/bin/env python3
import json, sys
with open({log!r}, 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
'''


@pytest.fixture
def toolforge(tmp_path):
    bin_dir, bot_dir = tmp_path / 'bin', tmp_path / "Zack's bot"
    (bot_dir / 'venv' / 'bin').mkdir(parents=True)
    bin_dir.mkdir()
    for path, log in [(bin_dir / 'toolforge', tmp_path / 'toolforge.log'),
                      (bot_dir / 'venv' / 'bin' / 'infoboxsweep', tmp_path / 'bot.log'),
                      (bot_dir / 'venv' / 'bin' / 'imagesweep', tmp_path / 'images.log')]:
        path.write_text(STAND_IN.format(log=str(log)))
        path.chmod(0o755)
    return tmp_path, bin_dir, bot_dir


def _env(toolforge, **extra):
    tmp_path, bin_dir, bot_dir = toolforge
    return {'PATH': f'{bin_dir}:/usr/bin:/bin', 'HOME': str(tmp_path),
            'INFOBOXSWEEP_DIR': str(bot_dir), **extra}


def bash(toolforge, function, *args, **env):
    script = f'source {shlex.quote(str(RUNIBOX))}; {function} "$@"'
    return subprocess.run(['bash', '-c', script, function, *args], env=_env(toolforge, **env),
                          capture_output=True, text=True)


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@needs_bash
@pytest.mark.parametrize(('function', 'log'), [('runibox', 'bot.log'),
                                               ('runimages', 'images.log')])
def test_each_task_has_its_command(toolforge, function, log):
    tmp_path, _, _ = toolforge
    assert bash(toolforge, function, '--dry-run').returncode == 0
    [call] = _read(tmp_path / 'toolforge.log')
    name = {'runibox': 'dry-ibox', 'runimages': 'dry-images'}[function]
    assert call[:3] == ['jobs', 'run', name]
    subprocess.run(['sh', '-c', call[call.index('--command') + 1]], check=True)
    assert _read(tmp_path / log) == [['run', '--stop-file', f'stop/{name}']]


@needs_bash
@pytest.mark.parametrize(('args', 'name', 'bot_args'), [
    ((), 'ibox', ['run', '--live', '--stop-file', 'stop/ibox']),
    (('--max-edits', '10'), 'ibox',
     ['run', '--live', '--stop-file', 'stop/ibox', '--max-edits', '10']),
    (('--dry-run', '--limit', '50', '--summary-suffix', "it's done"), 'dry-ibox',
     ['run', '--stop-file', 'stop/dry-ibox', '--limit', '50', '--summary-suffix', "it's done"]),
])
def test_runibox(toolforge, args, name, bot_args):
    tmp_path, _, bot_dir = toolforge
    done = bash(toolforge, 'runibox', *args)
    assert done.returncode == 0, done.stderr
    [call] = _read(tmp_path / 'toolforge.log')
    assert call[:3] == ['jobs', 'run', name]
    assert call[call.index('--image') + 1] == 'python3.13'
    command = call[call.index('--command') + 1]
    # Run the job's command as Toolforge would, with the stand-in bot.
    subprocess.run(['sh', '-c', command], check=True)
    [ran] = _read(tmp_path / 'bot.log')
    assert ran == bot_args
    cli._build_parser().parse_args(ran)   # one the bot understands


@needs_bash
def test_stopibox(toolforge):
    tmp_path, _, bot_dir = toolforge
    stop = bot_dir / 'stop' / 'ibox'

    def bot_stops():
        for _ in range(100):
            if stop.exists():
                stop.unlink()
                return
            time.sleep(0.05)
    thread = threading.Thread(target=bot_stops)
    thread.start()
    done = bash(toolforge, 'stopibox')
    thread.join()
    assert done.returncode == 0 and 'ibox has stopped' in done.stdout


@needs_bash
def test_stopibox_gives_up(toolforge):
    _, _, bot_dir = toolforge
    done = bash(toolforge, 'stopibox', '--dry-run', INFOBOXSWEEP_STOP_WAIT='0')
    assert done.returncode == 1 and "dry-ibox hasn't stopped" in done.stderr
    assert not (bot_dir / 'stop' / 'dry-ibox').exists()
    done = bash(toolforge, 'stopimages', INFOBOXSWEEP_STOP_WAIT='0')
    assert done.returncode == 1 and "images hasn't stopped" in done.stderr
    done = bash(toolforge, 'stopimages', 'extra')
    assert done.returncode == 2 and 'usage: stopimages' in done.stderr


def test_jobs_example():
    jobs = yaml.safe_load((DEPLOY / 'jobs.example.yaml').read_text())
    assert jobs
    for job in jobs:
        assert job['image'] == 'python3.13' and job['emails'] == 'onfailure'
        cd, run = job['command'].split(' && ')
        assert cd == 'cd ~/InfoboxSweep'
        program, *args = shlex.split(run)
        task = {'venv/bin/infoboxsweep': INFOBOX, 'venv/bin/imagesweep': PHOTO}[program]
        cli._build_parser(task).parse_args(args)
        assert f'stop/{job["name"]}' in args
