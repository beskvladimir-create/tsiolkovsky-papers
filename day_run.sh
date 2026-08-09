#!/bin/bash
# Дневной прогон: запускается вручную, когда машина свободна.
#
# Ночной агент работает с 22:00 до 4:00 и в это окно не пускает ничего лишнего.
# Днём окно надо снять, но взамен нужен предел по времени: иначе прогон съест
# квоту к моменту, когда она понадобится для работы.
#
#     ./day_run.sh        четыре часа
#     ./day_run.sh 2      два часа
#     ./day_run.sh 8      восемь
#
# Останавливается сам по времени, по исчерпании лимита сессии или после пяти
# сбоев подряд. Прервать досрочно можно: состояние очереди на диске, теряется
# самое большее одна пачка.
cd "$(dirname "$0")" || exit 1

HOURS="${1:-4}"
case "$HOURS" in
    ''|*[!0-9.]*) echo "укажите число часов, например ./day_run.sh 3"; exit 1 ;;
esac
MIN=$(python3 -c "print(int(float('$HOURS')*60))")

if pgrep -f night_run.sh >/dev/null; then
    echo "прогон уже идёт, второй не нужен"
    exit 0
fi

echo "запускаю на $HOURS ч (до $(date -v+${MIN}M '+%H:%M' 2>/dev/null || echo "+${MIN} мин"))"
IGNORE_WINDOW=1 MAX_MINUTES="$MIN" nohup ./night_run.sh > /tmp/day_run.out 2>&1 &
sleep 20
if pgrep -f night_run.sh >/dev/null; then
    tail -2 /tmp/day_run.out
    echo
    echo "идёт. посмотреть ход:   tail -f /tmp/day_run.out"
    echo "остановить досрочно:    pkill -f night_run.sh"
else
    echo "не запустился, вот что в логе:"
    tail -5 /tmp/day_run.out
    exit 1
fi
