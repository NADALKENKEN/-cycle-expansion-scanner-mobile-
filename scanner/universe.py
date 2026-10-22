"""Starter symbols; this project never loads or modifies other scanners."""
from dataclasses import dataclass
from pathlib import Path
import csv

@dataclass(frozen=True)
class Asset:
    market: str
    name: str
    symbol: str
    alt_symbol: str = ""
    note: str = ""
    enabled: bool = True

FX_NAMES = {
 'USDJPY':'米ドル/円','EURJPY':'ユーロ/円','GBPJPY':'ポンド/円','AUDJPY':'豪ドル/円','TRYJPY':'トルコリラ/円',
 'MXNJPY':'メキシコペソ/円','ZARJPY':'南アフリカランド/円','NZDJPY':'NZドル/円','CADJPY':'カナダドル/円','CHFJPY':'スイスフラン/円',
 'CNYJPY':'人民元/円','SGDJPY':'シンガポールドル/円','HKDJPY':'香港ドル/円','HUFJPY':'ハンガリーフォリント/円',
 'CZKJPY':'チェココルナ/円','NOKJPY':'ノルウェークローネ/円','SEKJPY':'スウェーデンクローナ/円',
 'KRWJPY':'韓国ウォン/円','PLNJPY':'ポーランドズロチ/円','BRLJPY':'ブラジルレアル/円','RUBJPY':'ロシアルーブル/円',
 'EURUSD':'ユーロ/米ドル','GBPUSD':'ポンド/米ドル','AUDUSD':'豪ドル/米ドル','NZDUSD':'NZドル/米ドル',
 'EURGBP':'ユーロ/ポンド','EURAUD':'ユーロ/豪ドル','GBPAUD':'ポンド/豪ドル','EURNZD':'ユーロ/NZドル',
 'AUDNZD':'豪ドル/NZドル','USDCHF':'米ドル/スイスフラン','EURCHF':'ユーロ/スイスフラン',
 'GBPCHF':'ポンド/スイスフラン','AUDCHF':'豪ドル/スイスフラン','CHFTRY':'スイスフラン/トルコリラ',
 'CHFMXN':'スイスフラン/メキシコペソ','CHFZAR':'スイスフラン/南アフリカランド',
 'USDCNY':'米ドル/人民元','USDCAD':'米ドル/カナダドル',
}
JP = [
 ('7203','トヨタ自動車'),('6758','ソニーグループ'),('8306','三菱UFJ'),('8316','三井住友FG'),('8411','みずほFG'),
 ('8035','東京エレクトロン'),('6857','アドバンテスト'),('9984','ソフトバンクグループ'),('9983','ファーストリテイリング'),
 ('6501','日立製作所'),('6503','三菱電機'),('7011','三菱重工業'),('7012','川崎重工業'),('7013','IHI'),
 ('5803','フジクラ'),('5801','古河電気工業'),('6890','フェローテック'),('4063','信越化学工業'),('6146','ディスコ'),
 ('6723','ルネサス'),('8031','三井物産'),('8001','伊藤忠商事'),('8058','三菱商事'),('8766','東京海上HD'),
 ('7974','任天堂'),('9432','NTT'),('9433','KDDI'),('4502','武田薬品'),('4568','第一三共'),
 ('3697','SHIFT'),('3916','デジタル・インフォメーション・テクノロジー'),('7818','トランザクション'),
 ('6920','レーザーテック'),('6367','ダイキン'),('7267','ホンダ'),('9101','日本郵船'),('9104','商船三井'),
 ('4523','エーザイ'),('6902','デンソー'),('4661','オリエンタルランド')
]
US = [
 'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','AMD','PLTR','NFLX','CRM','ORCL','ADBE','INTC',
 'MU','AMAT','LRCX','KLAC','QCOM','ARM','TSM','ASML','LITE','COHR','CRWD','PANW','MSTR','COIN','BMNR',
 'JPM','GS','BAC','V','MA','UNH','LLY','NVO','PFE','XOM','CVX','CAT','BA','GE','RTX','LMT','NOC','WMT','COST','SPY','QQQ','IWM'
]
# SBI店頭CFD実際の銘柄とYahooで取得する参照指標/先物/現物の代替データは別物。
CFD = [
 ('日本225','NKD=F','^N225','日経先物近似・SBI日本225価格ではない'),
 ('米国S500','ES=F','^GSPC','E-mini先物近似'),
 ('米国NQ100','NQ=F','^NDX','NASDAQ100先物近似'),
 ('米国30','YM=F','^DJI','NYダウ先物近似'),
 ('米国R2000','RTY=F','^RUT','ラッセル2000先物近似'),
 ('中国A50','','','SBIの価格データなし：OHLCV CSV取り込み専用'),
 ('金スポット','GC=F','','金先物近似（SBI金スポットとは異なる）'),
 ('銀スポット','SI=F','','銀先物近似（SBI銀スポットとは異なる）'),
 ('銅','HG=F','','CME銅先物近似'),('北海原油','BZ=F','','ブレント先物近似'),
 ('WTI原油','CL=F','','WTI先物近似（限月切替に注意）'),('天然ガス','NG=F','','天然ガス先物近似（限月切替に注意）'),
 ('コーン','ZC=F','','とうもろこし先物近似'),('小麦','ZW=F','','小麦先物近似'),('大豆','ZS=F','','大豆先物近似'),
 ('ビットコイン','BTC-USD','','USD現物指標（SBI提示価格とは異なる）'),
 ('イーサリアム','ETH-USD','','USD現物指標（SBI提示価格とは異なる）'),
 ('XRP','XRP-USD','','USD現物指標（SBI提示価格とは異なる）'),
 ('ドージコイン','DOGE-USD','','USD現物指標（SBI提示価格とは異なる）'),
 ('ソラナ','SOL-USD','','USD現物指標（SBI提示価格とは異なる）'),
]

def built_in():
    assets = [Asset('日本株', n, s+'.T') for s,n in JP]
    assets += [Asset('米国株', t, t) for t in US]
    for code,name in FX_NAMES.items():
        alt = {'USDJPY':'JPY=X','USDCAD':'CAD=X','USDCHF':'CHF=X','USDCNY':'CNY=X'}.get(code,'')
        note='公開為替参考レート。SBI FXのBid/Ask/スワップと異なる'
        if code=='KRWJPY':
            note += '。SBIは100ウォン表示のため価格単位に注意'
        if code=='RUBJPY':
            note += '。SBIは新規取引を停止（公式情報を要確認）'
        assets.append(Asset('SBI FX', name,code+'=X',alt,note,code!='RUBJPY'))
    assets += [Asset('SBI CFD',n,s,a,note,True) for n,s,a,note in CFD]
    return assets


def merge_user_csv(content, baseline):
    """Append / replace using market,name,symbol[,alt_symbol,note,enabled]; never execute CSV content."""
    if not content:
        return baseline
    import io
    if isinstance(content,bytes):
        content=content.decode('utf-8-sig')
    rows=csv.DictReader(io.StringIO(content))
    expected={'market','name','symbol'}
    if not expected.issubset(set(rows.fieldnames or [])):
        raise ValueError('銘柄CSVには market,name,symbol の列が必要です')
    combined={(a.market,a.name):a for a in baseline}
    for row in rows:
        market=row.get('market','').strip()
        name=row.get('name','').strip()
        symbol=row.get('symbol','').strip()
        if market not in ['日本株','米国株','SBI FX','SBI CFD'] or not name or not symbol:
            continue
        enabled=row.get('enabled','1').strip().lower() not in ('false','0','no','off')
        combined[(market,name)] = Asset(market,name,symbol,row.get('alt_symbol','').strip(),row.get('note','').strip(),enabled)
    return list(combined.values())


def make_example_csv(path:Path):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        wr=csv.writer(f); wr.writerow(['market','name','symbol','alt_symbol','note','enabled'])
        wr.writerow(['日本株','任意の日本株','1234.T','','上場コードを実際の銘柄へ変更',0])
        wr.writerow(['米国株','任意の米国株','EXAMPLE','','上場ティッカーへ変更',0])
        wr.writerow(['SBI CFD','中国A50','YOUR_VENDOR_SYMBOL','','取引画面からCSVを取り込む場合はSBI CFD側の名前と一致させる',0])
