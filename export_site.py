"""Generate a mobile-readable static report for GitHub Pages.

No broker credentials, direct broker requests, trades, or made-up quotes.
"""
import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scanner.data import load_ohlcv
from scanner.engine import scan_universe
from scanner.universe import built_in, merge_user_csv

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'site' / 'data' / 'latest.json'

FIELD_MAP = {
    '市場': 'market', '銘柄': 'name', 'シンボル': 'symbol', '期間': 'horizon',
    '方向': 'side', '判定': 'signal', 'スコア': 'score', '価格': 'price',
    '基準日': 'bar_date', '参考エントリー': 'entry', '参考損切り': 'stop',
    '参考利確2R': 'target_2r', '損切幅ATR': 'risk_atr', 'ATR': 'atr',
    'RSI': 'rsi', '出来高倍率': 'volume_ratio', '相対強度20日': 'rs20',
    'BB幅パーセンタイル': 'bb_width_rank', '完了サイクル': 'cycle',
    'サイクル高値位置パーセント': 'cycle_peak_pct', 'ワイコフ類似': 'wyckoff_proxy',
    '上値突破基準': 'upper_break', '下値割れ基準': 'lower_break',
    '週足方向': 'weekly_trend', '検証条件': 'passed_checks',
    'データ': 'feed', '注意': 'note',
}


def normalize(v):
    """Produce strict JSON, converting non-finite pandas/numpy values to null."""
    if v is None: return None
    if hasattr(v, 'item'): return normalize(v.item())
    if isinstance(v, float) and not math.isfinite(v): return None
    if isinstance(v, (str, int, float, bool)): return v
    if hasattr(v, 'isoformat'): return v.isoformat()
    return str(v)


def build_payload(assets, signals, feeds, issues, clock=None):
    now = clock or datetime.now(ZoneInfo('Asia/Tokyo'))
    rows = []
    for record in signals.to_dict('records'):
        rows.append({dest: normalize(record.get(origin)) for origin, dest in FIELD_MAP.items()})
    # Distinct instrument count, not number of long/short/horizon evaluations.
    analyzed = len(feeds)
    charts = {}
    for (market, name), (frame, _) in feeds.items():
        if len(frame):
            # Instrument-specific, 60 completed reference closes. Never invent prices.
            recent = frame['close'].tail(60)
            charts[f'{market}::{name}'] = {
                'dates': [str(i.date()) for i in recent.index],
                'values': [normalize(float(v)) for v in recent.values],
            }
    first = {
        'generated_at': now.isoformat(timespec='seconds'),
        'timezone': 'Asia/Tokyo',
        'method': '公表市場データの参考日足。SBIのリアルタイム提示価格ではありません。',
        'source': 'Yahoo Finance reference via yfinance and optional user CSV',
        'assets_enabled': len(assets),
        'assets_analyzed': analyzed,
        'signals_count': len(rows),
        'issue_count': len(issues),
        'issues': [str(x)[:240] for x in issues[:120]],
    }
    return {'meta': first, 'rows': rows, 'charts': charts}


def write_payload(payload, path=OUT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--universe', default='', help='Optional CSV of symbols to append')
    parser.add_argument('--markets', nargs='+', choices=['JP', 'US', 'FX', 'CFD'],
                        default=['JP', 'US', 'FX', 'CFD'])
    args = parser.parse_args()
    names = {'JP': '日本株', 'US': '米国株', 'FX': 'SBI FX', 'CFD': 'SBI CFD'}
    assets = built_in()
    if args.universe:
        assets = merge_user_csv(Path(args.universe).read_bytes(), assets)
    assets = [a for a in assets if a.enabled and a.market in {names[v] for v in args.markets}]
    print(f'Scanning {len(assets)} instruments for short + medium mobile report')
    feeds, indexes, download_problems = load_ohlcv(assets)
    signals, analysis_problems = scan_universe(assets, feeds, indexes, ('短期','中期'))
    payload = build_payload(assets, signals, feeds, download_problems + analysis_problems)
    out = write_payload(payload)
    print(f'Exported {len(payload["rows"])} evaluations from {len(feeds)}/{len(assets)} instruments into {out}')
    print(f'Warnings: {payload["meta"]["issue_count"]}')
    if len(feeds) == 0:
        # Deployment still publishes an explicit "no usable data" state, not false signals.
        print('WARNING: No usable reference data were obtained. Site will show this plainly.')


if __name__ == '__main__':
    main()
