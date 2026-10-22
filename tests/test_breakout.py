"""Breakout panel matches actual daily-bar logic in scanner.engine."""
import pytest
from scanner.breakout import breakout_reference


def scan_ref(period="短期", side="買い", close=98.5, high_line=100,
             low_line=90, bb_upper=100.5, bb_lower=88, atr=2):
    return breakout_reference(period=period, side=side, close=close,
                              high_line=high_line, low_line=low_line,
                              bb_upper=bb_upper, bb_lower=bb_lower,
                              atr=atr, bar_date="2026-10-22")


def test_short_term_buy_waits_for_daily_close_above_reference_and_bb():
    r=scan_ref()
    assert r["timeframe"]=="日足（確定足）"
    assert r["lookback_bars"]==20
    assert r["comparison"]==">"
    assert r["reference_price"]==100
    assert not r["complete"] and not r["price_crossed"]
    assert r["remaining_price"]==pytest.approx(1.5)
    assert r["remaining_pct"]==pytest.approx(1.5/98.5*100)
    assert "BB＋2σ" in r["rule"]


def test_stock_price_cross_without_bollinger_confirmation():
    r=scan_ref(close=100.25)
    assert r["price_crossed"]
    assert not r["complete"]
    assert r["state"]=="価格ライン通過、BB条件は未成立"
    assert r["remaining_price"]==0


def test_short_buy_breakout_requires_both_conditions():
    r=scan_ref(close=101)
    assert r["price_crossed"] and r["bb_passed"] and r["complete"]


def test_short_term_sell_uses_low_and_lower_band():
    r=scan_ref(side="ショート",close=89,bb_lower=88.5)
    assert r["comparison"]=="<"
    assert r["reference_price"]==90
    assert r["complete"]
    assert r["line_name"]=="直前20本の最安値"


def test_medium_uses_55_daily_bars_without_bollinger_filter():
    r=scan_ref(period="中期",side="ショート",close=89)
    assert r["lookback_bars"]==55
    assert r["complete"]
    assert r["bb_required"] is False
    assert r["bb_reference"] is None
    assert "BB" not in r["rule"]


def test_equal_price_does_not_break_strict_line():
    assert not scan_ref(close=100,bb_upper=99)["complete"]
    assert not scan_ref(side="ショート",close=90,bb_lower=91)["complete"]
