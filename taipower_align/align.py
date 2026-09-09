# -*- coding: utf-8 -*-
"""台電 機組資料(A) x 每日供需(B) 名稱對齊 + 裝置容量客觀驗證"""
import csv, re, io, collections, sys

# Windows 終端預設 cp950，印中文/數學符號會 UnicodeEncodeError 導致非零 exit
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

A = list(csv.DictReader(open('units.csv', encoding='utf-8-sig')))
for r in A:
    r['cap'] = int(r['裝置容量(瓩)']) / 1e4      # 瓩 -> 萬瓩，與 B 同單位
    r['unit'] = r['機組名稱'].strip()
    r['plant'] = r['電廠名稱'].strip()

rd = csv.reader(open('daily.csv', encoding='utf-8-sig'))
cols = next(rd)
data = [r for r in rd if r and r[0].strip()]
GEN = cols[7:]

# B 各欄實測極大值：裝置容量是物理上限，全年 max 應逼近牌牌容量
obs = {}
for i, c in enumerate(GEN):
    vals = []
    for r in data:
        try:
            vals.append(float(r[7 + i]))
        except Exception:
            pass
    vals.sort()
    obs[c] = dict(max=vals[-1] if vals else 0.0,
                  nz=sum(1 for v in vals if v > 0), n=len(vals))

CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}
def cn(s):
    m = re.search(r'([一二三四五六七八九十]+)', s)
    return CN.get(m.group(1)) if m else None

def units(plant=None, pred=None):
    return [r for r in A
            if (plant is None or r['plant'] == plant) and (pred is None or pred(r))]

def pfx(p):
    return lambda r: r['unit'].startswith(p)

def plants_of(us, fallback=''):
    """從實際比對到的機組推導電廠清單（去重、保序）。空集合時回退到宣告值。"""
    seen = list(collections.OrderedDict((u['plant'], None) for u in us))
    return '|'.join(seen) if seen else fallback

# ---- 對應規則：B欄位 -> (A電廠, 機組挑選條件, 信心, 備註) ----
RULES = []
for n in range(1, 4):
    RULES.append(('林口#%d(萬瓩)' % n, '林口發電廠',
                  lambda r, n=n: r['unit'].startswith('林') and cn(r['unit']) == n,
                  '高', '國字→阿拉伯'))
for n in range(1, 11):
    RULES.append(('台中#%d(萬瓩)' % n, '台中發電廠',
                  lambda r, n=n: r['unit'].startswith('中') and cn(r['unit']) == n,
                  '高', '國字→阿拉伯'))
for n in range(1, 5):
    RULES.append(('興達#%d(萬瓩)' % n, '興達發電廠',
                  lambda r, n=n: r['unit'].startswith('興') and '複' not in r['unit'] and cn(r['unit']) == n,
                  '高', '燃煤機；#1#2已除役不在A'))
for n in (1, 2):
    RULES.append(('大林#%d(萬瓩)' % n, '大林發電廠',
                  lambda r, n=n: r['unit'].startswith('大') and cn(r['unit']) == n,
                  '高', '燃煤機'))

RULES += [
 ('大潭 (#1-#9)(萬瓩)', '大潭發電廠', lambda r: True, '中', 'A僅7台(複1-6+GT7)，B已含新增#8#9'),
 ('通霄 (#1-#6、GT#9)(萬瓩)', '通霄發電廠', lambda r: True, '高', '完全對應7台'),
 ('興達 (#1-#5)(萬瓩)', '興達發電廠', pfx('興達複'), '高', '燃氣複循環5台'),
 ('南部 (#1-#4)(萬瓩)', '南部發電廠', lambda r: True, '高', '完全對應4台'),
 ('大林(#5-#6)(萬瓩)', '大林發電廠', pfx('大六'), '中', 'A僅大六機；大五機已除役'),
 ('協和 (#1-#4)(萬瓩)', '協和發電廠', lambda r: True, '中', 'A僅協三/協四；#1#2已除役'),
 ('氣渦輪(萬瓩)', '台中發電廠', pfx('GT#'), '低', 'B為全系統氣渦輪彙總，A只對到台中GT#1-4'),
 ('德基(萬瓩)', '大甲溪發電廠', pfx('德基'), '高', '大甲溪分廠'),
 ('青山(萬瓩)', '大甲溪發電廠', pfx('青山'), '高', '大甲溪分廠'),
 ('谷關(萬瓩)', '大甲溪發電廠', pfx('谷關'), '高', '大甲溪分廠'),
 ('天輪(萬瓩)', '大甲溪發電廠', pfx('天輪'), '高', '大甲溪分廠'),
 ('馬鞍(萬瓩)', '大甲溪發電廠', pfx('馬鞍'), '高', '大甲溪分廠'),
 ('大觀(萬瓩)', '大觀發電廠', pfx('大觀一廠'), '高', '大觀一廠'),
 ('大觀二(萬瓩)', '大觀發電廠', pfx('大觀二廠'), '高', '大觀二廠(抽蓄)'),
 ('明潭(萬瓩)', '明潭發電廠', pfx('明潭#'), '高', '抽蓄'),
 ('鉅工(萬瓩)', '明潭發電廠', pfx('鉅工'), '高', '明潭分廠'),
 ('水里(萬瓩)', '明潭發電廠', lambda r: r['unit'] == '水里', '高', '明潭分廠'),
 ('碧海(萬瓩)', '東部發電廠', lambda r: r['unit'] == '碧海', '高', '東部分廠'),
 ('立霧(萬瓩)', '東部發電廠', pfx('立霧'), '高', '東部分廠'),
 ('龍澗(萬瓩)', '東部發電廠', pfx('龍澗'), '高', '東部分廠'),
 ('卓蘭(萬瓩)', '卓蘭發電廠', pfx('卓蘭#'), '高', '不含景山'),
 ('萬大(萬瓩)', '萬大發電廠', pfx('萬大#'), '高', '不含松林'),
]

out = io.open('crosswalk.txt', 'w', encoding='utf-8')
def P(*a):
    out.write(' '.join(str(x) for x in a) + '\n')

rows_cw = []
matched = set()

P('%-22s %-14s %2s %9s %9s %6s %-4s %s' % ('B欄位', 'A電廠', '台', 'A容量', 'B實測max', '比值', '信心', '備註'))
P('-' * 126)
for col, plant, pred, conf, note in RULES:
    us = units(plant, pred)
    ca = sum(u['cap'] for u in us)
    ob = obs.get(col, {}).get('max', 0.0)
    ratio = (ob / ca) if ca else 0.0
    flag = '' if 0.80 <= ratio <= 1.06 else '   <<< 比值異常'
    P('%-22s %-14s %2d %9.2f %9.2f %6.2f %-4s %s%s' % (
        col.replace('(萬瓩)', ''), plant, len(us), ca, ob, ratio, conf, note, flag))
    for u in us:
        matched.add((u['plant'], u['unit']))
    rows_cw.append(dict(b_column=col, a_plant=plants_of(us, plant), n_plants=len(us and
                        set(u['plant'] for u in us) or {plant}),
                        a_units='|'.join(u['unit'] for u in us), n_units=len(us),
                        cap_a_wankw=round(ca, 2), obs_max_b=ob,
                        ratio=round(ratio, 3), confidence=conf, note=note))

# 離島 = 尖山 + 塔山 + 珠山
iso = units(pred=lambda r: r['plant'] in ('尖山發電廠', '塔山發電廠', '協和電廠－珠山分廠'))
ca = sum(u['cap'] for u in iso); ob = obs['離島(萬瓩)']['max']
P('%-22s %-14s %2d %9.2f %9.2f %6.2f %-4s %s' % ('離島', '(3座電廠)', len(iso), ca, ob, ob/ca, '高', '地理定義彙總'))
for u in iso:
    matched.add((u['plant'], u['unit']))
rows_cw.append(dict(b_column='離島(萬瓩)', a_plant=plants_of(iso),
                    n_plants=len(set(u['plant'] for u in iso)),
                    a_units='|'.join(u['unit'] for u in iso), n_units=len(iso),
                    cap_a_wankw=round(ca, 2), obs_max_b=ob, ratio=round(ob/ca, 3),
                    confidence='高', note='地理定義彙總：澎湖+金門+馬祖三離島電廠'))

# 其他小水力 = 剩下所有水力機組（殘差）
hyd = [r for r in A if r['燃料種類'] == '水' and (r['plant'], r['unit']) not in matched]
ca = sum(u['cap'] for u in hyd); ob = obs['其他小水力(萬瓩)']['max']
P('%-22s %-14s %2d %9.2f %9.2f %6.2f %-4s %s' % (
    '其他小水力', '(%d座電廠)' % len(set(u['plant'] for u in hyd)), len(hyd), ca, ob, ob/ca, '中', '殘差彙總'))
for u in hyd:
    matched.add((u['plant'], u['unit']))
rows_cw.append(dict(b_column='其他小水力(萬瓩)', a_plant=plants_of(hyd),
                    n_plants=len(set(u['plant'] for u in hyd)),
                    a_units='|'.join(u['unit'] for u in hyd), n_units=len(hyd),
                    cap_a_wankw=round(ca, 2), obs_max_b=ob, ratio=round(ob/ca, 3),
                    confidence='中',
                    note='殘差彙總：全部水力扣除15個具名欄位後的剩餘；成分隨版本可能改變，不適合跨期比較'))

BONLY = [c for c in GEN if c not in {r['b_column'] for r in rows_cw}]
P(''); P('########## B 有、A 完全沒有 (%d 欄) ##########' % len(BONLY))
for c in BONLY:
    P('  %-14s 實測max=%7.2f 萬瓩   有值天數=%d/%d' % (
        c.replace('(萬瓩)', ''), obs[c]['max'], obs[c]['nz'], obs[c]['n']))

AONLY = [r for r in A if (r['plant'], r['unit']) not in matched]
P(''); P('########## A 有、B 無獨立欄位 (%d 台) ##########' % len(AONLY))
for p in collections.OrderedDict((r['plant'], None) for r in AONLY):
    rs = [r for r in AONLY if r['plant'] == p]
    P('  %-14s %2d台 %7.2f萬瓩  %s' % (p, len(rs), sum(x['cap'] for x in rs),
                                       '/'.join(x['unit'] for x in rs)))

# ---- 標記桶狀欄位：is_residual = 成分由消去法決定，定義會隨版本漂移 ----
RESIDUAL = {'其他小水力(萬瓩)', '氣渦輪(萬瓩)'}     # 真殘差：定義為「其他」
BUCKET   = {'離島(萬瓩)'}                        # 桶狀但有穩定規則(地理)
for r in rows_cw:
    r['is_residual'] = 1 if r['b_column'] in RESIDUAL else 0
    r['is_bucket'] = 1 if r['b_column'] in (RESIDUAL | BUCKET) else 0

# ---- 桶狀欄位的電廠組成 ----
P(''); P('########## 桶狀欄位的電廠組成 ##########')
for r in rows_cw:
    if not r['is_bucket']:
        continue
    P('  %s  (%d座電廠 / %d台 / %.2f萬瓩)  is_residual=%d' % (
        r['b_column'].replace('(萬瓩)', ''), r['n_plants'], r['n_units'],
        r['cap_a_wankw'], r['is_residual']))
    us = r['a_units'].split('|') if r['a_units'] else []
    byp = collections.OrderedDict()
    for u in us:
        for a in A:
            if a['unit'] == u:
                byp.setdefault(a['plant'], []).append(a)
                break
    for p, rs in sorted(byp.items(), key=lambda kv: -sum(x['cap'] for x in kv[1])):
        P('      %-14s %2d台 %6.2f萬瓩  %s' % (
            p, len(rs), sum(x['cap'] for x in rs), '/'.join(x['unit'] for x in rs)))

# ---- 被拆到「具名欄位」與「殘差欄位」兩邊的電廠 ----
named_plants = collections.defaultdict(list)
for r in rows_cw:
    if not r['is_bucket'] and r['a_plant']:
        for p in r['a_plant'].split('|'):
            named_plants[p].append(r['b_column'].replace('(萬瓩)', ''))
resid_plants = set()
for r in rows_cw:
    if r['is_residual'] and r['a_plant']:
        resid_plants.update(r['a_plant'].split('|'))
split = sorted(resid_plants & set(named_plants))
P(''); P('########## 警告：同時橫跨具名欄位與殘差欄位的電廠 (%d座) ##########' % len(split))
P('  這些電廠無法從 B 還原完整出力 —— 殘差桶內的部分拆不出來')
for p in split:
    P('  %-14s 具名欄位: %s   + 落在殘差桶內的機組' % (p, '/'.join(named_plants[p])))

P(''); P('對應率:  A %d/%d 台 (%.0f%%)   |   B %d/%d 欄 (%.0f%%)' % (
    len(matched), len(A), 100.0*len(matched)/len(A),
    len(rows_cw), len(GEN), 100.0*len(rows_cw)/len(GEN)))
out.close()

FIELDS = ['b_column', 'a_plant', 'n_plants', 'a_units', 'n_units', 'cap_a_wankw',
          'obs_max_b', 'ratio', 'confidence', 'is_residual', 'is_bucket', 'note']
with io.open('crosswalk.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader(); w.writerows(rows_cw)

print(io.open('crosswalk.txt', encoding='utf-8').read())
