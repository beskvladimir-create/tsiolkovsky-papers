#!/bin/bash
# Сторож скачивателя.
#
# Ноутбук носят с собой: сон, смена сети, macOS прибивает процесс без всякого
# traceback. Сторож раз в две минуты смотрит, жив ли скачиватель, и поднимает
# его заново. Resume в самом скачивателе гарантирует, что перезапуск ничего не
# теряет: скачанные и валидные файлы не перекачиваются.
#
# Запуск:  nohup ./keeper.sh >> keeper.log 2>&1 &
# Остановка: kill $(cat .keeper_pid) && kill $(cat .full_pid)

cd "$(dirname "$0")" || exit 1
echo $$ > .keeper_pid

ARGS="--to 2200 --miss-stop 60 --delay 0.3 0.6"
log() { echo "$(date '+%F %T') $*"; }

log "сторож запущен, проверка каждые 120 с"

while true; do
    alive=0
    if [ -f .full_pid ] && ps -p "$(cat .full_pid)" >/dev/null 2>&1; then
        alive=1
    fi

    if [ "$alive" -eq 0 ]; then
        # ждём сеть: после смены wifi поднимать бессмысленно
        for i in 1 2 3 4 5; do
            code=$(curl -s -o /dev/null --max-time 15 -w "%{http_code}" \
                   "https://www.ras.ru/ktsiolkovskyarchive/1_actview.aspx?id=1")
            [ "$code" = "200" ] && break
            log "сети нет (HTTP $code), жду 60 с"
            sleep 60
        done

        pages=$(find data -name '*.jpg' | wc -l | tr -d ' ')
        log "скачиватель не найден, поднимаю. Листов на диске: $pages"
        nohup caffeinate -is python3 tsiolkovsky_downloader.py $ARGS \
              >> full_run.log 2>&1 &
        echo $! > .full_pid
        sleep 15
        if ps -p "$(cat .full_pid)" >/dev/null 2>&1; then
            log "поднят, PID $(cat .full_pid)"
        else
            log "поднять не удалось, повтор через 120 с"
        fi
    fi

    sleep 120
done
