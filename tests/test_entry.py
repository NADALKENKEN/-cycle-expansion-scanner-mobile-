"""Regression tests: direction confidence is independent from immediate entry suitability."""
from scanner.entry import assess_entry


def candidate(**kwargs):
    data = dict(side='ショート', trend=True, momentum=True, confirmed=True,
                ready=False, hit=True, pull=False, expansion=True,
                risk_atr=1.4, price=628.25, stop=653, ema20=638,
                atr=16, rsi=46, breakout_level=642.50)
    data.update(kwargs)
    return assess_entry(**data)


def test_strong_trend_but_large_stop_lowers_entry_score():
    score, state, reasons = candidate(risk_atr=4.73, stop=709.065,
                                      ema20=650, rsi=27.8)
    assert score < 55, (score, state, reasons)
    assert state.startswith('見送り')
    assert any('4.73 ATR' in message for message in reasons)


def test_moderate_risk_entry_is_ranked_higher():
    strong = candidate()
    weak = candidate(risk_atr=4.73, stop=709.065, ema20=650, rsi=27.8)
    assert strong[0] >= 75
    assert strong[0] > weak[0]


def test_ready_but_no_breakout_is_not_entry_now():
    score, state, _ = candidate(confirmed=False, ready=True, hit=False)
    assert state == 'ブレイク待ち'


def test_no_signal_is_not_entry_candidate():
    score, state, _ = candidate(confirmed=False, ready=False,
                                hit=False, trend=False, momentum=False)
    assert state == '条件不足（見送り）'


def test_invalid_risk_metrics_are_ineligible():
    score, state, _ = candidate(atr=0)
    assert score == 0
    assert state == '評価不可'
