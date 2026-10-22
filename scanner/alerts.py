"""Send conditional 15-minute entry signals to Pushover (iPhone / Apple Watch mirroring).

This separate workflow never places orders or logs credentials. Alerts require:
- completed 15m reference bar, <=45m since bar close,
- an actual NEW entry signal, not a repeated active condition,
- both trend and entry suitability thresholds,
- safe reference stop, and cooldown between re-entries.
Signal memory is restored/saved by GitHub Actions cache; caches can be evicted.
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import parse, request
from zoneinfo import ZoneInfo

from scanner.daytrade import load_day_prices, scan_day_universe
from scanner.universe import built_in, merge_user_csv

JST = ZoneInfo("Asia/Tokyo")
PUBLIC_URL = "https://nadalkenken.github.io/-cycle-expansion-scanner-mobile-/"
MAX_BAR_AGE_MINUTES = 45
COOLDOWN_HOURS = 4
MAX_PER_RUN = 5


def parse_bar_close(text):
    """Day scanner bar_date: YYYY-MM-DD HH:MM JST (already bar end time)."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M JST").replace(tzinfo=JST).astimezone(timezone.utc)


def event_key(row):
    return "|".join(map(str, (row.get("市場"), row.get("シンボル"), row.get("方向"))))


def eligible(row, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Current time must be timezone-aware")
    if row.get("期間") != "デイトレ":
        return False
    if row.get("判定") not in ("買い初動", "ショート初動"):
        return False
    if row.get("エントリー判定") != "新規エントリー検討":
        return False
    if (row.get("エントリー適性") or 0) < 75 or (row.get("スコア") or 0) < 70:
        return False
    if (row.get("損切幅ATR") or 100) > 2.5:
        return False
    br = row.get("ブレイク基準情報") or {}
    if not br.get("complete") or br.get("timeframe") != "15分足（確定足）":
        return False
    try:
        close_at = parse_bar_close(row["基準日"])
        age = (now - close_at).total_seconds() / 60
        return -3 <= age <= MAX_BAR_AGE_MINUTES
    except (KeyError, ValueError, TypeError):
        return False


def format_price(number):
    try:
        return f"{float(number):.6f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return "不明"


def format_message(row):
    br = row.get("ブレイク基準情報") or {}
    direction = "上抜け" if row["方向"] == "買い" else "下抜け"
    line = format_price(br.get("reference_price"))
    lines = [
        f"{row['市場']} / {row['銘柄']} ({row['シンボル']})",
        f"{row['方向']}初動｜確定15分足 {row['基準日']}",
        f"参考終値 {format_price(row.get('価格'))} / {direction}ライン {line}",
        f"参考損切り {format_price(row.get('参考損切り'))} / 2R目標 {format_price(row.get('参考利確2R'))}",
        f"方向一致 {row['スコア']}点・エントリー適性 {row['エントリー適性']}点",
        "公開参考値による条件成立。SBIの現値・スプレッド・注文可能条件を必ず確認。",
        "通知遅延あり／自動発注なし",
    ]
    return "\n".join(lines)


def push_pushover(title, message, *, token=None, user=None, url=PUBLIC_URL):
    token = token if token is not None else os.getenv("PUSHOVER_APP_TOKEN", "")
    user = user if user is not None else os.getenv("PUSHOVER_USER_KEY", "")
    if not token or not user:
        raise RuntimeError("PUSHOVER_APP_TOKEN / PUSHOVER_USER_KEY secret is not configured")
    payload = {
        "token": token,
        "user": user,
        "title": title[:200],
        "message": message[:1000],
        "priority": "0",
        "url": url,
        "url_title": "デイトレスキャナーを開く",
        "ttl": "3600",
    }
    device = os.getenv("PUSHOVER_DEVICE", "").strip()
    if device:
        payload["device"] = device
    encoded = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        "https://api.pushover.net/1/messages.json",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "CycleExpansionDaytradeAlert/1.0"},
        method="POST",
    )
    # API response is checked for actual acceptance; it does not guarantee device display.
    with request.urlopen(req, timeout=15) as response:
        result = json.loads(response.read(8192).decode("utf-8"))
    if result.get("status") != 1:
        raise RuntimeError("Pushover did not accept the notification")
    return True


def load_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") == 1 and isinstance(data.get("active"), dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "initialized": False, "active": {},
            "last_sent": {}, "last_checked": None}


def save_state(path, state):
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(file)


def process_signals(rows, state, send, now=None, limit=MAX_PER_RUN):
    """Update active flags for evaluated instruments; do not clear missing symbols.

    A first-time scan only initializes memory, so existing setups do not produce
    a flood of stale alerts. Re-crossing after inactivity and cooldown may alert.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Current time must be timezone-aware")
    records = rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows)
    valid = {event_key(r): r for r in records}
    active = state.setdefault("active", {})
    last_sent = state.setdefault("last_sent", {})
    is_first = not state.get("initialized", False)
    candidates = []
    for key, row in valid.items():
        was = bool(active.get(key, False))
        qualifies = eligible(row, now=now)
        active[key] = qualifies
        if is_first or was or not qualifies:
            continue
        last = last_sent.get(key)
        if last:
            try:
                previous = datetime.fromisoformat(last)
                if previous.tzinfo and now-previous < timedelta(hours=COOLDOWN_HOURS):
                    continue
            except ValueError:
                pass
        candidates.append((key, row))
    state["initialized"] = True
    state["last_checked"] = now.isoformat()
    if is_first:
        return {"sent": [], "errors": [], "bootstrap": True, "eligible": sum(eligible(r,now) for r in records)}
    candidates.sort(key=lambda x: (x[1].get("エントリー適性") or 0, x[1].get("スコア") or 0), reverse=True)
    sent=[]; errors=[]
    for key, row in candidates[:max(0,limit)]:
        try:
            title=f"【デイトレ{row['方向']}】{row['銘柄']}"
            send(title, format_message(row))
            last_sent[key] = now.isoformat()
            sent.append(key)
        except Exception as exc:
            # Retain retry eligibility if Pushover rejected this message.
            active[key] = False
            errors.append(f"{key}: {type(exc).__name__} (送信失敗)")
    return {"sent": sent, "errors": errors, "bootstrap": False, "eligible": sum(eligible(r,now) for r in records)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--state", default=".alert_state/state.json")
    parser.add_argument("--test", action="store_true", help="Send one Pushover connection test, no market trade signal")
    parser.add_argument("--universe", default="", help="Optional CSV selecting monitoring universe")
    opts=parser.parse_args()
    if opts.test:
        push_pushover("Cycle×Expansion 接続テスト",
                      "デイトレ通知の接続テストです。売買シグナルではありません。"
                      "iPhoneとApple Watchの通知設定を確認してください。")
        print("Pushover test accepted by API (device delivery is not guaranteed).")
        return
    assets=built_in()
    if opts.universe:
        content=Path(opts.universe).read_bytes()
        assets=merge_user_csv(content,[])
    assets=[a for a in assets if a.enabled]
    data, download_problems = load_day_prices(assets)
    signals, scan_problems = scan_day_universe(assets, data)
    state=load_state(opts.state)
    report=process_signals(signals, state, push_pushover)
    save_state(opts.state, state)
    print(f"15min feed {len(data)}/{len(assets)}, candidate {report['eligible']},"
          f" sent {len(report['sent'])}, errors {len(report['errors'])},"
          f" bootstrap {report['bootstrap']}.")
    print(f"Feed/scan problems: {len(download_problems)+len(scan_problems)}")
    for failure in report["errors"]:
        print("::warning::Pushover " + failure)
    if not data:
        print("::warning::No public 15-minute candles were available. No trade messages sent.")
    if report["bootstrap"]:
        print("::notice::First run initialized signal history without sending historical trade alerts.")


if __name__=="__main__":
    main()
