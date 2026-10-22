"""Technical indicators, no lookahead: breakout reference is strictly prior bars."""
import numpy as np
import pandas as pd


def prepare(df):
    frame=df.copy()
    frame.columns=[str(x).strip().lower() for x in frame.columns]
    for field in ('open','high','low','close'):
        if field not in frame:
            raise ValueError(f'{field}列がありません')
        frame[field]=pd.to_numeric(frame[field],errors='coerce')
    if 'volume' not in frame:
        frame['volume']=np.nan
    frame['volume']=pd.to_numeric(frame['volume'],errors='coerce')
    frame=frame.replace([np.inf,-np.inf],np.nan).dropna(subset=['open','high','low','close'])
    frame=frame[(frame['close']>0)&(frame['high']>=frame['low'])&(frame['high']>=frame[['open','close']].max(axis=1))&(frame['low']<=frame[['open','close']].min(axis=1))]
    frame=frame[~frame.index.duplicated(keep='last')].sort_index()
    return frame


def add_indicators(df):
    d=prepare(df)
    c=d['close']; h=d['high']; l=d['low']
    for n in (10,20,50,200): d[f'ema{n}']=c.ewm(span=n,adjust=False,min_periods=n).mean()
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    d['atr']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    sma=c.rolling(20).mean(); std=c.rolling(20).std(ddof=0)
    d['bb_mid']=sma;d['bb_up']=sma+2*std;d['bb_lo']=sma-2*std
    d['bb_width']=(4*std/sma.replace(0,np.nan))
    # Prior 120 observations so percentile has no forward information.
    d['bb_pct']=d['bb_width'].rolling(120,min_periods=80).apply(lambda a: float((a <= a[-1]).sum())/len(a)*100,raw=True)
    d['high20']=h.shift(1).rolling(20).max(); d['low20']=l.shift(1).rolling(20).min()
    d['high55']=h.shift(1).rolling(55).max(); d['low55']=l.shift(1).rolling(55).min()
    d['vol_ratio']=d['volume']/d['volume'].shift(1).rolling(20).mean().replace(0,np.nan)
    delta=c.diff();up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    dn=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d['rsi']=100-100/(1+up/dn.replace(0,np.nan))
    d.loc[(dn==0)&(up>0),'rsi']=100
    d.loc[(up==0)&(dn>0),'rsi']=0
    d['rsi']=d['rsi'].fillna(50)
    macd=c.ewm(span=12,adjust=False,min_periods=26).mean()-c.ewm(span=26,adjust=False,min_periods=26).mean()
    sig=macd.ewm(span=9,adjust=False,min_periods=9).mean()
    d['macd_hist']=macd-sig
    return d


def weekly_trend(d):
    ohlcv=d[['open','high','low','close','volume']].resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna(subset=['close'])
    if len(ohlcv)<30:return 0,0
    # Remove last uncompleted calendar week to avoid weekly lookahead when scanning midweek.
    last=ohlcv.index[-1]
    ref=pd.Timestamp(d.index[-1]).normalize()
    if last.normalize()>ref:
        ohlcv=ohlcv.iloc[:-1]
    if len(ohlcv)<30:return 0,0
    wk=ohlcv['close'];w10=wk.ewm(span=10,adjust=False,min_periods=10).mean()
    bullish=wk.iloc[-1]>w10.iloc[-1] and w10.iloc[-1]>w10.iloc[-4]
    bearish=wk.iloc[-1]<w10.iloc[-1] and w10.iloc[-1]<w10.iloc[-4]
    return int(bullish),int(bearish)


def completed_cycle_translation(d,period='短期'):
    """Heuristic completed low-to-low cycle; never label a forming future cycle.

    Symmetric 3/5-bar pivot confirmation introduces delay (intentionally).
    It is not a forecast of the next peak nor a canonical cycle-length estimator.
    """
    pivot=3 if period=='短期' else 5
    min_len,max_len=(10,50) if period=='短期' else (20,110)
    low=d['low'].to_numpy(dtype=float)
    close=d['close'].to_numpy(dtype=float)
    n=len(d)
    points=[]
    # Exclude unconfirmed most-recent observations.
    for i in range(pivot,n-pivot):
        if low[i]<np.min(low[i-pivot:i]) and low[i]<=np.min(low[i+1:i+pivot+1]):
            points.append(i)
    for b in range(len(points)-1,0,-1):
        i,j=points[b-1],points[b]
        duration=j-i
        if not min_len<=duration<=max_len:continue
        peak=i+int(np.argmax(close[i:j+1]))
        location=(peak-i)/duration
        rising_low=low[j]>low[i]
        falling_low=low[j]<low[i]
        if location>=0.55 and rising_low:return 'ライト傾向',round(location*100)
        if location<=0.45 and falling_low:return 'レフト傾向',round(location*100)
        return '中立',round(location*100)
    return '判定不足',None
