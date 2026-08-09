#!/bin/bash
# Overnight transcription run.
#
# The hard requirement is that the subscription is free again by morning, so
# there is a fixed stop hour chosen with margin: the usage window is a rolling
# five hours, so the run has to finish at least five hours before the working
# day starts.
#
# Default: runs until 04:00, so the window is clear from 09:00.
#
#   ./night_run.sh                    until 04:00
#   STOP_HOUR=3 ./night_run.sh        until 03:00
#   MAX_BATCHES=5 ./night_run.sh      cap the volume, for a trial run
#   MAX_MINUTES=180 ./night_run.sh    stop after three hours
#   IGNORE_WINDOW=1 ./night_run.sh    run outside the night window
#
# IGNORE_WINDOW exists for running while away from the machine during the day.
# Pair it with MAX_MINUTES: the usage window is a rolling five hours, so a
# daytime run should end well before you need the quota back.
#
# Stops by itself on hitting the subscription limit. State lives in
# queue.json; the run can be killed at any point and loses at most one batch.

cd "$(dirname "$0")" || exit 1

# One instance only. The scheduled 22:00 launch would otherwise start a second
# run on top of one still going, and both would write the same queue file.
if [ -f .night_pid ] && ps -p "$(cat .night_pid)" >/dev/null 2>&1; then
    echo "$(date '+%F %T') already running as PID $(cat .night_pid), exiting" \
        | tee -a night_run.log
    exit 0
fi

STOP_HOUR="${STOP_HOUR:-4}"
MAX_BATCHES="${MAX_BATCHES:-100000}"
MAX_MINUTES="${MAX_MINUTES:-0}"
IGNORE_WINDOW="${IGNORE_WINDOW:-0}"

# launchd starts with a bare environment, and claude does not live on that PATH.
# Without this every call fails instantly, and a run that cannot work at all
# marches through the queue marking scan after scan failed: 7,639 of them in one
# night, none of them read.
CLAUDE="${CLAUDE:-$HOME/.local/bin/claude}"
[ -x "$CLAUDE" ] || CLAUDE="$(command -v claude 2>/dev/null)"
if [ -z "$CLAUDE" ] || [ ! -x "$CLAUDE" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') claude not found; refusing to start" >&2
    exit 1
fi

# A batch may fail on its own account. Every batch failing means the pipeline is
# broken, and the right response is to stop rather than to consume the queue.
MAX_STREAK="${MAX_STREAK:-5}"
STREAK=0
STARTED=$(date +%s)
OUT=data/transcripts_raw
mkdir -p "$OUT"
echo $$ > .night_pid

log() { echo "$(date '+%F %T') $*" | tee -a night_run.log; }

if [ "$MAX_MINUTES" -gt 0 ]; then
    log "run started, stopping after $MAX_MINUTES min, batch cap $MAX_BATCHES"
else
    log "run started, stopping at ${STOP_HOUR}:00, batch cap $MAX_BATCHES"
fi

SPEC=$(cat TRANSCRIPTION_SPEC.md)
n=0

while true; do
    if [ "$MAX_MINUTES" -gt 0 ]; then
        ELAPSED=$(( ($(date +%s) - STARTED) / 60 ))
        if [ "$ELAPSED" -ge "$MAX_MINUTES" ]; then
            log "ran for $ELAPSED min, stopping"
            break
        fi
    fi
    H=$(date +%-H)
    # window: from the evening until STOP_HOUR in the morning
    if [ "$IGNORE_WINDOW" -eq 0 ] && [ "$H" -ge "$STOP_HOUR" ] && [ "$H" -lt 20 ]; then
        log "outside the night window (now ${H}:00), stopping"
        break
    fi
    if [ "$n" -ge "$MAX_BATCHES" ]; then
        log "batch cap reached, stopping"
        break
    fi

    # next batch for one model
    BATCH_JSON=$(python3 next_batch.py) || { log "queue empty or error"; break; }
    [ -z "$BATCH_JSON" ] && { log "queue empty, everything done"; break; }

    MODEL=$(echo "$BATCH_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["model"])')
    PATHS=$(echo "$BATCH_JSON" | python3 -c 'import sys,json;print("\n".join(i["path"] for i in json.load(sys.stdin)["items"]))')
    IDS=$(echo "$BATCH_JSON" | python3 -c 'import sys,json;print(" ".join(i["id"] for i in json.load(sys.stdin)["items"]))')

    log "batch $((n+1)): $MODEL, $(echo "$PATHS" | wc -l | tr -d ' ') scans"

    # The prompt stays in Russian: the manuscripts are Russian and so is
    # the specification the model is asked to follow.
    PROMPT="Ты транскрибируешь сканы рукописей К.Э. Циолковского из фонда 555 Архива РАН.

СПЕЦИФИКАЦИЯ (следуй буквально):
$SPEC

Прочитай инструментом Read эти сканы по порядку:
$(echo "$PATHS" | sed "s|^|$PWD/|")

Твой финальный ответ это и есть результат. Верни ТОЛЬКО транскрипции,
разделённые строкой-маркером вида === ИМЯ_ФАЙЛА === перед каждым листом,
например === 003.jpg ===. Никакого вступления и никаких выводов."

    RESP=$(echo "$PROMPT" | "$CLAUDE" -p --model "$MODEL" --allowedTools Read 2>&1)
    RC=$?

    if echo "$RESP" | grep -qiE "session limit|rate.?limit|usage limit|exceeded your"; then
        log "hit the subscription limit; this batch is not counted"
        log "$(echo "$RESP" | grep -iE 'limit|reset' | head -2)"
        # This is the five-hour session window, not the week's, and the reply
        # says when it lifts. Leaving at that point throws away the rest of the
        # night: on 8 August the run stopped at 00:34 for a limit that lifted at
        # 01:00 and never came back. Wait it out instead.
        WAIT=$(echo "$RESP" | python3 reset_wait.py 2>/dev/null || echo 0)
        if [ "${WAIT:-0}" -gt 0 ]; then
            log "limit lifts in $((WAIT/60)) min; waiting rather than losing the night"
            sleep "$WAIT"
            STREAK=0
            continue
        fi
        log "no usable reset time in the reply, stopping"
        break
    fi
    if [ $RC -ne 0 ] || [ -z "$RESP" ]; then
        log "failure (code $RC), marking the batch failed and carrying on"
        python3 mark_batch.py failed $IDS
        STREAK=$((STREAK+1))
        if [ "$STREAK" -ge "$MAX_STREAK" ]; then
            log "$MAX_STREAK batches failed in a row: something is broken, not busy."
            log "stopping so the queue is not burned through. Last reply: $(echo "$RESP" | head -1)"
            break
        fi
        n=$((n+1)); sleep 10; continue
    fi

    printf '%s' "$RESP" | python3 save_batch.py $IDS
    python3 mark_batch.py done $IDS
    STREAK=0   # only a batch that actually came back clears the streak
    n=$((n+1))
    sleep 3
done

python3 build_queue.py --status | tee -a night_run.log
log "run finished, batches done: $n"
rm -f .night_pid
