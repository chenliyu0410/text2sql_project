# -*- coding: utf-8 -*-
"""從台電開放資料端點重新抓取原始檔。

用法:  python fetch.py            # 抓 units.csv + daily.csv
       python fetch.py --extra    # 另外抓可選的擴充資料集

注意 daily.csv 是「滾動視窗」——台電只保留上一年度及今年度至上月份，
舊資料會被覆蓋。若要累積長期序列，請定期執行並自行封存（見 README「資料時效」）。
"""
import sys, os, csv, io, urllib.request, datetime

BASE = 'https://service.taipower.com.tw/data/opendata/apply/file/%s/001.%s'

CORE = [
    ('units.csv', 'd004011', 'csv', 8934,
     '水火力發電廠位置及機組設備（機組主檔，175台）'),
    ('daily.csv', 'd006005', 'csv', 19995,
     '過去電力供需資訊（每日尖峰，64機組欄位；滾動約2年）'),
]

EXTRA = [
    ('extra_reserve_3y.csv', 'd006004', 'csv', 24945,
     '近三年每日尖峰備轉容量率（僅3欄，但回溯到2023-01）'),
    ('extra_outage.csv', 'd006008', 'csv', None,
     '機組歲修/停機排程（事件表，可解釋出力為0的期間）'),
    ('extra_annual_peak.csv', 'd006013', 'csv', None,
     '歷年尖峰日（2021~，年粒度）'),
]


def get(name, fid, ext, dsid, desc):
    url = BASE % (fid, ext)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as r:
            blob = r.read()
    except Exception as e:
        print('  [失敗] %-24s %s' % (name, e))
        return
    old = os.path.getsize(name) if os.path.exists(name) else -1
    with open(name, 'wb') as f:
        f.write(blob)
    # 讀出日期範圍供核對
    rng = ''
    try:
        rows = [x for x in csv.reader(io.StringIO(blob.decode('utf-8-sig'))) if x and x[0].strip()]
        d = [x[0] for x in rows[1:] if x[0][:4].isdigit()]
        if d:
            rng = '  範圍 %s~%s (%d列)' % (min(d), max(d), len(d))
    except Exception:
        pass
    tag = '無變動' if old == len(blob) else ('新檔' if old < 0 else '已更新 %+d bytes' % (len(blob) - old))
    print('  [%s] %-24s %8d bytes  %s%s' % (tag, name, len(blob), fid, rng))
    if dsid:
        print('           https://data.gov.tw/dataset/%s' % dsid)


if __name__ == '__main__':
    print('抓取時間: %s\n' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print('核心檔案:')
    for a in CORE:
        get(*a)
    if '--extra' in sys.argv:
        print('\n擴充檔案:')
        for a in EXTRA:
            get(*a)
    print('\n完成。接著執行:  python align.py  &&  python final.py')
