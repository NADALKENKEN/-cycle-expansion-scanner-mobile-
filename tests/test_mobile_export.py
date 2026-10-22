import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from export_site import build_payload, normalize, write_payload
from scanner.universe import Asset


def test_json_contains_both_modes_and_no_nan(tmp_path):
    asset=Asset('日本株','検証銘柄','1234.T')
    idx=pd.date_range('2026-09-01',periods=3,freq='D')
    price=pd.DataFrame({'close':[101.0,102.0,103.0]},index=idx)
    signals=pd.DataFrame([
        {'市場':'日本株','銘柄':'検証銘柄','シンボル':'1234.T','期間':'短期','方向':'買い','判定':'買い初動','価格':103,'参考損切り':99,'参考利確2R':111,'スコア':75,'ATR':np.nan},
        {'市場':'日本株','銘柄':'検証銘柄','シンボル':'1234.T','期間':'中期','方向':'ショート','判定':'様子見','価格':103,'スコア':35,'ATR':np.inf},
    ])
    fixed=datetime(2026,10,22,12,30,tzinfo=ZoneInfo('Asia/Tokyo'))
    payload=build_payload([asset],signals,{('日本株','検証銘柄'):(price,'TEST')},['test issue'],clock=fixed)
    assert payload['meta']['assets_analyzed']==1
    assert {r['horizon'] for r in payload['rows']}=={'短期','中期'}
    assert payload['rows'][0]['atr'] is None
    assert payload['rows'][1]['atr'] is None
    assert len(payload['charts']['日本株::検証銘柄']['values'])==3
    path=write_payload(payload,tmp_path/'data'/'latest.json')
    reloaded=json.loads(path.read_text('utf-8'))
    assert len(reloaded['rows'])==2
    assert reloaded['meta']['issue_count']==1


def test_value_normalizer_rejects_nan_infinity():
    assert normalize(float('nan')) is None
    assert normalize(np.float64(np.inf)) is None
    assert normalize(np.int64(42))==42


def test_nested_explanation_json(tmp_path):
    asset=Asset('米国株','CHECK','CHECK')
    signals=pd.DataFrame([{'市場':'米国株','銘柄':'CHECK','シンボル':'CHECK',
        '期間':'短期','方向':'買い','判定':'買い準備',
        '分析根拠':['BBエクスパンション','RSI・MACD一致'],
        '根拠詳細':[{'name':'BBエクスパンション','detail':'前日比5%以上拡大'}],
        '未成立条件':['価格突破/押し目'],'主な根拠':'BBエクスパンション'}])
    frame=pd.DataFrame({'close':[120]},index=pd.date_range('2026-10-22',periods=1))
    payload=build_payload([asset],signals,{('米国株','CHECK'):(frame,'TEST')},[])
    row=payload['rows'][0]
    assert row['technical_tags']==['BBエクスパンション','RSI・MACD一致']
    assert row['technical_details'][0]['name']=='BBエクスパンション'
    assert row['missing_checks']==['価格突破/押し目']
    path=write_payload(payload,tmp_path/'latest.json')
    assert json.loads(path.read_text('utf-8'))['rows'][0]['technical_tags'][0]=='BBエクスパンション'


def test_mobile_report_includes_entry_suitability(tmp_path):
    asset=Asset('SBI CFD','小麦','ZW=F')
    signals=pd.DataFrame([{
        '市場':'SBI CFD','銘柄':'小麦','シンボル':'ZW=F',
        '期間':'短期','方向':'ショート','判定':'ショート初動',
        'スコア':100,'エントリー適性':33,
        'エントリー判定':'見送り（追いかけ注意）',
        'エントリー注意':['損切りが 4.73 ATR と非常に大きい。'],
    }])
    frame=pd.DataFrame({'close':[628.25]},index=pd.date_range('2026-10-21',periods=1))
    payload=build_payload([asset],signals,{('SBI CFD','小麦'):(frame,'TEST')},[])
    row=payload['rows'][0]
    assert row['score']==100
    assert row['entry_score']==33
    assert row['entry_state']=='見送り（追いかけ注意）'
    assert '4.73 ATR' in row['entry_notes'][0]
    path=write_payload(payload,tmp_path/'latest.json')
    after=json.loads(path.read_text(encoding='utf-8'))['rows'][0]
    assert after['entry_score']==33
    assert after['entry_notes']==row['entry_notes']


def test_mobile_json_includes_daily_breakout_line():
    from scanner.breakout import breakout_reference
    ref=breakout_reference(period='短期',side='買い',close=97.75,
        high_line=100,low_line=93,bb_upper=99.0,bb_lower=94,
        atr=2.5,bar_date='2026-10-21')
    signals=pd.DataFrame([{'市場':'日本株','銘柄':'CHECK','シンボル':'1234.T',
        '期間':'短期','方向':'買い','判定':'買い準備',
        'スコア':78,'エントリー判定':'ブレイク待ち',
        'ブレイク基準情報':ref}])
    a=Asset('日本株','CHECK','1234.T')
    frame=pd.DataFrame({'close':[97.75]},index=pd.date_range('2026-10-21',periods=1))
    out=build_payload([a],signals,{('日本株','CHECK'):(frame,'TEST')},[])
    row=out['rows'][0]
    assert row['breakout']['timeframe']=='日足（確定足）'
    assert row['breakout']['reference_price']==100
    assert row['breakout']['remaining_price']==2.25
    assert row['breakout']['bb_required'] is True
