"""Explain the *daily* breakout line used by the scanner.

Lines are historical reference values at the last completed daily bar, not
intraday execution triggers or SBI broker quotes. They roll with each scan.
"""
import math


def breakout_reference(*, period, side, close, high_line, low_line, bb_upper,
                       bb_lower, atr, bar_date):
    if period not in ("短期", "中期") or side not in ("買い", "ショート"):
        raise ValueError("Unknown period or side")
    numeric=(close,high_line,low_line,atr)
    if not all(math.isfinite(float(v)) for v in numeric) or close<=0 or atr<=0:
        raise ValueError("Invalid breakout reference")
    n=20 if period=="短期" else 55
    buy=side=="買い"
    line=float(high_line if buy else low_line)
    crossed=close>line if buy else close<line
    band_value=float(bb_upper if buy else bb_lower)
    band_passed=(math.isfinite(band_value) and
                 (close>band_value if buy else close<band_value)) if period=="短期" else None
    complete=bool(crossed and (band_passed if period=="短期" else True))
    pending_distance=max(0.0, line-close if buy else close-line)
    direction="上抜け" if buy else "下抜け"
    comparison="厳密に上回る" if buy else "厳密に下回る"
    bb_name="BB＋2σ" if buy else "BB－2σ"
    price_condition=f"日足終値が直前{n}本の"+("最高値" if buy else "最安値")+f" {line:g} を{comparison}"
    condition=(price_condition + (f"、さらにその確定日足の{bb_name}の外側で確定" if period=="短期" else ""))
    if complete:
        state="ブレイク条件成立"
    elif crossed:
        state="価格ライン通過、BB条件は未成立"
    else:
        state="ブレイク未成立（終値待ち）"
    return dict(
        timeframe="日足（確定足）",
        lookback_bars=n,
        line_name=f"直前{n}本の"+("最高値" if buy else "最安値"),
        reference_price=line,
        direction=direction,
        comparison=">" if buy else "<",
        price_crossed=bool(crossed),
        bb_required=period=="短期",
        bb_name=bb_name if period=="短期" else None,
        bb_reference=band_value if period=="短期" and math.isfinite(band_value) else None,
        bb_passed=bool(band_passed) if period=="短期" else None,
        complete=complete,
        state=state,
        remaining_price=pending_distance,
        remaining_pct=pending_distance/close*100,
        remaining_atr=pending_distance/atr,
        rule=condition,
        as_of=str(bar_date),
        caution=("基準日時点の公開参考日足。次の確定足では直前高値・安値とBBが変化します。"
                 "FX・CFDはSBIの提示レートではなく、参考指標と同じ価格単位です。"),
    )
