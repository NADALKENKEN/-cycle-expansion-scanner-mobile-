"""Historical OHLCV: CSV override first, Yahoo public *reference* feed second."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import re
import pandas as pd
from scanner.indicators import prepare


ROOT=Path(__file__).resolve().parent.parent
DATA_DIR=ROOT/'data'/'ohlcv'


def safe_filename(asset):
    return re.sub(r'[^\w.-]+','_',f'{asset.market}__{asset.name}')+'.csv'


def read_csv_asset(asset, data_dir=DATA_DIR):
    path=Path(data_dir)/safe_filename(asset)
    if not path.exists():return None
    d=pd.read_csv(path, encoding='utf-8-sig')
    lower={c.lower().strip():c for c in d.columns}
    if 'date' not in lower:raise ValueError(f'{path.name}: Date列がありません')
    d['__date']=pd.to_datetime(d[lower['date']],errors='coerce',utc=True)
    d=d.set_index('__date')
    if d.index.isna().any():raise ValueError(f'{path.name}: 不正な日時')
    d=d.rename(columns={v:k for k,v in lower.items()})
    return prepare(d)


def as_completed_bars(d,market,now=None):
    """Drop only an apparent uncompleted *current-day* bar; don't invent bars."""
    if len(d)==0:return d
    now=now or datetime.now(ZoneInfo('Asia/Tokyo'))
    tz=ZoneInfo('America/New_York') if market=='米国株' else ZoneInfo('Asia/Tokyo')
    local=now.astimezone(tz)
    last=pd.Timestamp(d.index[-1]).date()
    # Use feed's native labelled trading dates; for FX and futures daily bars can roll at non-midnight.
    if market=='日本株' and last==local.date() and local.hour<16:
        return d.iloc[:-1]
    if market=='米国株' and last==local.date() and (local.hour<16 or (local.hour==16 and local.minute<25)):
        return d.iloc[:-1]
    if market in ('SBI FX','SBI CFD') and last==local.date():
        return d.iloc[:-1]
    return d


def split_ticker_frame(full,symbol):
    if full is None or full.empty:return pd.DataFrame()
    if isinstance(full.columns,pd.MultiIndex):
        lvl0=list(map(str,full.columns.get_level_values(0)))
        lvl1=list(map(str,full.columns.get_level_values(1)))
        if symbol in lvl0:d=full[symbol].copy()
        elif symbol in lvl1:d=full.xs(symbol,axis=1,level=1).copy()
        else:return pd.DataFrame()
    else:d=full.copy()
    try:
        d=prepare(d)
    except (ValueError,KeyError):return pd.DataFrame()
    if isinstance(d.index,pd.DatetimeIndex) and d.index.tz is not None:
        d.index=d.index.tz_localize(None)
    return d


def fetch_yahoo(assets,batch_size=24):
    """Retrieve reference prices; never asserts SBI-broker quotes, volume or availability."""
    import yfinance as yf
    symbols=list(dict.fromkeys([a.symbol for a in assets if a.symbol] +
        ['^GSPC','^TOPX','1306.T']))
    data={}; errors=[]
    for i in range(0,len(symbols),batch_size):
        part=symbols[i:i+batch_size]
        try:
            raw=yf.download(tickers=part,period='3y',interval='1d',group_by='ticker',
                            auto_adjust=True,progress=False,threads=False,timeout=15)
            for s in part:
                x=split_ticker_frame(raw,s)
                if len(x)>=240:data[s]=x
                else:errors.append(f'{s}: 取得不足/未対応（{len(x)}本）')
        except Exception as exc:
            errors.append('バッチ取得失敗: '+str(exc)[:120])
    # Try configured alternative symbols only for assets whose primary is missing.
    altmap={a.alt_symbol for a in assets if a.alt_symbol and a.symbol not in data}
    for alt in sorted(altmap):
        if alt in data:continue
        try:
            raw=yf.download(tickers=alt,period='3y',interval='1d',auto_adjust=True,progress=False,timeout=15)
            x=split_ticker_frame(raw,alt)
            if len(x)>=240:data[alt]=x
        except Exception as exc:errors.append(f'代替 {alt}: {str(exc)[:80]}')
    return data,errors


def load_ohlcv(assets, allow_yahoo=True):
    data={}; issues=[]; refs={}
    pending=[]
    for a in assets:
        try:
            csv_df=read_csv_asset(a)
            if csv_df is not None:
                data[(a.market,a.name)]=(as_completed_bars(csv_df,a.market),'CSV（利用者提供）')
                continue
        except Exception as exc:
            issues.append(f'{a.market}/{a.name}: CSVエラー {exc}')
            continue
        if allow_yahoo and (a.symbol or a.alt_symbol):pending.append(a)
        else:issues.append(f'{a.market}/{a.name}: CSVなし・参考ティッカー未設定')
    if pending:
        downloaded,errors=fetch_yahoo(pending)
        issues.extend(errors)
        refs={s:df for s,df in downloaded.items() if s in ('^GSPC','^TOPX','1306.T')}
        for a in pending:
            key=a.symbol if a.symbol in downloaded else a.alt_symbol
            if key and key in downloaded:
                d=as_completed_bars(downloaded[key],a.market)
                if d.empty:
                    issues.append(f'{a.market}/{a.name}: 完了済み日足がありません')
                    continue
                gap=(datetime.now(ZoneInfo('Asia/Tokyo')).date()-pd.Timestamp(d.index[-1]).date()).days
                if gap>7 or gap < -1:
                    issues.append(f'{a.market}/{a.name}: 古い/未来の参考価格（基準日 {pd.Timestamp(d.index[-1]).date()}）→売買候補に使用しません')
                    continue
                data[(a.market,a.name)]=(d,'Yahoo参考')
            else:
                issues.append(f'{a.market}/{a.name}: 有効な参考価格なし ({a.symbol})')
    return data,refs,issues


def confirm_four_hour(symbol,side):
    """Secondary confirmation only; reference Yahoo 1-hour bars regrouped in 4-hour blocks."""
    if not symbol:return '未取得'
    try:
        import yfinance as yf
        raw=yf.download(symbol,period='60d',interval='1h',auto_adjust=True,progress=False,timeout=15)
        d=split_ticker_frame(raw,symbol)
        if len(d)<90:return '未取得'
        # Require at least 3 hourly candles to avoid evaluating an incomplete block.
        count=d['close'].resample('4h').count()
        c=d['close'].resample('4h').last().loc[count>=3]
        if len(c)<30:return '未取得'
        e10=c.ewm(span=10,min_periods=10,adjust=False).mean()
        e20=c.ewm(span=20,min_periods=20,adjust=False).mean()
        is_up=c.iloc[-1]>e10.iloc[-1]>e20.iloc[-1]
        is_down=c.iloc[-1]<e10.iloc[-1]<e20.iloc[-1]
        return '一致' if (is_up if side=='買い' else is_down) else '不一致'
    except Exception:return '未取得'
