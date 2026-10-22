"""Independent 15-minute day-trading scanner using delayed public reference data.

No brokerage connection, live alerts or intraday order execution.
Every signal is based on a COMPLETED 15-minute OHLCV bar. Stale
instruments cannot qualify as trading candidates.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

from scanner.indicators import prepare
from scanner.entry import assess_entry

BAR_MINUTES = 15
LOOKBACK = 12                 # Previous 12 completed 15-minute bars (3 trading hours)
MAX_AGE_MINUTES = 90          # Old/closed-session prices never become active signals
PERIOD = "デイトレ"
JST = ZoneInfo("Asia/Tokyo")


def _index_utc(frame):
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("15分足のタイムゾーン不明（UTC時刻が必要です）")
    out = prepare(frame)
    out.index = out.index.tz_convert("UTC")
    return out


def drop_incomplete(frame, now=None):
    """Yahoo timestamps are bar START times; cut off a still-forming bar."""
    d = _index_utc(frame)
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.tz_convert("UTC")
    return d.loc[d.index + pd.Timedelta(minutes=BAR_MINUTES + 2) <= now].copy()


def _rsi(series, n=14):
    diff = series.diff()
    up = diff.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    out = 100-100/(1+up/down.replace(0,np.nan))
    out.loc[(down==0)&(up>0)] = 100
    out.loc[(up==0)&(down>0)] = 0
    return out.fillna(50)


def _intraday_vwap(d, market):
    """Only cash-stock trading-session VWAP; no imaginary FX/CFD volume."""
    if market not in ("日本株", "米国株"):
        return None
    local_zone = "Asia/Tokyo" if market=="日本株" else "America/New_York"
    session = d.index.tz_convert(local_zone).date
    latest = session[-1]
    current = d.loc[session==latest]
    volume = current["volume"].fillna(0).clip(lower=0)
    if len(current)<2 or volume.sum()<=0:
        return None
    typical=(current["high"]+current["low"]+current["close"])/3
    return float((typical*volume).sum()/volume.sum())


def scan_day_asset(asset, frame, now=None, feed="Yahoo 15分足参考"):
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert("UTC")
    d = drop_incomplete(frame, now=now)
    if len(d)<85:
        raise ValueError(f"完了済み15分足不足：{len(d)}本（85本必要）")
    age_minutes = max(0.0, (now-d.index[-1]).total_seconds()/60 - BAR_MINUTES)
    fresh = age_minutes<=MAX_AGE_MINUTES
    c=d["close"];h=d["high"];l=d["low"]
    ema9=c.ewm(span=9,adjust=False,min_periods=9).mean()
    ema21=c.ewm(span=21,adjust=False,min_periods=21).mean()
    rsi=_rsi(c)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    sma=c.rolling(20).mean();sd=c.rolling(20).std(ddof=0)
    bb_width=4*sd/sma.replace(0,np.nan)
    expansion=bool(bb_width.iloc[-1]>bb_width.iloc[-2]*1.05)
    prior_contraction=bool(bb_width.iloc[-13:-1].min()<=bb_width.iloc[-13:-1].median()*0.85)
    hi=float(h.shift().rolling(LOOKBACK).max().iloc[-1])
    lo=float(l.shift().rolling(LOOKBACK).min().iloc[-1])
    price=float(c.iloc[-1])
    atr_now=float(atr.iloc[-1])
    if not all(np.isfinite([hi,lo,price,atr_now])) or atr_now<=0:
        raise ValueError("15分足の価格・ATRを判定できません")
    vr=None
    if asset.market in ("日本株","米国株"):
        recent=d["volume"].iloc[-21:]
        baseline=recent.iloc[:-1].replace(0,np.nan).mean()
        if pd.notna(baseline) and baseline>0 and recent.iloc[-1]>0:
            vr=float(recent.iloc[-1]/baseline)
    vwap=_intraday_vwap(d,asset.market)
    timestamp=(d.index[-1]+pd.Timedelta(minutes=BAR_MINUTES)).tz_convert(JST)
    bar_label=timestamp.strftime("%Y-%m-%d %H:%M JST")
    note=(asset.note or "") + " ／ 15分足はYahoo等の遅延参考値。SBI提示価格・約定条件と異なります。"
    rows=[]
    for side in ("買い","ショート"):
        buy=side=="買い"
        trend=bool(price>ema9.iloc[-1]>ema21.iloc[-1]) if buy else bool(price<ema9.iloc[-1]<ema21.iloc[-1])
        mom=bool(rsi.iloc[-1]>52) if buy else bool(rsi.iloc[-1]<48)
        line=hi if buy else lo
        hit=bool(price>line) if buy else bool(price<line)
        dist=(line-price)/atr_now if buy else (price-line)/atr_now
        near=0<=dist<=0.6
        vol_ok=asset.market not in ("日本株","米国株") or (vr is not None and vr>=1.25)
        vwap_ok=((price>vwap if buy else price<vwap) if vwap is not None else False) if asset.market in ("日本株","米国株") else True
        checks=[
            ("15分足EMA9/21方向一致",trend,27),
            ("直前12本の高安突破",hit,27),
            ("RSI方向一致",mom,13),
            ("BB拡大/収縮",bool(expansion or prior_contraction),9),
        ]
        if asset.market in ("日本株","米国株"):
            checks += [("株式15分出来高1.25倍",bool(vol_ok),13)]
            checks += [("当日VWAP方向一致",bool(vwap_ok),11)]
        score=round(100*sum(w for _,ok,w in checks if ok)/sum(w for _,ok,w in checks))
        confirmed=bool(fresh and trend and mom and hit and vol_ok and vwap_ok and score>=65)
        ready=bool(fresh and trend and mom and near and vol_ok and score>=55)
        status=side+"初動" if confirmed else side+"準備" if ready else "様子見"
        swing_low=float(l.iloc[-13:-1].min())
        swing_high=float(h.iloc[-13:-1].max())
        stop=min(price-atr_now,swing_low-0.15*atr_now) if buy else max(price+atr_now,swing_high+0.15*atr_now)
        target=price+2*(price-stop) if buy else price-2*(stop-price)
        risk_atr=abs(stop-price)/atr_now
        if risk_atr>3 or target<=0:
            if confirmed or ready:status="要確認（損切幅過大）"
        e_score,e_state,e_reasons=assess_entry(
            side=side,trend=trend,momentum=mom,confirmed=confirmed,ready=ready,hit=hit,
            pull=False,expansion=expansion,risk_atr=risk_atr,price=price,
            stop=stop,ema20=float(ema21.iloc[-1]),atr=atr_now,rsi=float(rsi.iloc[-1]),
            breakout_level=line)
        if not fresh:
            status="参考のみ（古い15分足）"
            e_state="時間外・更新遅延（見送り）"
            e_score=0
            e_reasons=[f"最後の確定15分足から約{age_minutes:.0f}分。90分以内のデータのみ候補対象。"]
        elif risk_atr>3 or target<=0:
            e_state="見送り（損切幅過大）"
        terms=[
            ("15分足高値ブレイク" if buy else "15分足安値ブレイク",hit,
             f"15分足終値が直前12本の{'高値' if buy else '安値'} {line:g} を{'上回る' if buy else '下回る'}"),
            ("EMA9/21方向一致",trend,"15分足のEMA9/21と終値の並びが一致"),
            ("15分足RSI方向",mom,f"RSI14＝{rsi.iloc[-1]:.1f}"),
            ("BBエクスパンション",expansion,"15分足BB幅が直前の確定足から5%以上拡大"),
            ("BBスクイーズ後（近似）",prior_contraction,"直前12本内で相対的な収縮を確認"),
            ("株式出来高条件",asset.market in ("日本株","米国株") and vol_ok,
             f"直前20本平均比 {vr:.2f}倍" if vr is not None else "データなし"),
            ("セッションVWAP方向一致",vwap is not None and vwap_ok,
             f"取引セッションVWAP {vwap:g} と一致" if vwap is not None else "対象外"),
        ]
        details=[{"name":name,"detail":description} for name,ok,description in terms if ok]
        tags=[item["name"] for item in details]
        main=("15分足高値ブレイク" if buy else "15分足安値ブレイク") if hit else ("ブレイク接近" if near else "EMA9/21トレンド")
        breakout={
            "timeframe":"15分足（確定足）",
            "lookback_bars":LOOKBACK,
            "line_name":f"直前{LOOKBACK}本の"+("最高値" if buy else "最安値"),
            "reference_price":line,
            "comparison":">" if buy else "<",
            "direction":"上抜け" if buy else "下抜け",
            "price_crossed":hit,
            "bb_required":False,"bb_name":None,"bb_reference":None,"bb_passed":None,
            "complete":hit,
            "state":"価格ライン突破済み" if hit else "ブレイク未成立（15分足終値待ち）",
            "remaining_price":max(0.,line-price if buy else price-line),
            "remaining_pct":100*max(0.,line-price if buy else price-line)/price,
            "remaining_atr":max(0.,line-price if buy else price-line)/atr_now,
            "rule":f"確定した15分足終値が直前{LOOKBACK}本の"+("高値" if buy else "安値")+
                   f" {line:g} を厳密に"+("上回る" if buy else "下回る")+
                   "。EMA9/21・RSI、株式なら出来高/VWAPも別途確認。",
            "as_of":bar_label,
            "caution":"値は15分ごとに変動。公開参考値、約定レートではありません。15分足の終値確定が必要。",
        }
        rows.append(dict(
            市場=asset.market,銘柄=asset.name,シンボル=asset.symbol,期間=PERIOD,
            方向=side,判定=status,スコア=score,エントリー適性=e_score,
            エントリー判定=e_state,エントリー注意=e_reasons,
            価格=price,基準日=bar_label,参考エントリー=price,参考損切り=stop,
            参考利確2R=target,損切幅ATR=round(risk_atr,2),ATR=atr_now,
            RSI=round(float(rsi.iloc[-1]),1),出来高倍率=round(vr,2) if vr is not None else None,
            相対強度20日=None,BB幅パーセンタイル=None,完了サイクル="15分足は対象外",
            サイクル高値位置パーセント=None,ワイコフ類似="未評価",
            上値突破基準=hi,下値割れ基準=lo,週足方向="-",
            検証条件=" / ".join(name for name,ok,_ in checks if ok),
            主な根拠=main,分析根拠=tags,根拠詳細=details,
            未成立条件=[name for name,ok,_ in checks if not ok],ブレイク基準情報=breakout,
            データ=feed,注意=note,
        ))
    return rows


def load_day_prices(assets, now=None, batch_size=18):
    """1-month public intraday history, UTC-indexed; fresh bars only for active candidates."""
    import yfinance as yf
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    data={}; errors=[]
    requested=list(dict.fromkeys(a.symbol for a in assets if a.symbol))
    symbols={}
    for i in range(0,len(requested),batch_size):
        batch=requested[i:i+batch_size]
        try:
            raw=yf.download(tickers=batch,period="1mo",interval="15m",group_by="ticker",
                auto_adjust=True,prepost=False,progress=False,threads=False,timeout=15)
            for sym in batch:
                try:
                    if raw is None or raw.empty:raise ValueError("価格履歴なし")
                    if isinstance(raw.columns,pd.MultiIndex):
                        levels=[raw.columns.get_level_values(n).astype(str) for n in range(raw.columns.nlevels)]
                        level=next((n for n,v in enumerate(levels) if sym in v),None)
                        if level is None:raise ValueError("ティッカーが返却されていません")
                        part=raw.xs(sym,axis=1,level=level).copy()
                    else:
                        part=raw.copy()
                    part=_index_utc(part)
                    part=drop_incomplete(part, now=now)
                    if len(part)<85:raise ValueError(f"確定15分足不足 {len(part)}本")
                    symbols[sym]=part
                except Exception as exc:
                    errors.append(f"デイトレ {sym}: {str(exc)[:100]}")
        except Exception as exc:
            errors.append("デイトレ一括取得失敗 "+str(exc)[:130])
    for a in assets:
        part=symbols.get(a.symbol)
        if part is None and a.alt_symbol:
            part=symbols.get(a.alt_symbol)  # no extra request; do not invent an equivalent
        if part is not None:
            data[(a.market,a.name)]=(part,"Yahoo 15分足参考")
        else:
            if not a.symbol:errors.append(f"デイトレ {a.name}: 参照ティッカー未設定")
    return data,errors


def scan_day_universe(assets,frames,now=None):
    rows=[];issues=[]
    for a in assets:
        pair=frames.get((a.market,a.name))
        if pair is None:continue
        try:rows.extend(scan_day_asset(a,pair[0],now=now,feed=pair[1]))
        except Exception as exc:issues.append(f"デイトレ {a.name}: {str(exc)[:120]}")
    return pd.DataFrame(rows),issues
