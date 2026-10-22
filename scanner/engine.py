"""Deterministic, independently configurable short- and medium-term signal engine."""
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from scanner.indicators import add_indicators, weekly_trend, completed_cycle_translation
from scanner.entry import assess_entry
from scanner.breakout import breakout_reference

CONFIG={
 '短期':dict(lookback=20,near_atr=0.65,trigger_score=68,ready_score=55),
 '中期':dict(lookback=55,near_atr=1.15,trigger_score=68,ready_score=55),
}

def numerical(x,default=0.0):
    try:
        v=float(x)
        return v if np.isfinite(v) else default
    except (ValueError,TypeError):return default


def rs_metric(frame,benchmark):
    if benchmark is None or len(benchmark)<30:return None
    # Use equal observed dates to avoid cross-market lookahead.
    tmp=pd.concat([frame['close'].rename('a'),benchmark['close'].rename('b')],axis=1,join='inner').dropna()
    if len(tmp)<25:return None
    return 100*((tmp['a'].iloc[-1]/tmp['a'].iloc[-21])- (tmp['b'].iloc[-1]/tmp['b'].iloc[-21]))


def scan_asset(asset,frame,period='短期',benchmark=None,feed='Yahoo参考'):
    if period not in CONFIG:raise ValueError('短期/中期を指定してください')
    d=add_indicators(frame)
    if len(d)<240:raise ValueError('必要本数240本以上（EMA200等）')
    a=d.iloc[-1];p=d.iloc[-2];c=numerical(a['close']);atr=numerical(a['atr'])
    if c<=0 or atr<=0:raise ValueError('価格またはATRが不正')
    cfg=CONFIG[period];lb=cfg['lookback']
    hi=numerical(a[f'high{lb}']);lo=numerical(a[f'low{lb}'])
    bb=numerical(a['bb_width']);pb=numerical(p['bb_width'])
    pct=numerical(a['bb_pct'],100)
    prior_squeeze=d['bb_pct'].iloc[-13:-1].min()<25
    expansion=bb>pb*1.05
    rs=rs_metric(d,benchmark) if asset.market in ('日本株','米国株') else None
    has_vol=asset.market in ('日本株','米国株')
    vratio=numerical(a['vol_ratio']) if has_vol and np.isfinite(a['vol_ratio']) and a['vol_ratio']>0 else None
    wlong,wshort=weekly_trend(d) if period=='中期' else (0,0)
    cycle,cycle_peak_pct=completed_cycle_translation(d,period)
    med=period=='中期'
    # Short: fast trend and breakout; Medium: 50/200 EMA & confirmed weekly trend.
    bullish=(c>numerical(a['ema20']) and a['ema20']>a['ema50'] and a['ema20']>d['ema20'].iloc[-6]) if not med else (c>a['ema50'] and a['ema50']>a['ema200'] and wlong==1)
    bearish=(c<numerical(a['ema20']) and a['ema20']<a['ema50'] and a['ema20']<d['ema20'].iloc[-6]) if not med else (c<a['ema50'] and a['ema50']<a['ema200'] and wshort==1)
    momup=numerical(a['rsi'])>50 and numerical(a['macd_hist'])>0
    momdn=numerical(a['rsi'])<50 and numerical(a['macd_hist'])<0
    hitup=c>hi and c>numerical(a['bb_up']) if not med else c>hi
    hitdn=c<lo and c<numerical(a['bb_lo']) if not med else c<lo
    # Wyckoff-*like* break from contraction. Not a definitive accumulation/distribution identification.
    wyckoff_up=bool(prior_squeeze and hitup)
    wyckoff_dn=bool(prior_squeeze and hitdn)
    # Medium has an alternate, EMA20 reaction / pullback signal; no same-bar data leakage.
    pullup=med and c>a['ema20'] and p['close']>=p['ema50'] and a['low']<=a['ema20']+0.2*atr and c>a['open']
    pulldn=med and c<a['ema20'] and p['close']<=p['ema50'] and a['high']>=a['ema20']-0.2*atr and c<a['open']
    candidates=[]
    for side in ('買い','ショート'):
        trend=bullish if side=='買い' else bearish
        hit=hitup if side=='買い' else hitdn
        pull=pullup if side=='買い' else pulldn
        mom=momup if side=='買い' else momdn
        vol_threshold=0.8 if med and pull else 1.5
        vol_ok=(not has_vol) or (vratio is not None and vratio>=vol_threshold)
        dist=(hi-c)/atr if side=='買い' else (c-lo)/atr
        near=0<=dist<=cfg['near_atr']
        rso=(rs is not None and (rs>0 if side=='買い' else rs<0))
        checks=[('トレンド',bool(trend),24),('価格突破/押し目',bool(hit or pull),27),
                ('BB拡大または直近収縮',bool(expansion or prior_squeeze),12),('RSI・MACD',bool(mom),12)]
        if rs is not None:checks.append(('相対的強さ',bool(rso),8))
        if has_vol:checks.append(('株式出来高'+ ('0.8倍（押し目）' if med and pull else '1.5倍'),bool(vol_ok),10))
        if med:checks.append(('週足一致',bool(wlong if side=='買い' else wshort),7))
        if cycle!='判定不足':checks.append(('完了サイクル方向',cycle==('ライト傾向' if side=='買い' else 'レフト傾向'),7))
        checks.append(('蓄積/分配類似ブレイク',wyckoff_up if side=='買い' else wyckoff_dn,7))
        score=round(100*sum(weight for _,passed,weight in checks if passed)/sum(weight for _,_,weight in checks))
        confirmed=bool(trend and mom and (hit or (pull and med)) and vol_ok and score>=cfg['trigger_score'] and (med or expansion or prior_squeeze))
        ready=bool(trend and mom and near and score>=cfg['ready_score'])
        status=(side+'初動') if confirmed else (side+'準備') if ready else '様子見'
        # Show actual detected conditions, not a claim of predictive effectiveness.
        technical=[]
        def note_if(ok,name,detail):
            if ok: technical.append({'name':name,'detail':detail})
        direction='上昇' if side=='買い' else '下降'
        breakout_name='高値ブレイク' if side=='買い' else '安値ブレイク'
        note_if(bool(hit),breakout_name,
                f'終値 {c:.5g} が直前{lb}本の'+
                (f'最高値 {hi:.5g} を上抜け' if side=='買い' else f'最安値 {lo:.5g} を下抜け')+
                ('、かつBB外側で確定。' if not med else '。'))
        note_if(bool(pull),'EMA押し目買い' if side=='買い' else 'EMA戻り売り',
                '中期：EMA20付近への反応と当日の反転足を検出（確定足ベース）。')
        note_if(bool(near) and not hit and not pull,'ブレイク接近',
                f'直前{lb}本の'+('最高値' if side=='買い' else '最安値')+f'まで {dist:.2f} ATR。まだ突破は未確定。')
        note_if(bool(expansion),'BBエクスパンション',
                f'ボリンジャーバンド幅が前日比 {(bb/pb-1)*100:.1f}% 拡大（5%超）。拡大自体は方向を示しません。' if pb>0 else 'ボリンジャーバンド幅が拡大。')
        note_if(bool(prior_squeeze),'BBスクイーズ後',
                '過去12本（当日を除く）にBB幅パーセンタイル25%未満の日が存在。現在の幅が狭いとは限りません。')
        note_if(bool(trend),direction+'トレンド',
                '短期：終値・EMA20・EMA50の並びとEMA20傾斜が一致。' if not med else '中期：EMA50とEMA200の並び、週足方向が一致。')
        note_if(bool(mom),'RSI・MACD一致',
                f'RSI {numerical(a["rsi"]):.1f} / MACDヒストグラム '+('プラス' if side=='買い' else 'マイナス')+'。')
        note_if(bool(has_vol and vol_ok),'株式出来高条件',
                f'当日の出来高が直前20本平均の {(vratio if vratio is not None else 0):.2f} 倍（必要 {vol_threshold:g} 倍以上）。')
        note_if(bool(rso),'指数比の相対強度',
                f'市場指数との差（20本）：{(rs if rs is not None else 0):+.2f}ポイント。指数より'+('強い' if side=='買い' else '弱い')+'。')
        note_if(bool(med and (wlong if side=='買い' else wshort)),'週足トレンド一致',
                '確定週足ベースの10週EMAと方向が一致。')
        note_if(cycle==('ライト傾向' if side=='買い' else 'レフト傾向'),
                'ライトトランスレーション' if side=='買い' else 'レフトトランスレーション',
                f'直近の確認済み安値〜安値サイクルで高値位置が {cycle_peak_pct}% 。近似判定であり予測ではありません。')
        note_if(bool(wyckoff_up if side=='買い' else wyckoff_dn),'ワイコフ型ブレイク（近似）',
                '過去のBB収縮と価格突破が重なった状態。厳密なワイコフの蓄積・分配確認ではありません。')
        technical_names=[item['name'] for item in technical]
        headline=next((name for name in (
            breakout_name,'EMA押し目買い' if side=='買い' else 'EMA戻り売り',
            'ブレイク接近','BBエクスパンション',
            'ライトトランスレーション' if side=='買い' else 'レフトトランスレーション',
            direction+'トレンド') if name in technical_names), '明確な形状は未検出')
        missing_checks=[name for name,ok,_ in checks if not ok]
        # Stop behind swing, capped by ATR floor; reject invalid or unreasonably broad levels later.
        if side=='買い':
            swing=numerical(d['low'].iloc[-11:-1].min(),c)
            stop=min(swing-0.15*atr,c-1.2*atr)
            target=c+2*(c-stop)
        else:
            swing=numerical(d['high'].iloc[-11:-1].max(),c)
            stop=max(swing+0.15*atr,c+1.2*atr)
            target=c-2*(stop-c)
        risk=abs(c-stop);risk_atr=risk/atr
        if target<=0 or risk_atr>5:
            if status!='様子見':status='要確認（損切幅過大）'
        entry_score, entry_state, entry_notes = assess_entry(
            side=side, trend=bool(trend), momentum=bool(mom),
            confirmed=confirmed, ready=ready, hit=bool(hit), pull=bool(pull),
            expansion=bool(expansion), risk_atr=risk_atr, price=c, stop=stop,
            ema20=numerical(a['ema20']), atr=atr, rsi=numerical(a['rsi']),
            breakout_level=hi if side=='買い' else lo,
        )
        breakout = breakout_reference(
            period=period, side=side, close=c, high_line=hi, low_line=lo,
            bb_upper=numerical(a['bb_up']), bb_lower=numerical(a['bb_lo']),
            atr=atr, bar_date=pd.Timestamp(d.index[-1]).date(),
        )
        candidates.append(dict(
            市場=asset.market,銘柄=asset.name,シンボル=asset.symbol,期間=period,方向=side,判定=status,
            スコア=score,エントリー適性=entry_score,エントリー判定=entry_state,
            エントリー注意=entry_notes,価格=c,基準日=str(pd.Timestamp(d.index[-1]).date()),
            参考エントリー=c,参考損切り=stop,参考利確2R=target,損切幅ATR=round(risk_atr,2),
            ATR=atr,RSI=round(numerical(a['rsi']),1),出来高倍率=round(vratio,2) if vratio is not None else None,
            相対強度20日=round(rs,2) if rs is not None else None,BB幅パーセンタイル=round(pct,1),
            完了サイクル=cycle,サイクル高値位置パーセント=cycle_peak_pct,
            ワイコフ類似=('蓄積候補の上放れ' if wyckoff_up else '分配候補の下放れ' if wyckoff_dn else '未検出'),
            上値突破基準=hi,下値割れ基準=lo,週足方向=('上' if wlong else '下' if wshort else '中立') if med else '-',
            検証条件=' / '.join(name for name,ok,_ in checks if ok),
            主な根拠=headline,分析根拠=technical_names,根拠詳細=technical,
            未成立条件=missing_checks,ブレイク基準情報=breakout,データ=feed,
            注意=(asset.note or ('Yahooの参考価格。SBI約定価格ではありません' if asset.market.startswith('SBI') else '')) + (' ／ RSI過熱注意' if (numerical(a['rsi'])>=85 if side=='買い' else numerical(a['rsi'])<=15) else ''),
        ))
    return candidates


def scan_universe(assets,data,refs=None,periods=('短期','中期')):
    refs=refs or {}; rows=[]; issues=[]
    for a in assets:
        pair=data.get((a.market,a.name))
        if pair is None:continue
        df,feed=pair
        bench=(refs.get('^TOPX') if '^TOPX' in refs else refs.get('1306.T')) if a.market=='日本株' else refs.get('^GSPC') if a.market=='米国株' else None
        for period in periods:
            try:rows.extend(scan_asset(a,df,period,bench,feed))
            except Exception as exc:issues.append(f'{a.market}/{a.name}/{period}: {exc}')
    d=pd.DataFrame(rows)
    if len(d):
        rank={'買い初動':0,'ショート初動':0,'買い準備':1,'ショート準備':1,'要確認（損切幅過大）':2,'様子見':3}
        d['__rank']=d['判定'].map(rank).fillna(4)
        d=d.sort_values(['__rank','スコア'],ascending=[True,False]).drop(columns='__rank').reset_index(drop=True)
    return d,issues
