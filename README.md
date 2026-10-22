# Cycle × Expansion | iPhone対応・独立型スキャナー

既存の `evening-swing-edge` や `tob-initial-scanner` には手を加えない、独立した市場分析スキャナーです。

## iPhoneで開く

公開設定が済み、GitHub Actions の実行が成功すると、以下のURLで開けます。

https://nadalkenken.github.io/-cycle-expansion-scanner-mobile-/

Safari の共有 →「ホーム画面に追加」でアプリのように起動できます。

## GitHub Pages の初回設定

1. リポジトリの **Settings → Pages** を開く。
2. **Build and deployment → Source** を **GitHub Actions** にする。
3. **Actions → Mobile scanner - analyze and publish → Run workflow** を実行する。
4. 実行ログの **build** と **deploy** が成功（緑色）したら、上のURLをiPhoneのSafariで開く。

以後は平日07:35/21:35（日本時間）に更新を試みます。GitHubの都合で遅延・停止する場合があります。

## 対象・分析内容

- 短期（3〜10営業日）と中期（2週間〜3か月）を別タブで表示。
- 買い初動・ショート初動・買い準備・ショート準備のランキング。
- ダウ理論、サイクル理論の近似、ボリンジャーバンド、出来高、相対的強さ、ワイコフ類似パターン。
- 日本株・米国株、SBI FX通貨ペア、SBI CFDの参考市場商品を初期設定で監視（利用できない公開ティッカーは分析対象外）。
- 参考損切り価格、2R利益目標、ミニチャート、CSV銘柄追加。
- 各銘柄カードに「検出したテクニカル」「主な形状」「根拠と未成立条件」を表示。短期と中期、買いとショートで別判定。

- スコアを「方向の条件一致度」と「今から入る場合のエントリー適性」に分離。後者は損切り幅（ATR/価格）、EMA20からの乖離、RSI過熱、ブレイクからの距離を考慮する**検証用の独自採点**です。いずれも勝率・確率・期待収益を示しません。
- 例えば下降シグナルが100点でも、損切りが4.73 ATRなど大きい場合は「見送り（追いかけ注意）」となり得ます。日足参考値であり、SBIの板・証拠金・コストは未反映です。
- iPhoneの時刻表示と更新ボタンが重ならないよう、安全領域を確保。画面本文にも押しやすい「表示データを再読込」を設置しました。**押しても新しい市場データの解析は始まりません**。市場データの更新はGitHub Actionsの定期/手動実行で行います。
- BBエクスパンション・BBスクイーズ後・高値/安値ブレイク・ライト/レフトトランスレーション・EMA押し目/戻りなどで結果を絞り込み。
- テクニカル名は成立した条件を示すもので、その指標が将来の値動きに有効であることを実証したものではありません。
- iPhoneの更新ボタンは**既に公開済みのデータを読み直す**操作です。新しい市場データの解析はActions実行で行います。

## 市場データの注意事項

Yahoo Finance等の公開参考日足を `yfinance` で取得します。
**SBI FX・SBI CFDの提示レート、スプレッド、限月、証拠金率、金利・調整額とは一致しません。**
FX・CFDの現物出来高を推定したり、価格を創作したりしません。
このソフトは参考情報の自動集計であり、自動売買・取引口座へのログインは行いません。
PublicリポジトリとPagesの内容は誰でも閲覧できます。APIキーなどの秘密情報はコミットしないでください。

## ソース構成

- `scanner/`：分析ロジック、データ取得、監視銘柄リスト
- `export_site.py`：価格データ取得・分析結果を `site/data/latest.json` へ出力
- `site/`：iPhoneで閲覧できる日本語ウェブ画面
- `.github/workflows/pages.yml`：定期スキャンとGitHub Pages公開
- `app.py` / `run_scan.py`：Windows向けのローカル実行（任意）
- `tests/`：計算とデータ出力の自動テスト

## ローカルで実行・検証

`pip install -r requirements.txt` → `python -m pytest -q`
手動集計：`python export_site.py`
ローカル表示：`python -m http.server 8000 --directory site`

`universe.csv` を追加する場合は `market,name,symbol,alt_symbol,note,enabled` の列が必要です。
