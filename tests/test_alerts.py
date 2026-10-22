"""Alert transitions, stale bars, cooldown and safe Pushover payload (no live network)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from scanner.alerts import eligible, process_signals, format_message, parse_bar_close, load_state

JST=ZoneInfo("Asia/Tokyo")
BASE=datetime(2026,10,22,13,0,tzinfo=JST).astimezone(timezone.utc)


def signal(now=BASE, side="買い", name="テスト株"):
    close_time=(now-timedelta(minutes=20)).astimezone(JST)
    label=close_time.strftime("%Y-%m-%d %H:%M JST")
    return {
        "市場":"日本株","銘柄":name,"シンボル":"1234.T",
        "期間":"デイトレ","方向":side,"判定":side+"初動",
        "エントリー判定":"新規エントリー検討",
        "エントリー適性":84,"スコア":88,"損切幅ATR":1.6,
        "基準日":label,"価格":110,"参考損切り":108,
        "参考利確2R":114,
        "ブレイク基準情報":{
            "timeframe":"15分足（確定足）",
            "reference_price":109,"complete":True,
            "comparison":">",
        },
    }


def new_state():
    return {"version":1,"initialized":False,"active":{},"last_sent":{}}


def test_fresh_15min_signal_eligible():
    r=signal()
    assert eligible(r,now=BASE)
    assert parse_bar_close(r["基準日"]).tzinfo is not None


def test_stale_daytrade_signal_never_notifies():
    r=signal(now=BASE-timedelta(hours=2))
    assert not eligible(r,now=BASE)
    r=signal()
    r["判定"]="参考のみ（古い15分足）"
    assert not eligible(r,now=BASE)


def test_nonconfirmed_and_ineligible_entry_rejected():
    r=signal()
    r["ブレイク基準情報"]["complete"]=False
    assert not eligible(r,now=BASE)
    r=signal()
    r["エントリー適性"]=55
    assert not eligible(r,now=BASE)
    r=signal()
    r["損切幅ATR"]=4.73
    assert not eligible(r,now=BASE)


def test_bootstrap_sends_no_old_signals_and_deduplicates():
    rows=[signal()]
    sent=[]
    state=new_state()
    first=process_signals(rows,state,lambda title,msg:sent.append((title,msg)),now=BASE)
    assert first["bootstrap"] and not sent
    same=process_signals(rows,state,lambda title,msg:sent.append((title,msg)),now=BASE+timedelta(minutes=5))
    assert not same["sent"] and not sent
    # One non-eligible scan re-arms this market/side without re-alerting indefinitely.
    quiet=signal(now=BASE+timedelta(minutes=15))
    quiet["判定"]="様子見"
    process_signals([quiet],state,lambda *_:None,now=BASE+timedelta(minutes=15))
    later=signal(now=BASE+timedelta(minutes=30))
    again=process_signals([later],state,lambda title,msg:sent.append((title,msg)),now=BASE+timedelta(minutes=30))
    assert len(again["sent"])==1 and len(sent)==1
    assert "15分足" in sent[0][1] and "109" in sent[0][1]
    repeat=process_signals([later],state,lambda title,msg:sent.append((title,msg)),now=BASE+timedelta(minutes=35))
    assert not repeat["sent"]


def test_cooldown_blocks_alert_spam_after_retrigger():
    state=new_state()
    process_signals([signal()],state,lambda *_:None,now=BASE)
    quiet=signal(now=BASE+timedelta(minutes=10)); quiet["判定"]="様子見"
    process_signals([quiet],state,lambda *_:None,now=BASE+timedelta(minutes=10))
    sent=[]
    first=signal(now=BASE+timedelta(minutes=20))
    process_signals([first],state,lambda *v:sent.append(v),now=BASE+timedelta(minutes=20))
    assert len(sent)==1
    later_quiet=signal(now=BASE+timedelta(minutes=30));later_quiet["判定"]="様子見"
    process_signals([later_quiet],state,lambda *_:None,now=BASE+timedelta(minutes=30))
    next_active=signal(now=BASE+timedelta(minutes=40))
    out=process_signals([next_active],state,lambda *v:sent.append(v),now=BASE+timedelta(minutes=40))
    assert not out["sent"] and len(sent)==1


def test_failed_push_is_retryable_not_reported_sent():
    state=new_state()
    process_signals([signal()],state,lambda *_:None,now=BASE)
    quiet=signal(now=BASE+timedelta(minutes=10));quiet["判定"]="様子見"
    process_signals([quiet],state,lambda *_:None,now=BASE+timedelta(minutes=10))
    active=signal(now=BASE+timedelta(minutes=20))
    def fail(*_):
        raise RuntimeError("fake API failure")
    result=process_signals([active],state,fail,now=BASE+timedelta(minutes=20))
    assert not result["sent"] and result["errors"]
    sent=[]
    result=process_signals([active],state,lambda *v: sent.append(v),now=BASE+timedelta(minutes=22))
    assert len(sent)==1 and len(result["sent"])==1


def test_missing_state_first_run_is_safe(tmp_path):
    state=load_state(tmp_path/"state.json")
    assert state["initialized"] is False
    assert state["active"]=={}
