"""Entry suitability distinct from directional technical confluence.

Heuristic research score (not probability, expectation, or trading advice).
Only completed bars, the technical setup and stop from scan_asset are used.
"""
import math


def assess_entry(*, side, trend, momentum, confirmed, ready, hit, pull,
                 expansion, risk_atr, price, stop, ema20, atr, rsi,
                 breakout_level):
    if side not in ('買い', 'ショート'):
        raise ValueError('side must be 買い or ショート')
    nums = (risk_atr, price, stop, ema20, atr, rsi, breakout_level)
    if not all(math.isfinite(float(v)) for v in nums) or price <= 0 or atr <= 0 or risk_atr <= 0:
        return 0, '評価不可', ['参考価格・ATR・損切り情報が不足しています。']

    # No gain in this score merely because a 2R objective is constructed.
    score = 50
    score += 12 if trend else -18
    score += 8 if momentum else -12
    score += 12 if confirmed else (4 if ready else -15)
    score += 6 if pull else (4 if hit else 0)
    score += 3 if expansion else 0

    reasons = []
    if risk_atr <= 1.5:
        score += 15
    elif risk_atr <= 2.5:
        score += 7
    elif risk_atr <= 3.5:
        score -= 10
        reasons.append(f'損切りが {risk_atr:.2f} ATR と広めです。')
    elif risk_atr <= 4.5:
        score -= 22
        reasons.append(f'損切りが {risk_atr:.2f} ATR と大きく、追いかけ注文は不利になりやすいです。')
    else:
        score -= 35
        reasons.append(f'損切りが {risk_atr:.2f} ATR と非常に大きく、押し目・戻り待ちを優先。')

    stretch = abs(price - ema20) / atr
    if stretch <= 0.9:
        score += 8
    elif stretch <= 1.7:
        score += 3
    elif stretch <= 2.5:
        score -= 8
        reasons.append(f'価格がEMA20から {stretch:.2f} ATR 離れています。')
    else:
        score -= 16
        reasons.append(f'価格がEMA20から {stretch:.2f} ATR 離れ、反動に警戒。')

    if side == '買い':
        if rsi >= 75:
            score -= 18
            reasons.append(f'RSI {rsi:.1f}：上昇が過熱気味です。')
        elif rsi >= 70:
            score -= 10
            reasons.append(f'RSI {rsi:.1f}：高値での新規買いに注意。')
        overshoot = max(0.0, (price - breakout_level) / atr)
    else:
        if rsi <= 25:
            score -= 18
            reasons.append(f'RSI {rsi:.1f}：短期反発に警戒。')
        elif rsi <= 30:
            score -= 10
            reasons.append(f'RSI {rsi:.1f}：売られ過ぎ圏に近く反発に注意。')
        overshoot = max(0.0, (breakout_level - price) / atr)
    if hit:
        if overshoot >= 2:
            score -= 12
            reasons.append(f'突破ラインから {overshoot:.2f} ATR 乖離：追随は慎重に。')
        elif overshoot >= 1:
            score -= 6
            reasons.append(f'突破ラインから {overshoot:.2f} ATR 乖離。')

    price_risk = abs(price - stop) / price * 100
    if price_risk >= 8:
        score -= 10
        reasons.append(f'参考損切り幅が価格の {price_risk:.1f}% に達しています。')

    score = max(0, min(100, round(score)))
    if not confirmed:
        state = 'ブレイク待ち' if ready else '条件不足（見送り）'
    elif risk_atr > 5 or (side == 'ショート' and price - 2 * (stop - price) <= 0):
        state = '見送り（リスク過大）'
    elif score >= 75:
        state = '新規エントリー検討'
    elif score >= 55:
        state = '慎重（押し・戻り待ち）'
    else:
        state = '見送り（追いかけ注意）'
    if not reasons:
        reasons.append('過熱や極端な損切り幅は未検出。ただし発注価格・スプレッド等は未反映。')
    return score, state, reasons
