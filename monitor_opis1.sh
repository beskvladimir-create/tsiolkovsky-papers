#!/bin/bash
cd ~/Desktop/Projects/tsiolkovsky-archive
log(){ echo "$(date '+%F %T') $*" | tee -a heal.log; }
PID=$(cat .dl_pid)
log "монитор: жду конца основного прохода описи 1 (PID $PID)"
while ps -p $PID >/dev/null 2>&1; do sleep 120; done
log "основной проход закончен, начинаю до-качивание неполных"
for pass in 1 2 3 4 5; do
  python3 tsiolkovsky_downloader.py --opis 1 --redo-incomplete --delay 1 2 >> heal.log 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then log "проход $pass: все дела ok"; break; fi
  log "проход $pass: ещё остались неполные, пауза 5 мин и повтор"
  sleep 300
done
echo "=== ОПИСЬ 1 ГОТОВА $(date '+%F %T') ===" > opis1_summary.txt
python3 - >> opis1_summary.txt <<'PY'
import csv
rows=[r for r in csv.DictReader(open('catalog.csv',encoding='utf-8')) if r['opis_page']=='1']
ok=[r for r in rows if r['status']=='ok']
bad=[r for r in rows if r['status']!='ok']
print(f"дел ok: {len(ok)} | листов: {sum(int(r['pages']) for r in ok)}")
if bad: print("НЕ долечено (нет сканов на сервере или упорный сбой):",[r['delo'] for r in bad])
print("топ-20 объёмных:")
for r in sorted(ok,key=lambda x:-int(x['pages']))[:20]:
    print(f"  дело {r['delo']}: {r['pages']} л. — {r['name'][:70]}")
PY
cat opis1_summary.txt >> heal.log
