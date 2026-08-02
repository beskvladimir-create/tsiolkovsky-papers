#!/usr/bin/env python3
"""
Очередь на перечитывание листов, прочитанных не той моделью.

Классификатор по ровности строк ошибался на 29% сканов. Из уже расшифрованного
это задело две группы:

  156 листов печати, которые Opus читал как рукопись и архаизировал — дописал
      яти и еры, которых на скане нет (проверено глазами на выборке);
  222 листа рукописи, которые Sonnet читал как печать, а на почерке он
      измеримо слабее.

Три четверти неверно направленной печати модель прочитала правильно, поэтому
перечитываем не всё, а только эти две группы.

Прежние версии сохраняются рядом в transcripts_pass1, чтобы можно было
сравнить до и после, а не поверить на слово.
"""
import csv, json, os, re, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCH_THR = 0.10   # доля дореформенных знаков на слово, выше которой лист подозрителен


def raw_path(scan):
    p = scan.split('/')
    return os.path.join(ROOT, 'data', 'transcripts_raw', p[1], p[2],
                        p[3].replace('.jpg', '.txt'))


def archaisation(scan):
    t = raw_path(scan)
    if not os.path.exists(t):
        return None
    s = open(t, encoding='utf-8').read()
    w = len(s.split())
    if w < 30:
        return None
    return (len(re.findall(r'[ѣіѳѵ]', s)) + len(re.findall(r'ъ(?=\s|$)', s))) / w


def main():
    new = {r['path']: r['class'] for r in
           csv.DictReader(open(os.path.join(ROOT, 'page_classes.csv'), encoding='utf-8'))}
    q = json.load(open(os.path.join(ROOT, 'queue.json'), encoding='utf-8'))

    items = []
    for it in q['items']:
        now = new.get(it['path'], it['class'])
        was = it['class']
        if was == 'hand' and now == 'typed':
            a = archaisation(it['path'])
            if a is not None and a > ARCH_THR:
                items.append(dict(it, class_=now, model='sonnet',
                                  status='pending', reason='архаизация печати'))
        elif was in ('typed', 'note') and now == 'hand':
            items.append(dict(it, class_=now, model='opus',
                              status='pending', reason='рукопись на слабой модели'))

    # сохраняем прежние транскрипции, иначе сравнивать будет не с чем
    bak = os.path.join(ROOT, 'data', 'transcripts_pass1')
    kept = 0
    for it in items:
        src = raw_path(it['path'])
        if not os.path.exists(src):
            continue
        dst = os.path.join(bak, os.path.relpath(src, os.path.join(ROOT, 'data', 'transcripts_raw')))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        kept += 1

    for it in items:
        it['class'] = it.pop('class_')

    shutil.copy2(os.path.join(ROOT, 'queue.json'), os.path.join(ROOT, 'queue_pass1.json'))
    json.dump({'batch': q['batch'], 'items': items},
              open(os.path.join(ROOT, 'queue.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    import collections
    by = collections.Counter(i['reason'] for i in items)
    print(f"  на перечитывание: {len(items)} сканов")
    for k, v in by.items():
        print(f"    {k}: {v}")
    print(f"  прежние версии сохранены: {kept} файлов -> data/transcripts_pass1")
    print("  прежняя очередь -> queue_pass1.json")


if __name__ == '__main__':
    main()
