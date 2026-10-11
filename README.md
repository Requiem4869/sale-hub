# AIアフィリエイト運営組織（Amazon × X / Instagram）

20〜40代女性向けの靴・バッグのセール情報を、毎時自動で集めて告知する仕組み。
各Pythonモジュールが1つの「部署」として動き、GitHub Actions が毎時起動する。

## 部署とファイル

| 部署 | ファイル | 仕事 |
|---|---|---|
| 社長室 | `bot/cli.py` | 全部署を順番に動かす |
| リサーチ部 | `bot/amazon.py` | Creators APIでセール商品を検索 |
| 編集部 | `bot/editorial.py` | 割引率・価格帯・在庫でふるい分け、重複投稿の防止 |
| 制作部 | `bot/site.py` | ハブサイト（GitHub Pages）を毎時更新 |
| 広報部 | `bot/posts.py` | Xの下書き、Instagramストーリーズ画像を作成 |
| 法務部 | `bot/compliance.py` | PR表記・価格表記・禁止表現を自動チェック |
| 配信部 | `bot/publish.py` | 承認済みの下書きだけを投稿 |

## 規約から決まった設計（ここは変えないこと）

1. **SNSに価格・商品写真・割引率を載せない。** APIの商品データは「自分のサイト上でのみ」表示可能（API利用規約 1(a)・4(m)）。SNSは自分の言葉で告知し、詳細はハブサイトへ誘導する。
2. **価格履歴を保存しない。** 商品データの保存は24時間まで（4(n)）。値下げ判定はAmazonが返す割引率だけで行い、保存するのはASINと投稿時刻のみ。`public/` はリポジトリに入れない。
3. **ハブサイトの価格には取得時刻と免責文言を付ける**（4(o)・4(q)）。
4. **全投稿に「PR」**（ステマ規制）。法務部のチェックに通らない下書きは投稿されない。

## セットアップ手順

### フェーズ0：手動立ち上げ（APIなし）
Creators APIは**直近30日で10件以上の売上**がないと使えない。それまでは手動で売上を作る。
1. GitHubで新しいリポジトリを作り、このフォルダの中身をアップロード
2. Settings → Pages → Source を「GitHub Actions」に
3. `config.yaml` の `partner_tag` と `site_url` を自分の値に
4. `manual_picks.example.yaml` を `manual_picks.yaml` にコピーして商品を手入力
5. ハブサイトのURLを、Amazonアソシエイト・セントラルの「サイト情報」とX/Instagramのプロフィールに登録

### フェーズ1：半自動（承認あり）
1. アソシエイト・セントラル → ツール → Creators API でキーを発行
2. X Developer Console でアプリを作りクレジットを購入、Instagramはプロアカウント化してGraph APIのトークンを取得
3. リポジトリの Settings → Secrets に登録：
   `AMAZON_CLIENT_ID` `AMAZON_CLIENT_SECRET` `X_API_KEY` `X_API_SECRET` `X_ACCESS_TOKEN` `X_ACCESS_SECRET` `IG_USER_ID` `IG_ACCESS_TOKEN`
4. `config.yaml` の `phase: 1`
5. 承認方法：`drafts/` の下書きをGitHubアプリで開き、`approved: false` → `true` に書き換えて保存。次の毎時実行で投稿される

### フェーズ2：全自動
法務部の差し戻しが2週間ゼロなら `auto_approve: true`。

## ローカルでの確認（APIキー不要）
```bash
pip install -r requirements.txt
pytest -q                          # 規約ルールのテスト
python -m bot.cli run --mock       # サンプルデータで全工程を実行 → public/index.html
python -m bot.cli publish --dry-run
python -m bot.cli status
```

## 未確認の前提（運用前に確認）
- `searchItems` のURLは `getItems` と同じ命名規則（`/catalog/v1/searchItems`）と想定
- Instagram APIのストーリーズ投稿ではリンクスタンプを付けられない想定（プロフィールのリンクに誘導）
- Graph APIのバージョン（`bot/publish.py` の `GRAPH_VERSION`）

## Instagramの情報投稿（フィード・自動）
- ネタのストック：`content/feed.yaml`（上から順に投稿。`approved: true` のものだけ）
- 投稿日時：`config.yaml` の `feed_days`（月・水・金）と `feed_hour_jst`（20時以降の最初の実行）
- 画像：毎時の実行で `public/feed/<id>/<n>.jpg` に描画され、GitHub Pagesで公開 → Instagram APIがそのURLから取得
- 確認：`python -m bot.cli preview-feed` で `preview/` に一覧画像を出力
- 必要なSecrets：`IG_ACCESS_TOKEN`（長期トークン、約60日ごとに更新）、`IG_USER_ID`（任意）
