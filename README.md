# InfoboxSweep

A Wikipedia bot that removes stale infobox requests. It goes through every
talk page in
[Category:Wikipedia articles with an infobox request](https://en.wikipedia.org/wiki/Category:Wikipedia_articles_with_an_infobox_request)
and all its subcategories, however deep. For each one it checks the article
the talk page belongs to. If the article already has an infobox, it takes the
request off the talk page:

```diff
 {{WikiProject banner shell|class=Start|
-{{WikiProject Film|needs-infobox=yes}}
+{{WikiProject Film}}
 }}
```

**Every run is a dry run unless you add `--live`.** A dry run reads
Wikipedia, saves nothing, and writes every edit it would have made to a text
report in `out/`.

## Quick start

Needs Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# What's in the category tree?
infoboxsweep tree

# One article: does it have an infobox, and what would come off its talk page?
infoboxsweep check "Joe Bloggs"

# Dry run over the first 200 talk pages: nothing is saved
infoboxsweep run --limit 200

# Dry run over the whole tree
infoboxsweep run
```

Set up `user-config.py` (see [Going live](#going-live)) even for dry runs:
then the User-Agent names `User:ZackBot`, as Wikimedia's
[User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)
asks. Without one, a dry run still works, but anonymously, and Wikimedia
rate-limits anonymous requests much more strictly.

## What a run does

### 1. Walk the category tree

The bot reads the root category, then each of its subcategories, then
theirs, all the way down, and lists every page in any of them **once**:

- **De-duplication.** A talk page in several categories (say, both a film
  and a biography category) is checked once. The report says how many
  repeat listings were dropped.
- **Loops.** Each category is read once, however many parents it has, so a
  category that is (through others) its own subcategory can't make the walk
  go round for ever.
- **Stray categories.** Only subcategories with "infobox" in their name are
  followed. Every real one has it ("Film articles needing infoboxes",
  "Wikipedia requested infoboxes in …"). One without it was most likely put
  in the tree by mistake, and could lead the bot into thousands of pages that
  never asked for an infobox, so it isn't followed and is listed for manual
  review instead.
- **A ceiling.** The walk stops at 10,000 categories, far more than the tree
  has, and says so as an error.

`infoboxsweep tree` does only this, and prints what it found; `--list` prints
every category and page too.

### 2. Check the article

Category members are talk pages. For each, the bot checks the article it
belongs to (`Talk:Foo` → `Foo`), not the talk page. The article **has an
infobox** if it transcludes
[Template:Infobox](https://en.wikipedia.org/wiki/Template:Infobox) or
[Module:Infobox](https://en.wikipedia.org/wiki/Module:Infobox), which nearly
every infobox is built on, or one of the taxobox and chembox templates, which
are built their own way (`INFOBOX_PAGES` in
[`infoboxsweep/infobox.py`](infoboxsweep/infobox.py)). That counts infoboxes
however they get there, such as through a wrapper template, and never
counts one that's only in a comment. It's what MediaWiki actually rendered,
asked of the API 50 articles at a time.

### 3. Take the request off the talk page

A talk page asks for an infobox in one of three ways, and the bot removes
each it finds:

| On the talk page | What the bot does |
|---|---|
| A WikiProject banner's parameter: `needs-infobox=yes`, or `needs_infobox`, `infobox`, `infobox-needed`, … (`REQUEST_PARAMS` in [`infoboxsweep/request.py`](infoboxsweep/request.py)) with any value that means yes (`yes`, `y`, `true`, `1`, …) | removes the parameter, leaving the rest of the banner as it was |
| `{{Infobox requested}}`, or any of its redirects (read from the wiki) | removes the call, and its line if nothing else was on it |
| The category itself, added by hand: `[[Category:Wikipedia articles with an infobox request]]` or any category in the tree | removes the link |

A parameter saying `no`, or left empty, asks for nothing, and is left alone.

### 4. Check the result with MediaWiki, then save

Before saving, the bot has MediaWiki parse the talk page as it would be
after the edit (`action=parse`, which saves nothing), and checks which
categories it would be in. If it would **still** be in a request category,
the request comes some way the bot doesn't know about, so the bot leaves the
page alone and lists it for manual review. Dry runs do this check too.

Edit summaries say what was removed and why, and link the bot's approval:

```wikitext
Removing infobox request (needs-infobox=yes from {{WikiProject Film}}): [[Example]] has an infobox ([[Wikipedia:Bots/Requests for approval/ZackBot 15|ZackBot 15]])
```

### Pages for manual review

The bot never guesses. These are listed for a human, on the report page and
in the local report:

- the article doesn't exist, or is a redirect;
- the article calls a template named `Infobox …` but doesn't transclude
  Template:Infobox or Module:Infobox (the template may be broken or missing);
- the article has an infobox, but the bot couldn't find the request on the
  talk page, which is still in a request category;
- after the bot's change the talk page would still be in a request category;
- the page in the category isn't a talk page (the request is on the article
  itself, where the bot doesn't edit);
- a subcategory without "infobox" in its name (not followed);
- any error, such as a failed save.

These are only **skipped**, and listed in the local report:

- the talk page is gone, or is a redirect;
- the talk page excludes the bot with `{{bots}}` or `{{nobots}}`;
- the talk page no longer asks for an infobox (it was fixed after the
  category was listed: MediaWiki updates category listings a little after an
  edit).

Articles **without** an infobox are just counted: their request still
stands.

## The report page on Wikipedia

Every live run keeps a row about itself on
[User:ZackBot/InfoboxReport](https://en.wikipedia.org/wiki/User:ZackBot/InfoboxReport),
or `--report-page`. The page has two sections:

```wikitext
{{User:ZackBot/Header}}
Runs of [[User:ZackBot|ZackBot]]'s task removing infobox requests ...

== Runs ==
{| class="wikitable"
! Started (UTC) !! Finished (UTC) !! Duration !! Categories !! Talk pages found !! Checked !! Changed !! Manual review !! Result
<!-- InfoboxSweep: new runs go below this line -->
|- data-run="20261111T051702.104322"
| 2026-11-11 05:17 || — || — || — || — || 0 || 0 || 0 || started
|- data-run="20261104T051701.551920"
| 2026-11-04 05:17 || 2026-11-04 09:41 || 4 h 24 min || 412 || 38,120 || 38,120 || 2,904 || [[#Needs manual review|17]] || finished (1 error)
|}

== Needs manual review ==
<!-- InfoboxSweep review start -->
Updated 2026-11-04 09:41 (UTC), by the run that started 2026-11-04 05:17. 17 pages need manual review.
{| class="wikitable sortable"
! Page !! Article !! Why
|-
| [[:Talk:Joe Bloggs]] || [[Joe Bloggs]] || <nowiki>the article does not exist</nowiki>
...
|}
<!-- InfoboxSweep review end -->
```

- **When it's updated.** The run adds its row as soon as it starts (with its
  start time, saying "started"), updates it once the tree is walked (with the
  categories and talk pages found), every half hour as it goes (on the hour
  and the half hour, or `--progress-minutes N`; `0` for none), and gives the
  final numbers when it ends: when it finished, how long it took, how many
  talk pages it checked and how many it changed, how many need manual review,
  and how it ended (finished, finished early as asked, stopped, and why),
  with the number of errors.
- **The review list.** A run that went through every page replaces the
  list. One that didn't (`--page`, `--limit`, `--max-edits`, or stopped part
  way), and every progress report, changes only the pages it looked at, so
  the others stay listed. At most 2,000 are shown; the local report has them
  all. Errors are listed with the pages for review.
- **Rows.** Each row's hidden `data-run` says which run it is, so a run
  updates its own. New runs go at the top. The table keeps the 100 newest.
- **Runs that died.** A run whose job was killed can't finish its row, which
  goes on saying "running". When the next run starts, it marks rows that
  haven't been updated for two hours as "interrupted".
- **Editing by hand.** Everything above the
  `<!-- InfoboxSweep: new runs go below this line -->` line, below the table,
  and outside the review markers is kept as it is. If the line or the table
  is gone, the bot starts the page again.
- **Failures.** If the page can't be saved at the end of a run, that's an
  error in the local report, and the run exits with 1. An edit conflict is
  tried again.
- **Dry runs** never edit it.

A bot password with only the *Edit existing pages* grant can't create pages,
so create `User:ZackBot/InfoboxReport` (with any text) before the first live
run.

## Safeguards

- **Dry run by default.** Nothing is saved without `--live`.
- **Talk pages of articles only.** A live run edits only namespace 1.
  `--namespace` (such as `119` for Draft talk) is for dry runs only.
- **Checked with MediaWiki before every save** (see above).
- **Respects `{{bots}}` and `{{nobots}}`.**
- **Emergency stop.** A live run checks
  [User:ZackBot/Run](https://en.wikipedia.org/wiki/User:ZackBot/Run), or
  `--run-page`, before it starts, before every edit and with every progress
  report. If it doesn't say `yes`, the run stops, and its only edit after
  that is to its own row, saying when the Run page was changed and by whom.
  It's the same page DeprecBot uses, so one edit stops both.
- **Bot flag.** A live run refuses to start unless the account has the `bot`
  right. `--trial` allows approved trial edits without it, and starts each
  edit summary with "BRFA trial".
- **Rate limits.** Edits are at least `put_throttle` seconds apart (10, in
  the example `user-config.py`). Pywikibot waits whenever Wikipedia's servers
  are lagged or Wikipedia rate-limits the bot.
- **Errors.** An error on one page is logged and reported, and the run
  carries on. The run stops after five failures in a row, or at the first
  error every save would hit (the bot blocked, the wiki read-only).
- **Stopping cleanly.** `--stop-file PATH` or SIGTERM (`toolforge jobs
  delete`) stops the run after its current batch, still reporting on the
  wiki ("manually stopped by the bot operator").
- **Starting again** needs no checkpoint: talk pages the bot fixed leave the
  category, so a new run finds only the rest.

## Going live

The task needs its own approval at
[Wikipedia:Bots/Requests for approval](https://en.wikipedia.org/wiki/Wikipedia:Bots/Requests_for_approval).
The edit summaries link `Wikipedia:Bots/Requests for approval/ZackBot 15`:
change `BRFA` in [`infoboxsweep/__init__.py`](infoboxsweep/__init__.py) to the
request's real name once it's filed, or pass `--brfa`.

1. At [Special:BotPasswords](https://en.wikipedia.org/wiki/Special:BotPasswords),
   logged in as ZackBot, make a bot password named `infoboxsweep` with the
   *High-volume (bot) access* and *Edit existing pages* grants.
2. Copy [`deploy/user-config.example.py`](deploy/user-config.example.py) to
   `user-config.py`, and put the bot password in `user-password.py`, as the
   example describes. Both files are git-ignored.
3. Make sure [User:ZackBot/Run](https://en.wikipedia.org/wiki/User:ZackBot/Run)
   says `yes`, and create
   [User:ZackBot/InfoboxReport](https://en.wikipedia.org/wiki/User:ZackBot/InfoboxReport)
   with any text.
4. Do a dry run, and check its report in `out/`:

   ```bash
   infoboxsweep run --limit 500
   ```

5. Run it for real, a few edits at first:

   ```bash
   infoboxsweep run --live --trial --max-edits 50     # a BRFA trial
   infoboxsweep run --live                            # once approved
   ```

## Running on Toolforge

Set up as for ZackBotPy (see its README), with the checkout at
`~/InfoboxSweep` (`/data/project/zackbot/InfoboxSweep`):

```bash
ssh <your-shell-name>@login.toolforge.org
become zackbot
git clone https://github.com/zackmann08/InfoboxSweep.git ~/InfoboxSweep
toolforge jobs run setup-ibox --image python3.13 --wait \
  --command "cd /data/project/zackbot/InfoboxSweep && python3 -m venv venv && venv/bin/pip install -e ."
```

ZackBotPy's `user-config.py` works here too: `PYWIKIBOT_DIR` already points
Pywikibot at it, for every job. Add the `infoboxsweep` bot password to its
`user-password.py`, or give this checkout its own pair of files.

Then add `source ~/InfoboxSweep/deploy/runibox.sh` to `~/.bashrc`, for:

```bash
runibox                          # a live run over the whole tree, as the job "ibox"
runibox --max-edits 10           # options go to infoboxsweep run
runibox --dry-run --limit 500    # a dry run, as "dry-ibox"
stopibox                         # stop "ibox" cleanly, and wait until it has reported
```

Each job writes its log to `~/ibox.err` and its report to
`~/InfoboxSweep/out/`. To run it every week,
[`deploy/jobs.example.yaml`](deploy/jobs.example.yaml) has a scheduled job:

```bash
cp ~/InfoboxSweep/deploy/jobs.example.yaml ~/jobs.yaml   # or add it to the jobs.yaml you have
toolforge jobs load ~/jobs.yaml
```

## Usage

```
infoboxsweep [--lang en] [--family wikipedia] [-v] COMMAND ...
```

| Command | What it does |
|---|---|
| `tree` | Walks the category tree and prints what's in it: categories, depth, distinct pages, repeat listings, and subcategories not followed. `--list` prints every category and page. |
| `check TITLE` | For one article (or its talk page): whether it has an infobox and why, what the bot would take off the talk page, and whether that would take it out of the request categories. Saves nothing. |
| `run` | The task. A dry run unless `--live` is given. |

Options for `run`:

| Option | Meaning |
|---|---|
| `--live` | Edit for real. Needs `user-config.py`. |
| `--trial` | Allow a live run without the bot flag, for approved BRFA trial edits. |
| `--category TITLE` | The root of the tree. Default: `Category:Wikipedia articles with an infobox request`. Also taken by `tree`. |
| `--page TITLE` | Only check this page (a talk page, or an article for its talk page), not the tree. Repeatable. |
| `--namespace N` | Check talk pages in namespace N instead of 1. Repeatable. Dry runs only. |
| `--limit N` | Stop after checking N talk pages. |
| `--max-edits N` | Stop after N edits (or, in a dry run, after finding N). |
| `--run-page TITLE` | The emergency-stop page. Default: `User:<account>/Run`. |
| `--report-page TITLE` | The report page. Default: `User:<account>/InfoboxReport`. `""` turns it off. |
| `--stop-file PATH` | Stop cleanly, still reporting on the wiki, once this file exists. `runibox` gives each job one, for `stopibox`. |
| `--progress-minutes N` | How often a live run updates the report page as it goes. Default: 30. `0`: only at the start, after the walk, and at the end. |
| `--brfa TITLE` | The bot approval linked from every edit summary. `""` leaves the link out. |
| `--summary-suffix TEXT` | Added to the end of every edit summary. |
| `--out-dir DIR` | Where the report goes. Default: `out`. |

`run` exits with 0 when it finishes, 1 if any page had an error or the run
stopped part way, and 2 if it refused to start.

## Development

Before pushing, run the same checks GitHub runs:

```bash
ruff check .               # lint
mypy                       # type-check
coverage run -m pytest     # tests
coverage report            # fails below 95% of lines and branches covered
pytest -m live             # read-only tests against the real Wikipedia
```

[GitHub Actions](.github/workflows/ci.yml) runs lint, type checks and the
tests on Python 3.11 to 3.13 for every push and pull request, and with the
oldest dependencies `pyproject.toml` allows. The
[Live workflow](.github/workflows/live.yml) runs the live tests every Monday.
No ordinary test touches a real wiki: they use the fake wiki in
[`tests/fakes.py`](tests/fakes.py), which has the same methods as
`infoboxsweep.wiki.Wiki`.

### Project layout

A run goes `cli` → `bot`, which walks the tree (`tree`), checks each article
(`infobox`), takes the request off its talk page (`request`), and writes the
reports (`report`, `wikireport`). Only `wiki` talks to the wiki.

| Path | Contents |
|---|---|
| `infoboxsweep/cli.py` | The command line. |
| `infoboxsweep/bot.py` | A run: pre-flight checks, the page loop, checking with MediaWiki, saving, edit summaries, the report page. |
| `infoboxsweep/tree.py` | Walking the category tree, every level, each page once. |
| `infoboxsweep/infobox.py` | Whether an article has an infobox. |
| `infoboxsweep/request.py` | Taking an infobox request off a talk page's wikitext. |
| `infoboxsweep/report.py` | The text report of a run. |
| `infoboxsweep/wikireport.py` | The report page on the wiki: the Runs table and the review list. |
| `infoboxsweep/wiki.py` | Everything the bot asks of the wiki, through Pywikibot. |
| `infoboxsweep/wikitext.py` | Small wikitext helpers. |
| `deploy/` | `user-config.example.py`, the `runibox` and `stopibox` shortcuts, and an example scheduled job. |
| `tests/` | The test suite. `tests/fakes.py` is the fake wiki. |

## License

GNU General Public License v3.0, as for ZackBotPy, from which parts of the
code are adapted. See [LICENSE](LICENSE).
