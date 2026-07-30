#!/bin/bash
# Watchdog for the downloader.
#
# A laptop gets carried around: it sleeps, it changes network, and macOS kills
# the process with no traceback and no exit message. This checks every two
# minutes whether the downloader is alive and restarts it if not. The
# downloader's own resume logic makes restarts free — files already on disk and
# structurally valid are never refetched.
#
# Start:  nohup ./keeper.sh >> keeper.log 2>&1 &
# Stop:   kill $(cat .keeper_pid) && kill $(cat .full_pid)
#
# caffeinate keeps the machine from sleeping on idle. It does not override a
# closed lid: with the lid shut the download pauses and resumes when it opens.

cd "$(dirname "$0")" || exit 1
echo $$ > .keeper_pid

ARGS="--to 2200 --miss-stop 60 --delay 0.3 0.6"
log() { echo "$(date '+%F %T') $*"; }

log "watchdog started, checking every 120 s"

while true; do
    alive=0
    if [ -f .full_pid ] && ps -p "$(cat .full_pid)" >/dev/null 2>&1; then
        alive=1
    fi

    if [ "$alive" -eq 0 ]; then
        # Wait for the network first: respawning into a dead wifi connection
        # after moving between access points achieves nothing.
        for i in 1 2 3 4 5; do
            code=$(curl -s -o /dev/null --max-time 15 -w "%{http_code}" \
                   "https://www.ras.ru/ktsiolkovskyarchive/1_actview.aspx?id=1")
            [ "$code" = "200" ] && break
            log "no network (HTTP $code), waiting 60 s"
            sleep 60
        done

        pages=$(find data -name '*.jpg' | wc -l | tr -d ' ')
        log "downloader not running, starting it. Scans on disk: $pages"
        nohup caffeinate -is python3 tsiolkovsky_downloader.py $ARGS \
              >> full_run.log 2>&1 &
        echo $! > .full_pid
        sleep 15
        if ps -p "$(cat .full_pid)" >/dev/null 2>&1; then
            log "started, PID $(cat .full_pid)"
        else
            log "failed to start, retrying in 120 s"
        fi
    fi

    sleep 120
done
