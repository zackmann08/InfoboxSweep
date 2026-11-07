# runibox and stopibox: start and stop a Toolforge job running InfoboxSweep.
# Source this file from ~/.bashrc:
#
#     source ~/InfoboxSweep/deploy/runibox.sh
#
# runibox starts a live run over the whole category tree, as the job "ibox";
# with --dry-run first, a dry run, as "dry-ibox".  Anything after goes to
# infoboxsweep run, so quote option values with spaces:
#
#     runibox
#     runibox --max-edits 10
#     runibox --trial --max-edits 50
#     runibox --dry-run --limit 500
#
# stopibox stops the run cleanly, so that it still gives its row on
# User:ZackBot/InfoboxReport its final numbers ("manually stopped by the bot
# operator"), and waits until it has:
#
#     stopibox
#     stopibox --dry-run
#
# INFOBOXSWEEP_DIR is where the bot is checked out (default: ~/InfoboxSweep),
# INFOBOXSWEEP_IMAGE the image its virtual environment was built with (default:
# python3.13), and INFOBOXSWEEP_STOP_WAIT how long stopibox waits, in seconds
# (default: 600).

runibox() {
  local live=--live name=ibox dir cmd opt
  if [ "$1" = --dry-run ]; then live='' name=dry-ibox; shift; fi
  dir="${INFOBOXSWEEP_DIR:-$HOME/InfoboxSweep}"
  # Quote for the job's shell: each ' becomes '\''.
  cmd="cd '${dir//\'/\'\\\'\'}' && venv/bin/infoboxsweep run"
  [ -n "$live" ] && cmd+=" $live"
  cmd+=" --stop-file 'stop/$name'"
  for opt in "$@"; do cmd+=" '${opt//\'/\'\\\'\'}'"; done
  echo "Starting job $name: $cmd"
  toolforge jobs run "$name" --image "${INFOBOXSWEEP_IMAGE:-python3.13}" --command "$cmd"
}

# stopibox [--dry-run]: ask the run to stop, by creating its stop file, and
# wait until the bot has stopped and reported, which it says by deleting
# the file.
stopibox() {
  local name=ibox dir stop waited=0 limit="${INFOBOXSWEEP_STOP_WAIT:-600}"
  if [ "$1" = --dry-run ]; then name=dry-ibox; shift; fi
  if [ $# -ne 0 ]; then
    echo 'usage: stopibox [--dry-run]' >&2
    return 2
  fi
  dir="${INFOBOXSWEEP_DIR:-$HOME/InfoboxSweep}"
  stop="$dir/stop/$name"
  mkdir -p "$dir/stop" && : > "$stop" || return 1
  echo "Asked $name to stop. Waiting for it to finish its batch and report..."
  while [ -e "$stop" ]; do
    if [ "$waited" -ge "$limit" ]; then
      rm -f "$stop"
      echo "$name hasn't stopped after $limit s. Is it running? See: toolforge jobs list" >&2
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  echo "$name has stopped, and reported on the wiki."
}
