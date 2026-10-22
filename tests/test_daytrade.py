"""15-minute reference scan is independent and never treats stale/incomplete bars as live."""
from datetime import timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pytest

from scanner.daytrade import drop_incomplete, scan_day_asset
from scanner.universe import Asset


def bars(n=160, down=False, volume=True):
    idx=pd.date_range("2026-10-19 00:00",periods=n,freq="15min",tz="UTC")
    trend=np.linspace(110,96,n) if down else np.linspace(95,109,n)
    op=trend-.05 if not down else trend+.05
    close=trend
    hi=np.maximum(op,close)+.25
    lo=np.minimum(op,close)-.25
    vol=np.full(n,10000.0 if volume else 0.0)
    return pd.DataFrame({"Open":op,"High":hi,"Low":lo,"Close":close,"Volume":vol},index=idx)


def now_at_end(df):
    return df.index[-1]+pd.Timedelta(minutes=25)


def test_daytrade_uses_only_completed_15min_bars():
    frame=bars()
    x=drop_incomplete(frame,now=frame.index[-1]+pd.Timedelta(minutes=7))
    assert len(x)==len(frame)-1
    assert x.index.tz is not None


def test_naive_15_minute_timestamp_is_rejected():
    frame=bars()
    frame.index=frame.index.tz_localize(None)
    with pytest.raises(ValueError,match="タイムゾーン"):
        drop_incomplete(frame)


def test_fx_no_stock_volume_and_has_directional_breakout_line():
    frame=bars(volume=False)
    a=Asset("SBI FX","米ドル/円","USDJPY=X")
    rows=scan_day_asset(a,frame,now=now_at_end(frame))
    assert len(rows)==2
    buy=next(r for r in rows if r["方向"]=="買い")
    assert buy["期間"]=="デイトレ"
    assert buy["出来高倍率"] is None
    assert buy["ブレイク基準情報"]["timeframe"]=="15分足（確定足）"
    assert buy["ブレイク基準情報"]["lookback_bars"]==12
    assert buy["ブレイク基準情報"]["reference_price"]>=frame["High"].iloc[-13:-1].max()-1e-6
    assert "株式出来高条件" not in buy["分析根拠"]
    assert "JST" in buy["基準日"]


def test_short_direction_has_lower_low_reference():
    frame=bars(down=True,volume=False)
    a=Asset("SBI CFD","小麦","ZW=F")
    rows=scan_day_asset(a,frame,now=now_at_end(frame))
    short=next(r for r in rows if r["方向"]=="ショート")
    line=short["ブレイク基準情報"]
    assert line["comparison"]=="<"
    assert line["reference_price"]==pytest.approx(frame["Low"].iloc[-13:-1].min())
    assert short["方向"]=="ショート"


def test_stale_data_forces_nontradeable_even_with_breakout():
    frame=bars(volume=False)
    frame.iloc[-1,frame.columns.get_loc("Close")]=frame.Close.iloc[-2]+3
    frame.iloc[-1,frame.columns.get_loc("High")]=frame.Close.iloc[-1]+0.25
    a=Asset("SBI FX","米ドル/円","USDJPY=X")
    rows=scan_day_asset(a,frame,now=frame.index[-1]+pd.Timedelta(hours=4))
    assert all(r["判定"]=="参考のみ（古い15分足）" for r in rows)
    assert all(r["エントリー適性"]==0 for r in rows)
    assert all("見送り" in r["エントリー判定"] for r in rows)


def test_cash_stock_requires_volume_and_session_vwap():
    frame=bars(volume=False)
    a=Asset("日本株","検証株","1234.T")
    rows=scan_day_asset(a,frame,now=now_at_end(frame))
    assert all("初動" not in r["判定"] for r in rows)
    assert all("出来高倍率" in r and r["出来高倍率"] is None for r in rows)
