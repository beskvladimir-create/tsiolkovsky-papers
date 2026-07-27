#!/bin/bash
cd ~/Desktop/Projects/tsiolkovsky-archive
log(){ echo "$(date '+%F %T') $*" | tee -a auto_resume.log; }
TESTURL="https://www.ras.ru/CArchive/pageimages/555%5C1_009/001.jpg"
log "жду восстановления сервера РАН, проверка каждые 10 мин"
while true; do
  sz=$(curl -s -A "Mozilla/5.0" -o /tmp/hc.jpg -w "%{size_download}" "$TESTURL")
  code=$(curl -s -A "Mozilla/5.0" -o /dev/null -w "%{http_code}" "$TESTURL")
  if [ "$code" = "200" ] && [ "$sz" -gt 300000 ] && tail -c2 /tmp/hc.jpg | xxd | grep -qi ffd9; then
    log "сервер ОК (HTTP $code, $sz б, целый) -> возобновляю опись 1, пауза 2-4с"
    nohup python3 tsiolkovsky_downloader.py --opis 1 --from 1 --to 600 --delay 2 4 >> download_opis1.log 2>&1 &
    echo $! > .dl_pid
    log "скачивание запущено, PID $(cat .dl_pid)"
    exit 0
  fi
  log "ещё режет (HTTP $code, $sz б), жду 10 мин"
  sleep 600
done
