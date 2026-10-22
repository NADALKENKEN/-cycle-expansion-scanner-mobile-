import numpy as np
import pandas as pd
from scanner.universe import Asset,FX_NAMES,CFD,built_in,merge_user_csv
from scanner.indicators import add_indicators,prepare,weekly_trend
from scanner.engine import scan_asset,scan_universe
from scanner.data import as_completed_bars,safe_filename,read_csv_asset
from datetime import datetime
from zoneinfo import ZoneInfo


def prices(n=420,trend='up'):
    dates=pd.bdate_range('2024-01-02',periods=n)
    basis=100+np.arange(n)*(.14 if trend=='up' else -.14)
    wiggle=np.sin(np.arange(n)/3)*.33
    close=basis+wiggle
    op=close-.18 if trend=='up' else close+.18
    high=np.maximum(op,close)+.32
    low=np.minimum(op,close)-.32
    vol=np.full(n,1_000_000.0)
    return pd.DataFrame({'Open':op,'High':high,'Low':low,'Close':close,'Volume':vol},index=dates)


def test_market_coverage():
    a=built_in()
    assert len(FX_NAMES)==39
    assert len(CFD)==20
    assert len([v for v in a if v.market=='SBI FX'])==39
    assert len([v for v in a if v.market=='SBI CFD'])==20
    assert not next(v for v in a if v.name=='ロシアルーブル/円').enabled
    assert next(v for v in a if v.name=='中国A50').enabled


def test_breakout_uses_previous_bars_only():
    x=prices()
    x.iloc[-1,x.columns.get_loc('Close')]=x.Close.iloc[-2]+18
    x.iloc[-1,x.columns.get_loc('High')]=x.Close.iloc[-1]+.5
    x.iloc[-1,x.columns.get_loc('Volume')]=3_500_000
    d=add_indicators(x)
    assert d.iloc[-1].close>d.iloc[-1].high20
    assert d.iloc[-1].close>d.iloc[-1].bb_up
    assert d.iloc[-1].volume/d.iloc[-2]['volume']>3
    a=Asset('日本株','架空検証銘柄','TEST.T')
    rows=scan_asset(a,x,'短期',feed='TEST')
    buy=next(y for y in rows if y['方向']=='買い')
    assert buy['判定']=='要確認（損切幅過大）',buy
    assert buy['参考損切り']<buy['価格']<buy['参考利確2R']
    assert abs((buy['参考利確2R']-buy['価格'])/(buy['価格']-buy['参考損切り'])-2)<1e-8


def test_breakdown_short():
    x=prices(trend='down')
    x.iloc[-1,x.columns.get_loc('Close')]=x.Close.iloc[-2]-12
    x.iloc[-1,x.columns.get_loc('Low')]=x.Close.iloc[-1]-.5
    x.iloc[-1,x.columns.get_loc('Volume')]=3_000_000
    a=Asset('米国株','TEST','TEST')
    rows=scan_asset(a,x,'短期')
    short=next(y for y in rows if y['方向']=='ショート')
    assert short['判定']=='要確認（損切幅過大）',short
    assert short['参考利確2R']<short['価格']<short['参考損切り']


def test_no_volume_no_stock_breakout():
    x=prices()
    x.iloc[-1,x.columns.get_loc('Close')]=x.Close.iloc[-2]+18
    x.iloc[-1,x.columns.get_loc('High')]=x.Close.iloc[-1]+.5
    x['Volume']=0
    rows=scan_asset(Asset('日本株','ABC','ABC.T'),x,'短期')
    buy=next(y for y in rows if y['方向']=='買い')
    assert buy['判定']!='買い初動'


def test_fx_no_volume_and_independent_modes():
    x=prices()
    x['Volume']=0
    result=scan_asset(Asset('SBI FX','米ドル/円','USDJPY=X'),x,'短期')
    assert len(result)==2
    assert all(row['出来高倍率'] is None for row in result)
    assert 'SBI FX' in result[0]['市場']
    assert all(row['期間']=='短期' for row in result)
    med=scan_asset(Asset('SBI FX','米ドル/円','USDJPY=X'),x,'中期')
    assert len(med)==2 and all(row['期間']=='中期' for row in med)


def test_csv_override_priority(tmp_path):
    asset=Asset('SBI CFD','中国A50','')
    fn=tmp_path/safe_filename(asset)
    d=prices(300)
    d.index.name='Date'
    d.to_csv(fn)
    parsed=read_csv_asset(asset,tmp_path)
    assert len(parsed)==300
    assert parsed['close'].iloc[-1]>0


def test_universe_csv_safety():
    initial=built_in()
    blob='market,name,symbol,alt_symbol,note,enabled\n日本株,サンプル,1234.T,,,1\n不明,危険,ABC,,,1\n'
    out=merge_user_csv(blob,initial)
    assert next(v for v in out if v.name=='サンプル').symbol=='1234.T'
    assert not any(v.name=='危険' for v in out)


def test_ignore_incomplete_japan_bar():
    x=prepare(prices(260))
    dt=x.index[-1]
    now=datetime(dt.year,dt.month,dt.day,11,0,tzinfo=ZoneInfo('Asia/Tokyo'))
    assert len(as_completed_bars(x,'日本株',now))==len(x)-1


def test_batch_scan_both_modes():
    a=Asset('SBI FX','米ドル/円','USDJPY=X')
    d=prices()
    x,errors=scan_universe([a],{('SBI FX','米ドル/円'):(d,'TEST')},periods=('短期','中期'))
    assert len(x)==4 and not errors
    assert set(x.期間)=={'短期','中期'}


def test_moderate_breakout_is_actionable():
    x=prices()
    x.iloc[-1,x.columns.get_loc('Close')]=x.Close.iloc[-2]+2.2
    x.iloc[-1,x.columns.get_loc('High')]=x.Close.iloc[-1]+.5
    x.iloc[-1,x.columns.get_loc('Volume')]=3_500_000
    rows=scan_asset(Asset('日本株','TEST','TEST.T'),x,'短期')
    buy=next(y for y in rows if y['方向']=='買い')
    assert buy['判定']=='買い初動',buy
    assert buy['損切幅ATR']<=5


def test_output_includes_cycle_and_wyckoff_proxy():
    rows=scan_asset(Asset('日本株','CHECK','CHECK.T'),prices(),'中期')
    for r in rows:
        assert r['完了サイクル'] in ('ライト傾向','レフト傾向','中立','判定不足')
        assert r['ワイコフ類似'] in ('蓄積候補の上放れ','分配候補の下放れ','未検出')


def test_explanations_expansion_breakout_and_direction():
    x=prices()
    x.iloc[-1,x.columns.get_loc('Close')]=x.Close.iloc[-2]+2.2
    x.iloc[-1,x.columns.get_loc('High')]=x.Close.iloc[-1]+.5
    x.iloc[-1,x.columns.get_loc('Volume')]=3_500_000
    rows=scan_asset(Asset('日本株','TEST','TEST.T'),x,'短期')
    buy=next(r for r in rows if r['方向']=='買い')
    sell=next(r for r in rows if r['方向']=='ショート')
    assert '高値ブレイク' in buy['分析根拠']
    assert '高値ブレイク' not in sell['分析根拠']
    assert buy['主な根拠']=='高値ブレイク'
    assert 'BBエクスパンション' in buy['分析根拠']
    assert all(isinstance(v,dict) and v['name'] and v['detail'] for v in buy['根拠詳細'])
    assert isinstance(buy['未成立条件'],list)


def test_explanations_do_not_claim_broker_volume():
    x=prices()
    x['Volume']=0
    rows=scan_asset(Asset('SBI FX','米ドル/円','USDJPY=X'),x,'短期')
    assert all('株式出来高条件' not in r['分析根拠'] for r in rows)


def test_scanner_breakout_reference_matches_actual_daily_bars():
    x=prices()
    asset=Asset('SBI FX','米ドル/円','USDJPY=X')
    short=scan_asset(asset,x,'短期')
    med=scan_asset(asset,x,'中期')
    buy=next(r for r in short if r['方向']=='買い')
    sell=next(r for r in med if r['方向']=='ショート')
    shortline=add_indicators(x).iloc[-1]['high20']
    mediumline=add_indicators(x).iloc[-1]['low55']
    assert buy['ブレイク基準情報']['reference_price']==shortline
    assert buy['ブレイク基準情報']['lookback_bars']==20
    assert buy['ブレイク基準情報']['timeframe']=='日足（確定足）'
    assert sell['ブレイク基準情報']['reference_price']==mediumline
    assert sell['ブレイク基準情報']['lookback_bars']==55
    assert sell['ブレイク基準情報']['comparison']=='<'


def test_partial_price_break_does_not_claim_full_short_term_signal():
    x=prices()
    asset=Asset('日本株','TEST','TEST.T')
    rows=scan_asset(asset,x,'短期')
    for r in rows:
        b=r['ブレイク基準情報']
        assert b['complete']==bool(
            r['価格']>b['reference_price'] and r['価格']>b['bb_reference']
            if r['方向']=='買い' else
            r['価格']<b['reference_price'] and r['価格']<b['bb_reference']
        )
