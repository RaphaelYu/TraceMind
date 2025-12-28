# Intent Form v0

このフォームは要件の入り口として最低限必要な情報を提供します。フィールドは「次の分解ステップ」と「検収可能な条件」を強制するよう設計されています。

## 構造
- `intent_id`: 一意の識別子（TM-INT-xxxx の形式を推奨）。
- `title`: 一目で分かる意図の要約。
- `context`: 背景・動機。なぜ今この意図が必要か。
- `goal`: 少なくとも1つの可測な目標。達成基準を明示。
- `non_goals`: 明示的に対象外・スコープ外な観点。
- `actors`: 関与する主体（user/system/external など）。
- `inputs` / `outputs`: 入出力の型と起点／行き先。次のタスクで具体的に使う。
- `constraints`: 制約をわけて記載することで形式的保証・ポリシー注入点を明示。
  - `invariants`: 常に成り立つべき制約（安全性・一貫性・監査）。
  - `policies`: 外部ポリシーや規制を反映する箇所。
- `success_metrics`: 3〜5個程度。検収時に抽出できるメトリクス。
- `risks`: 失敗モード・落とし穴。
- `assumptions`: 後続作業で検証すべき前提。
- `trace_links`: 分解や履歴参照のためのリンクを確保。
  - `parent_intent`: 上位意図（無ければ null）。
  - `related_intents`: 関連する兄弟意図。

## 記入のコツ
1. 目的（goal）と非目的（non_goals）のギャップを明示すると次段階の分解や検証条件が浮かび上がる。
2. `success_metrics`は具体的な出力や状態と結びつけ、`constraints`の `policies` とは実装境界での対応関係を意識する。
3. `trace_links`には上位や関連の意図を入れ、次の細分化や QA で直接参照できるようにする。

## 記入例
```yaml
intent_id: TM-INT-0001
title: "ユーザーの推論結果を10秒以内に配信"
context: "現在のレポートはバッチ処理で、改善提案が翌日になってしまう。リアルタイム性を高めてフィードバックの鮮度を保ちたい。"
goal: "6秒以内に推論 API から通知を返し、平均的にユーザーに0.5秒の遅延で表示されること"
non_goals:
  - "既存のバッチ期間を短縮する"
actors:
  - "user"
  - "system"
inputs:
  - "新規データセット通知 (webhook)"
  - "過去の分析結果 (DB)"
outputs:
  - "反映済みのダッシュボード"
constraints:
  invariants:
    - "すべての通知は認可済みユーザーに届く"
  policies:
    - "GDPR の同意がない場合は結果を保存しない"
success_metrics:
  - "95% のリクエストで 6 秒以内に応答"
  - "遅延が 1% を超えるケースの特定警告"
risks:
  - "一時的なデータ欠損でリアルタイムフローが止まる"
assumptions:
  - "バックエンドには既に認証済みユーザー情報がある"
trace_links:
  parent_intent: null
  related_intents:
    - "TM-INT-0002"
```

この構成は次のワークストリーム（データパイプライン、QA、実装チーム）で必要な情報を明示的に提示し、検収可能な基準と分解先を残すことを目的としています。
