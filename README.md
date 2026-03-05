# Mitou Local Tidy Helper

定点カメラで部屋の一角を観測し、ローカルまたは任意のクラウド VLM で状況を分析し、次の一手だけを静かに通知する Windows 向けデスクトップアプリです。`Electron + React` のデスクトップシェルと、`FastAPI + SQLite` のローカルコアサービスで構成しています。

## できること

- `RTSP + ONVIF` カメラ、または画像ディレクトリを使う `MockCameraAdapter`
- `privacy -> observe -> capture -> privacy` を前提にした観測サイクル
- ローカル `llama.cpp` 系エンドポイント、OpenAI、OpenRouter の切替
- 厳格な JSON バリデーション付きのシーン分析と完了判定
- Windows 通知とトレイ常駐
- SQLite 履歴、フル画像保存、サムネイル、マスク、メモリルール
- 診断画面、履歴タイムライン、マスク編集、タスクの完了・スヌーズ

## ディレクトリ構成

- `src/`: React フロントエンド
- `electron/`: Electron メインプロセス、preload、トレイ
- `backend/`: FastAPI サービス、SQLite モデル、観測パイプライン、テスト
- `tests/e2e/`: Playwright の UI スモークテスト

## 必要環境

- Windows 11
- Node.js 24+
- `uv`
- Python 3.11+
- 実機利用時は RTSP/ONVIF 対応カメラ
- ローカル VLM 利用時は OpenAI 互換 API を持つ `llama.cpp server` など

## セットアップ

1. `.env.example` を参考に `.env` を配置します。`OPENAI_API_KEY` と `OPENROUTER_API_KEY` は使う場合だけ必要です。
2. フロントエンド依存を入れます。

```powershell
npm install
```

3. バックエンド依存を入れます。

```powershell
uv sync --project backend --extra dev
```

4. 開発モードで起動します。

```powershell
npm run dev
```

初回起動後、ダッシュボードから以下を設定してください。

- `RTSP URL`
- `ONVIF Host / Port / Username / Password`
- `observe` と `privacy` のプリセット名
- または `Mock画像ディレクトリ`
- 利用する AI プロバイダとモデル設定
- 観測間隔、quiet hours、通知上限

## 実機利用の流れ

1. カメラを ONVIF で手動操作し、観測位置に合わせる
2. ダッシュボードで `observe保存`
3. 壁向きなどプライバシー位置に合わせて `privacy保存`
4. `接続診断`
5. `今すぐ観測`

## ローカル VLM 利用

既定ではローカルプロバイダを使います。`llama.cpp` など OpenAI 互換の `/chat/completions` を持つサーバーを用意し、`ローカル base URL` と `ローカルモデル` を設定してください。

テストや UI 確認だけをしたい場合は `local_base_url` に `mock://local-vlm` を指定すると、決定論的なモック分析を返します。

## スクリプト

```powershell
npm run dev
npm run build
npm run test:e2e
uv run --project backend pytest
```

Windows 配布ビルド:

```powershell
npm run dist:win
```

注意:

- 現在の `dist:win` は Electron シェルとバックエンドソースを同梱しますが、実行環境側に `uv` と Python が必要です。
- `ffmpeg` は必須ではありません。RTSP フレーム取得は OpenCV を使います。

## プライバシー方針

- 画像はローカルにフル保存されます。
- OpenAI / OpenRouter は明示的に選択した場合のみ使われます。
- マスク領域は分析前に黒塗りされ、マスク済み画像とサムネイルも保存します。

## テスト

- `backend/tests/test_api.py`: mock カメラで `設定 -> 観測 -> 履歴 -> 診断` を確認
- `backend/tests/test_pipeline.py`: quiet hours、マスク、容量表示
- `tests/e2e/dashboard.spec.ts`: フロントエンドのスモークテスト

## 主な制約

- `ONVIF` 実装は標準プリセット操作に依存します。機種ごとの差分はあります。
- ローカル VLM 側の OpenAI 互換性は実装差があります。必要に応じて base URL とモデルを調整してください。
- 画像保持はフル保存前提です。保存容量はダッシュボードから監視してください。
