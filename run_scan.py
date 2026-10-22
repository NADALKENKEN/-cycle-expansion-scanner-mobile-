"""Batch command for an isolated repository or local Task Scheduler."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import requests
from scanner.universe import built_in,merge_user_csv
from scanner.data import load_ohlcv
from scanner.engine import scan_universe

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'data'/'notification_state.json'


def notify_new(rows):
    token=os.environ.get('PUSHOVER_APP_TOKEN','')
    user=os.environ.get('PUSHOVER_USER_KEY','')
    if not (token and user):
        print('通知は未設定です（PUSHOVER_APP_TOKENとPUSHOVER_USER_KEY）。')
        return
    STATE.parent.mkdir(parents=True,exist_ok=True)
    try:sent=set(json.loads(STATE.read_text('utf-8'))) if STATE.exists() else set()
    except (OSError,json.JSONDecodeError):sent=set()
    success_count=0
    # Notify breakout signals only; ready/watchlist is left in the report.
    for _,r in rows[rows['判定'].isin(['買い初動','ショート初動'])].iterrows():
        key='|'.join(map(str,[r['基準日'],r['期間'],r['市場'],r['銘柄'],r['方向']]))
        if key in sent:continue
        msg=f"{r['期間']} {r['市場']} {r['銘柄']} {r['判定']} スコア{r['スコア']} 基準価格{r['価格']:.6g} 損切{r['参考損切り']:.6g} 2R目標{r['参考利確2R']:.6g}\n※参考相場。実際のSBI価格・建玉条件は要確認"
        try:
            res=requests.post('https://api.pushover.net/1/messages.json',data={'token':token,'user':user,'title':'独立マルチ市場スキャナー','message':msg},timeout=15)
            res.raise_for_status()
            sent.add(key);success_count+=1
        except requests.RequestException as exc:
            print(f'通知に失敗: {exc}')
    STATE.write_text(json.dumps(sorted(sent)[-15000:],ensure_ascii=False,indent=2),'utf-8')
    print(f'通知成功: {success_count}件')


def main():
    p=argparse.ArgumentParser(description='Standalone multi-market swing scanner')
    p.add_argument('--period',choices=['short','medium','both'],default='both')
    p.add_argument('--markets',nargs='+',choices=['JP','US','FX','CFD'],default=['JP','US','FX','CFD'])
    p.add_argument('--universe',default='',help='market,name,symbol列を含むCSVパス')
    p.add_argument('--notify',action='store_true',help='通知設定済みの時だけPushoverへ新規シグナル送信')
    args=p.parse_args()
    mapping={'JP':'日本株','US':'米国株','FX':'SBI FX','CFD':'SBI CFD'}
    assets=built_in()
    if args.universe:
        path=Path(args.universe)
        assets=merge_user_csv(path.read_bytes(),assets)
    assets=[a for a in assets if a.enabled and a.market in [mapping[m] for m in args.markets]]
    periods={'short':['短期'],'medium':['中期'],'both':['短期','中期']}[args.period]
    print(f'スキャン開始: {len(assets)}商品 / {periods} / {datetime.now()}')
    data,refs,errors=load_ohlcv(assets)
    signals,issues=scan_universe(assets,data,refs,periods)
    out=ROOT/'output';out.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M')
    file=out/f'latest_{stamp}.csv'
    signals.to_csv(file,index=False,encoding='utf-8-sig')
    (out/f'issues_{stamp}.txt').write_text('\n'.join(errors+issues),encoding='utf-8')
    print(f'分析結果: {len(signals)}行（方向別・期間別）保存先: {file}')
    if len(signals):
        print(signals[signals['判定']!='様子見'][['市場','銘柄','期間','判定','スコア','価格']].head(50).to_string(index=False))
        if args.notify:notify_new(signals)
    elif args.notify:print('通知なし: 評価できるデータがありません')
    print(f'データ/解析の問題: {len(errors+issues)}件（詳細はissuesファイル）')

if __name__=='__main__':main()
