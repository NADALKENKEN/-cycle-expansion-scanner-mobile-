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
