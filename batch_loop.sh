#!/bin/bash
# Гонит очередь пакетными частями, пока она не кончится.
#
# Одна часть это 3 000 листов: файл задания около 800 МБ, а предел 2 ГБ, так
# что запас есть и на плотные сканы. Части идут по одной, а не пачкой:
# квота на одновременные задания неизвестна, а перерасход тут стоит денег.
#
# Цикл переживает перезапуск: что отправлено, лежит в batch_state.json, что
# прочитано, помечено в queue.json.
#
#   ./batch_loop.sh          # до конца очереди
#   ./batch_loop.sh 3        # только три части
set -u
cd "$(dirname "$0")"
LIMIT=${1:-999}
for ((n = 1; n <= LIMIT; n++)); do
  left=$(python3 -c "import json;print(sum(1 for i in json.load(open('queue.json'))['items'] if i['status'] in ('pending','failed')))")
  if [ "$left" -eq 0 ]; then
    echo "очередь пуста"
    break
  fi
  echo "=== часть $n, в очереди $left листов, $(date '+%H:%M')"
  # заливка идёт десять минут по сети, и разовый обрыв не повод бросать
  # весь остаток: пробуем часть трижды, прежде чем сдаться
  sent=0
  for try in 1 2 3; do
    if python3 batch_run.py submit --sheets 3000 --yes; then sent=1; break; fi
    echo "попытка $try не удалась, жду и повторяю"
    sleep 60
  done
  [ "$sent" = 1 ] || { echo "отправка не удалась трижды, останавливаюсь"; exit 1; }

  # ждём эту часть; задание на 3 000 листов считается минутами, но право
  # у сервера есть на сутки
  while :; do
    sleep 120
    state=$(python3 - <<'PY'
import json, urllib.request
key = open('.env').read().split('=', 1)[1].strip()
name = json.load(open('batch_state.json'))['jobs'][-1]['name']
r = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/' + name,
                           headers={'x-goog-api-key': key})
try:
    d = json.load(urllib.request.urlopen(r, timeout=60))
    print(d.get('metadata', {}).get('state', '?'))
except Exception as e:
    print('ОПРОС_НЕ_УДАЛСЯ')
PY
)
    case "$state" in
      *SUCCEEDED) break ;;
      *FAILED|*CANCELLED|*EXPIRED) echo "задание закончилось как $state"; exit 1 ;;
    esac
  done

  python3 batch_run.py collect || exit 1
done
python3 batch_run.py status

# Собираем дела из листов. assemble.py берёт только те дела, что прочитаны
# целиком: дело с дырой посреди читается как связный текст, и это худшая
# ошибка, какую может нести архивная публикация.
echo "=== сборка дел, $(date '+%H:%M')"
python3 assemble.py
