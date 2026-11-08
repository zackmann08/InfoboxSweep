# runibox, runimages, stopibox and stopimages: start and stop Toolforge jobs
# running InfoboxSweep's two tasks.  Source this file from ~/.bashrc:
#
#     source ~/InfoboxSweep/deploy/runibox.sh
#
# runibox starts a live run of the infobox task (infoboxsweep) over its whole
# category tree, as the job "needs-infobox"; runimages, of the photograph task
# (imagesweep), as "images".  With --dry-run first, a dry run, as
# "dry-needs-infobox"
# or "dry-images".  Anything after goes to the command's run, so quote
# option values with spaces:
#
#     runibox
#     runibox --max-edits 10
#     runimages --trial --max-edits 50
#     runimages --dry-run --limit 500
#
# stopibox and stopimages stop the run cleanly, so that it still gives its
# row on User:ZackBot/InfoboxReport or User:ZackBot/ImageReport its final
# numbers ("manually stopped by the bot operator"), and wait until it has:
#
#     stopibox
#     stopimages --dry-run
#
# INFOBOXSWEEP_DIR is where the bot is checked out (default: ~/InfoboxSweep),
# INFOBOXSWEEP_IMAGE the image its virtual environment was built with
# (default: python3.13), and INFOBOXSWEEP_STOP_WAIT how long the stop
# commands wait, in seconds (default: 600).

runibox() {
  _infoboxsweep_run infoboxsweep needs-infobox "$@"
}

runimages() {
  _infoboxsweep_run imagesweep images "$@"
}

stopibox() {
  _infoboxsweep_stop stopibox needs-infobox "$@"
}

stopimages() {
  _infoboxsweep_stop stopimages images "$@"
}

# _infoboxsweep_run PROGRAM JOB [--dry-run] [options]: start the job running
# "PROGRAM run [--live] --stop-file stop/JOB options".
_infoboxsweep_run() {
  local program=$1 name=$2 live=--live dir cmd opt
  shift 2
  if [ "$1" = --dry-run ]; then live='' name="dry-$name"; shift; fi
  dir="${INFOBOXSWEEP_DIR:-$HOME/InfoboxSweep}"
  # Quote for the job's shell: each ' becomes '\''.
  cmd="cd '${dir//\'/\'\\\'\'}' && venv/bin/$program run"
  [ -n "$live" ] && cmd+=" $live"
  cmd+=" --stop-file 'stop/$name'"
  for opt in "$@"; do cmd+=" '${opt//\'/\'\\\'\'}'"; done
  echo "Starting job $name: $cmd"
  toolforge jobs run "$name" --image "${INFOBOXSWEEP_IMAGE:-python3.13}" --command "$cmd"
}

# _infoboxsweep_stop FUNCTION JOB [--dry-run]: ask the job to stop, by
# creating its stop file, and wait until the bot has stopped and reported,
# which it says by deleting the file.
_infoboxsweep_stop() {
  local function=$1 name=$2 dir stop waited=0 limit="${INFOBOXSWEEP_STOP_WAIT:-600}"
  shift 2
  if [ "$1" = --dry-run ]; then name="dry-$name"; shift; fi
  if [ $# -ne 0 ]; then
    echo "usage: $function [--dry-run]" >&2
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
