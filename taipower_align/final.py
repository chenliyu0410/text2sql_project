# -*- coding: utf-8 -*-
"""產出最終對照表 + 長格式 + 缺漏清單，並驗證『尖峰時刻出力』語意"""
import csv, io, collections, sys

# Windows 終端預設 cp950，印中文/數學符號會 UnicodeEncodeError 導致非零 exit
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

A = list(csv.DictReader(open('units.csv', encoding='utf-8-sig')))
for r in A:
    r['cap'] = int(r['裝置容量(瓩)']) / 1e4
    r['unit'] = r['機組名稱'].strip()
    r['plant'] = r['電廠名稱'].strip()

rd = csv.reader(open('daily.csv', encoding='utf-8-sig'))
cols = next(rd)
data = [r for r in rd if r and r[0].strip()]
idx = {c: i for i, c in enumerate(cols)}
GEN = cols[7:]

out = io.open('final.txt', 'w', encoding='utf-8')
P = lambda *a: out.write(' '.join(str(x) for x in a) + '\n')

# ---- 驗證：各機組欄位加總 是否 ≈ 尖峰負載 ----
P('##### 語意驗證：機組欄位加總 vs 尖峰負載 #####')
P('若 B 是「尖峰時刻瞬時出力」，各機組加總應 ≈ 尖峰負載')
diffs = []
for r in data[:400]:
    try:
        tot = sum(float(r[idx[c]]) for c in GEN)
        peak = float(r[idx['尖峰負載(萬瓩)']])
        cap = float(r[idx['淨尖峰供電能力(萬瓩)']])
        diffs.append((r[0], tot, peak, cap, tot / peak))
    except Exception:
        pass
rr = sorted(d[4] for d in diffs)
P('  樣本 %d 天' % len(diffs))
P('  加總/尖峰負載  中位數=%.3f  p10=%.3f  p90=%.3f' % (
    rr[len(rr)//2], rr[len(rr)//10], rr[9*len(rr)//10]))
for d in diffs[:5]:
    P('    %s  機組加總=%7.1f  尖峰負載=%7.1f  淨尖峰供電能力=%7.1f  比=%.3f' % d)
P('')

# ---- 21 個 B-only 欄位分類 ----
CAT = {}
for c in ['核一#1', '核一#2', '核二#1', '核二#2', '核三#1', '核三#2']:
    CAT[c + '(萬瓩)'] = ('核能', 'A檔範圍為火力+水力，不含核能電廠')
for c in ['和平#1', '和平#2', '麥寮#1', '麥寮#2', '麥寮#3', '海湖 (#1-#2)', '國光 #1',
          '新桃#1', '星彰#1', '星元#1', '嘉惠(#1~#2)', '豐德(#1-#3)']:
    CAT[c + '(萬瓩)'] = ('民營電廠IPP', '非台電自有機組，A檔不收錄')
CAT['汽電共生(萬瓩)'] = ('汽電共生', '外購汽電共生彙總，無機組明細')
CAT['風力發電(萬瓩)'] = ('再生能源彙總', '可對接 data.gov.tw/dataset/29961 風機統計表')
CAT['太陽能發電(萬瓩)'] = ('再生能源彙總', '可對接 data.gov.tw/dataset/29938 太陽光電統計表')

P('##### B 有、A 無 的 21 欄分類 #####')
for cat in ['核能', '民營電廠IPP', '汽電共生', '再生能源彙總']:
    cs = [c for c, (k, _) in CAT.items() if k == cat]
    P('  [%s] %d 欄: %s' % (cat, len(cs), ', '.join(c.replace('(萬瓩)', '') for c in cs)))
    P('      -> %s' % CAT[cs[0]][1])
P('')

# ---- A 檔已知缺漏（由容量缺口反推）----
GAPS = [
    ('大潭發電廠', '大潭#8、#9', 211.88, '2025-05 起出力階梯上升；A檔僅到#GT7'),
    ('大林發電廠', '大林#5', 27.90, 'B的大林(#5-#6)有值521天，A僅大六機'),
    ('興達發電廠', '興一機、興二機', 0.0, 'A無此兩機；B僅零星4/11天有值(試車或殘值)，實質已除役'),
]
P('##### A 檔已知缺漏機組（依容量缺口反推）#####')
for p, u, gap, why in GAPS:
    P('  %-10s 缺 %-14s 容量缺口≈%6.2f萬瓩   %s' % (p, u, gap, why))
P('')

# ---- 輸出長格式（可直接入庫 join）----
cw = list(csv.DictReader(open('crosswalk.csv', encoding='utf-8-sig')))
cwmap = {r['b_column']: r for r in cw}
n = 0
with io.open('daily_long.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['日期', 'b_column', '尖峰出力_萬瓩', 'a_plant', 'a_units',
                'n_units', 'cap_a_萬瓩', 'grain', 'category', 'confidence'])
    for r in data:
        for c in GEN:
            try:
                v = float(r[idx[c]])
            except Exception:
                continue
            m = cwmap.get(c)
            if m:
                grain = '單機' if m['n_units'] == '1' else '彙總'
                w.writerow([r[0], c.replace('(萬瓩)', ''), v, m['a_plant'], m['a_units'],
                            m['n_units'], m['cap_a_wankw'], grain, '台電自有', m['confidence']])
            else:
                cat, _ = CAT.get(c, ('未分類', ''))
                w.writerow([r[0], c.replace('(萬瓩)', ''), v, '', '', 0, '', '彙總', cat, '無對應'])
            n += 1
P('##### 輸出 #####')
P('  crosswalk.csv    對照表 44 列 (B欄位 -> A機組集合 + 容量驗證)')
P('  daily_long.csv   長格式 %d 列 (577天 x 64欄，已附掛對應資訊)' % n)
out.close()
print(io.open('final.txt', encoding='utf-8').read())
