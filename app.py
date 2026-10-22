"""Run with: streamlit run app.py"""
from datetime import datetime
from pathlib import Path
import io
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from scanner.universe import built_in, merge_user_csv
from scanner.data import load_ohlcv,DATA_DIR,safe_filename,confirm_four_hour
from scanner.engine import scan_universe

st.set_page_config(page_title='Multi-Market Cycle & Expansion Scanner',page_icon='📈',layout='wide')
st.title('📈 Cycle × Expansion — 独立スキャナー')
st.caption('日本株・米国株・SBI FX・SBI店頭CFD ｜ 短期・中期独立判定 ｜ 買い・ショート')
st.warning('このソフトは売買候補抽出ツールです。SBIへの接続・発注は行いません。FX/CFDの外部データはSBIの提示価格ではなく参考指標です。')

assets=built_in()
with st.sidebar:
    st.header('スキャン設定')
    markets=st.multiselect('対象市場',['日本株','米国株','SBI FX','SBI CFD'],default=['日本株','米国株','SBI FX','SBI CFD'])
    choice=st.radio('売買期間',['両方','短期','中期'])
    presets={'両方':('短期','中期'),'短期':('短期',),'中期':('中期',)}
    status_opts=['買い初動','ショート初動','買い準備','ショート準備','要確認（損切幅過大）','様子見']
    wanted=st.multiselect('表示する判定',status_opts,default=status_opts[:4])
    min_score=st.slider('表示最低スコア',0,100,55,5)
    only_custom=st.toggle('CSV指定銘柄のみ（独自リスト優先）',value=False)
    user_csv=st.file_uploader('銘柄リストCSV（任意）',type='csv',key='universe_csv')
    four_hour=st.toggle('短期候補の4時間足を追加確認（上位12件）',value=False)
    st.caption('参考相場はYahoo Financeから取得。通信失敗・未対応銘柄は「失敗一覧」に表示します。')
    go_scan=st.button('🔎 スキャンを実行',type='primary',use_container_width=True)

if user_csv:
    try:
        supplied=merge_user_csv(user_csv.getvalue(),[])
        assets=merge_user_csv(user_csv.getvalue(),[] if only_custom else assets)
        st.sidebar.success(f'CSVから{len(supplied)}行の有効な銘柄を反映')
    except Exception as exc:
        st.sidebar.error(str(exc))
assets=[a for a in assets if a.market in markets and a.enabled]
st.sidebar.write(f'スキャン対象: **{len(assets)}** 銘柄（取扱可否・データ品質は別確認）')

if go_scan:
    if not assets:st.error('対象銘柄がありません。設定を変更してください。')
    else:
        with st.spinner('価格履歴を取得して判定しています。通信状況によっては失敗銘柄が発生します。'):
            try:
                frames,refs,fetch_errors=load_ohlcv(assets)
                rows,analysis_errors=scan_universe(assets,frames,refs,presets[choice])
                if four_hour and not rows.empty:
                    rows['4時間足']='未確認'
                    mask=(rows['期間']=='短期') & (rows['判定'].isin(['買い初動','ショート初動','買い準備','ショート準備']))
                    for idx in rows[mask].head(12).index:
                        r=rows.loc[idx]
                        rows.loc[idx,'4時間足']=confirm_four_hour(r['シンボル'],r['方向'])
                st.session_state['results']=rows
                st.session_state['frames']=frames
                st.session_state['issues']=fetch_errors+analysis_errors
                st.session_state['runat']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                st.session_state['scanned_count']=len(assets)
            except Exception as exc:
                st.error(f'スキャンを実行できませんでした: {exc}')

if 'results' not in st.session_state:
    st.info('左側で市場・期間を選び「スキャンを実行」を押してください。ネットワーク取得ができない場合は下記のOHLCV CSV取込が利用できます。')
    st.write('初期登録市場別件数:')
    st.dataframe(pd.Series([a.market for a in built_in()]).value_counts().rename('初期登録数'),use_container_width=True)

results=st.session_state.get('results',pd.DataFrame())
if 'runat' in st.session_state:
    st.caption(f"最後の実行: {st.session_state['runat']} / 対象 {st.session_state.get('scanned_count',0)}銘柄。これは約定通知ではありません。")

short_tab,medium_tab,assets_tab,issues_tab=st.tabs(['⚡ 短期（3〜10営業日）','📊 中期（2週間〜3か月）','🗂 取扱銘柄・CSV','⚠️ 注意・取得失敗'])


def render_period(period):
    if results.empty or '期間' not in results:
        st.info('該当するスキャン結果がありません。');return
    d=results[results['期間']==period].copy()
    a,b,c,dcol=st.columns(4)
    a.metric('買い初動',(d['判定']=='買い初動').sum())
    b.metric('ショート初動',(d['判定']=='ショート初動').sum())
    c.metric('買い準備',(d['判定']=='買い準備').sum())
    dcol.metric('ショート準備',(d['判定']=='ショート準備').sum())
    d=d[d['判定'].isin(wanted)&(d['スコア']>=min_score)]
    if d.empty:
        st.info('現在の絞り込み条件では候補がありません。閾値を下げるか、別の日のデータを確認してください。')
        return
    d['テクニカル根拠']=d['分析根拠'].apply(lambda v: ' / '.join(v) if isinstance(v,list) else '') if '分析根拠' in d.columns else ''
    show=['市場','銘柄','方向','判定','主な根拠','テクニカル根拠','スコア','価格','基準日','参考損切り','参考利確2R','損切幅ATR','RSI','出来高倍率','相対強度20日','完了サイクル','ワイコフ類似','データ']
    if '4時間足' in d.columns:show.insert(5,'4時間足')
    st.dataframe(d[show],use_container_width=True,hide_index=True,height=450)
    csv=d.to_csv(index=False).encode('utf-8-sig')
    st.download_button('📥 この期間の結果をCSV保存',csv,file_name=f'signals_{"short" if period=="短期" else "medium"}.csv',mime='text/csv',key='download_'+period)
    opts=[f'{r["市場"]} | {r["銘柄"]} | {r["方向"]} | {r["判定"]}' for _,r in d.iterrows()]
    selection=st.selectbox('チャート・根拠を詳しく確認',range(len(opts)),format_func=lambda i:opts[i],key='sel_'+period)
    r=d.iloc[selection]
    st.write(f"**{r['銘柄']}**　{r['判定']} / スコア {r['スコア']}（勝率ではありません）")
    st.caption(f"主な形状: {r.get('主な根拠','—')} ／ 成立条件: {r['検証条件']} ／ データ: {r['データ']} ／ 基準日: {r['基準日']}")
    details=r.get('根拠詳細',[])
    if isinstance(details,list):
        with st.expander('🔎 検出したテクニカルと根拠・未成立条件',expanded=False):
            for item in details:
                st.markdown(f"**{item['name']}**：{item['detail']}")
            missing=r.get('未成立条件',[])
            if isinstance(missing,list) and missing: st.warning('未成立：'+' / '.join(missing))
    st.caption(f"注意: {r['注意'] or 'スクリーニング指標のみ。板情報・売買可否・コストは未反映。'}")
    base=st.session_state['frames'].get((r['市場'],r['銘柄']))
    if base is not None:
        from scanner.indicators import add_indicators
        df=add_indicators(base[0]).tail(170)
        fig=go.Figure()
        fig.add_trace(go.Candlestick(x=df.index,open=df['open'],high=df['high'],low=df['low'],close=df['close'],name='OHLC'))
        for col,label in [('ema20','EMA20'),('ema50','EMA50'),('bb_up','BB上限'),('bb_lo','BB下限')]:
            fig.add_trace(go.Scatter(x=df.index,y=df[col],mode='lines',name=label,line={'width':1}))
        fig.add_hline(y=float(r['参考損切り']),line_dash='dot',annotation_text='参考損切り')
        fig.add_hline(y=float(r['参考利確2R']),line_dash='dot',annotation_text='参考利確 2R')
        fig.update_layout(height=460,margin=dict(l=5,r=5,t=25,b=5),xaxis_rangeslider_visible=False)
        st.plotly_chart(fig,use_container_width=True,key='chart_'+period)
        st.caption('参考エントリーは確定日足の終値。翌日その価格で約定できるとは限りません。建玉サイズ・証拠金・スプレッド・スワップ・限月調整などは未計算。')

with short_tab:render_period('短期')
with medium_tab:render_period('中期')
with assets_tab:
    st.subheader('登録銘柄')
    st.dataframe(pd.DataFrame([{'市場':a.market,'銘柄':a.name,'Yahoo参考シンボル':a.symbol,'代替':a.alt_symbol,'注意':a.note,'有効':a.enabled} for a in built_in()]),use_container_width=True,hide_index=True,height=390)
    st.markdown('**登録銘柄の拡張:** 日本株の4桁コードには `.T` を付けます。米国株はティッカーをそのまま指定します。銘柄CSVでは `market,name,symbol,alt_symbol,note,enabled` を指定します。')
    example='market,name,symbol,alt_symbol,note,enabled\n日本株,トヨタ自動車,7203.T,,,1\n米国株,NVIDIA,NVDA,,,1\n'
    st.download_button('銘柄CSVテンプレート',example.encode('utf-8-sig'),'stock_universe_example.csv','text/csv')
    st.markdown('**CSV OHLCVの優先使用:** 以下のように `Date,Open,High,Low,Close,Volume` 列を持つ日足CSVを取り込みます。SBI CFD の中国A50などYahoo参考価格が用意できない商品も取り込めます。')
    source_asset=st.selectbox('CSVを適用する登録銘柄',assets,format_func=lambda a:f'{a.market} / {a.name}',key='ohlcv_name') if assets else None
    datafile=st.file_uploader('日足OHLCV CSVファイル（任意）',type='csv',key='daily_csv')
    if source_asset and datafile and st.button('指定銘柄の価格データとして保存'):
        raw=datafile.getvalue()
        if len(raw)>15_000_000:st.error('CSVは15MB以内にしてください。')
        else:
            try:
                from scanner.indicators import prepare
                temp=pd.read_csv(io.BytesIO(raw))
                if not {'Date','Open','High','Low','Close'}.issubset(temp.columns):
                    raise ValueError('Date,Open,High,Low,Close列が必要です')
                temp.index=pd.to_datetime(temp['Date'],errors='raise')
                if len(prepare(temp.drop(columns='Date')))<240:raise ValueError('有効な日足は240本以上必要です')
                DATA_DIR.mkdir(parents=True,exist_ok=True)
                (DATA_DIR/safe_filename(source_asset)).write_bytes(raw)
                st.success('CSVを保存しました。再スキャンするとこの銘柄はYahooではなくCSVを優先します。')
            except Exception as exc:st.error(str(exc))
    st.caption('CSV保存は実行環境のローカルフォルダに行われます。クラウドホスティングでは再起動後に消える場合があります。')
with issues_tab:
    st.subheader('データ欠損・取得失敗')
    issues=st.session_state.get('issues',[])
    if not issues:st.info('現在報告された問題はありません（未実行の場合も含む）。')
    else:
        st.caption('通信制限やYahoo非対応ティッカー、FX特殊通貨などはスキップします。欠損を補完して架空の売買候補を表示することはありません。')
        st.code('\n'.join(issues[:400]),language=None)
        st.download_button('エラーログ保存','\n'.join(issues).encode('utf-8-sig'),'scan_issues.txt')
    st.subheader('運用上の注意')
    st.markdown('''- SBI FX・SBI CFDの正規のBid/Ask、売買単位、取引停止状況、ロールオーバー、スワップ、金利調整・価格調整額などは取得しません。
- CFD先物の参考連続価格は限月乗り換え時にギャップが生じ、SBIの店頭CFDチャートとは一致しない場合があります。
- FXでは公開データの出来高は取引所の全約定量ではないため、出来高チェックを無効化しています。
- 空売り可否、貸株料、信用取引規制、指標発表、配当落ち、決算予定は自動検査していません。
- RSIやワイコフ理論はヒントに過ぎず、スコアは勝率や期待利益ではありません。過去データで検証してから利用してください。''')
