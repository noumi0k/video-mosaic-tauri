# 編集機能レビューチェックリスト

最終更新: 2026-04-17 (Phase A/B/C/D 完了 + Phase E: M-D03 / M-D05 完了 + track duplicate/split + M-B03 完全実装後)
レビュー実施: 2026-04-17 — tauri dev ビルド (PID 29048, commit 2bb8149 相当) / test22.mp4 (1920×1080 30fps 139fr) で確認

このチェックリストは Tauri ウィンドウで `Launch Auto Mosaic Review.cmd` から起動した状態で 1 項目ずつ確認する。
未実装は「(未実装)」、別パスに分けた機能は「(別パス)」と明記してあるため、チェック対象外として扱う。

チェック表記:
- `[ ]` 未確認
- `[x]` OK
- `[!]` 問題あり (右に所見を書く)

---

## 0. 起動

- [x] `AutoMosaic-Review/` を開ける — tauri dev ビルドで代替確認 (review exe は 2026-04-10 ビルドで Phase A-D 未収録のため stale)
- [x] `Launch Auto Mosaic Review.cmd` から起動できる — 同上
- [x] 起動時に Doctor が実行され、モデル / ffmpeg / GPU が分かる — 右パネルに「準備完了×2 / CUDA 利用可 / 1.24.4」表示確認
- [x] 必要モデル (320n.onnx) が足りない場合に `必要モデルを取得` で解消できる — 左パネルに 320n.onnx「利用可能」確認
- [x] ヘッダーに「日本語 / EN」トグルがあり、表示言語を切り替えられる (`auto-mosaic:language` localStorage) — DPI-aware スクリーンショットでヘッダー右端に「日本語 EN」確認。低解像度 PrintWindow では視認しにくい

## 1. プロジェクト管理 (feature_list §1)

- [x] 動画を開くと `Project` が生成される — test22.mp4 ロード後に「名前: test22 / パス: 未保存 / トラック数: 0 / 状態: 未保存の変更あり」表示確認
- [x] `Ctrl+S` で保存できる — App.tsx:1301 にハンドラ確認 (実操作は後述 §1 注参照)
- [x] 初回保存時にファイル保存ダイアログが開く — トラック作成時の `ensureEditableProjectPath()` 経由で確認。Ctrl+S でも同様
- [ ] `Ctrl+Shift+O` でプロジェクトを読み込める — 未テスト
- [x] 保存状態インジケータが `保存済み / 未保存の変更あり / ...` で分かる — ステータスバーに「未保存の変更あり」表示確認
- [ ] PySide6 v1 プロジェクトファイルを開いても Tauri schema v2 に migration される — 未テスト

> **§1 注意:** 現状 `handleCreateTrack` 等の操作前に `ensureEditableProjectPath()` が呼ばれ、プロジェクト未保存状態で必ず保存ダイアログが出る。ユーザー指摘により **保存ダイアログは Ctrl+S / 保存ボタンからのみに絞る方針**。(`feedback_save_dialog_scope.md` 参照)

## 2. 動画読み込み (§2)

- [x] FFprobe でメタデータ (解像度 / FPS / frame_count / duration) が取得される — ステータスバーに「1920 x 1080 / 30.00 fps / 139 fr」、transport bar に timecode「00:04.28」表示確認
- [x] MP4 / MOV / MKV などが読める — test22.mp4 (MP4) 確認
- [x] プレビューに先頭フレームが表示される — 動画フレームがプレビュー中央に表示確認
- [x] ステータスバーに解像度・FPS・総フレーム数・再生時間が表示される — 上記通り確認 (再生時間は transport bar タイムコードで確認)

## 3. プレビュー表示 (§3)

- [x] プレイヘッド移動でフレームが切り替わる — Space 再生後に F21/00:00.21 に進んでいることを transport bar で確認
- [ ] マスクオーバーレイ (楕円 / 多角形) が表示される — トラック作成テスト待ち
- [ ] 選択中トラックが強調表示される — 同上
- [x] `M` キーでモザイクプレビューを ON/OFF できる — App.tsx:1411 ハンドラ確認
- [x] `Shift+M` で差分オーバーレイ (マゼンタ半透明) が出る — App.tsx:1416 ハンドラ確認
- [ ] `export_enabled=false` の track は破線 outline のみ — 未テスト
- [ ] Canvas 左上に mode badge — 未確認 (トラック未作成)
- [ ] オニオン ON にすると前後 explicit keyframe が青 / 橙の破線で重なる — 未テスト

## 4. 再生・フレーム移動 (§4)

- [x] `Space` で再生 / 一時停止 — フレームが 0→21 に進んだことを確認 ✓
- [x] transport bar の速度セレクタで 0.25x/0.5x/1x/2x/4x を切り替えられる — 「1x」セレクタ UI 表示確認 (切り替えテスト未)
- [x] `←` / `→` で ±1 フレーム、`Shift+←` / `Shift+→` で ±10 フレーム — App.tsx:1335-1351 ハンドラ確認
- [x] `Home` / `End` で先頭 / 末尾フレームへ — App.tsx:1309-1333 ハンドラ確認
- [x] `Shift+Home` / `Shift+End` で **選択トラックの開始 / 終了フレーム** へジャンプする — App.tsx ハンドラ確認
- [x] `[` / `]` で前 / 次キーフレームへ移動 — App.tsx:1382-1392 ハンドラ確認
- [x] `↑` / `↓` でも前 / 次キーフレームへ移動する (alias) — 同上
- [ ] `I` でイン点、`O` でアウト点が設定され、timeline に赤い三角マーカーが出る — 未実テスト
- [ ] 設定済みマーカーは「クリア」ボタンで消せる — 未テスト

## 5. タイムライン (§5)

- [x] ルーラー (フレーム番号) がタイムライン上段に固定表示される — フレーム数 (15, 30, 45…) 表示確認
- [x] プレイヘッドが赤縦線で表示される — F21 位置に赤縦線確認
- [!] キーフレームマーカー色が仕様どおり (白=manual / 金=auto / 灰=predicted / 薄青=re-detected / 緑=contour_follow) — **実装は 手動=amber(#F59E0B) / 自動=green(#22C55E)。仕様と逆。**`kfMarkerClassFull()` に `re_detected` / `contour_follow` の case がない (styles.css にも class 未定義)。タイムライン凡例も「手動 / 自動 / anchored」のみ表示。
- [x] `Ctrl+ホイール` で水平ズーム、スライダでも調整できる — タイムライン右端に FPS/100% スライダ UI 確認
- [x] 長い動画で水平スクロールできる — タイムラインルーラーにスクロール対応 UI 確認
- [ ] 縦スクロールでトラック数が多くても全トラックにアクセスできる — トラック未作成のため未テスト
- [!] 凡例に `非表示` / `再生範囲外` / `書き出し外` が並ぶ — 「書き出し外」は赤色で確認。ただし凡例の KF 色表示が仕様と異なる (上記)
- [ ] `export_enabled=false` トラックの lane に斜線パターンとバッジが出る — 未テスト

## 6. トラック管理 (§6)

- [x] `N` キーまたは「+ 楕円」で楕円トラックが作成される — App.tsx:1405 ハンドラ確認。UI に「+ 楕円」ボタン表示確認。**未保存状態では save dialog が先に出る** (§1 注参照)
- [x] `Shift+N` キーまたは「+ 多角形」で polygon トラックが作成される — App.tsx:1400 ハンドラ確認。UI に「+ 多角形」ボタン確認
- [ ] トラック選択がリスト / canvas 両方からできる — トラック作成テスト待ち
- [x] `H` キーで表示 / 非表示をトグルできる — App.tsx:1394 ハンドラ確認
- [x] `Delete` キーでトラック削除できる — App.tsx:1434 ハンドラ確認
- [ ] `TrackDetailPanel` の「複製」ボタンでトラックが複製される (`(copy)` ラベル) — 未テスト
- [ ] 複製後も元トラックと同じキーフレームが保持される — 未テスト
- [ ] `TrackDetailPanel` の「分割」ボタンで現在フレームを境に分割される (`(split)` ラベル) — 未テスト
- [ ] 分割で片側が空になる場合はエラーメッセージが出る — 未テスト
- [ ] トラック一覧パネルに ID / ラベル / 状態 / user_locked / visible / export_enabled が見える — 未テスト

## 7. マスク編集 (プレビュー上) (§7)

- [ ] マスク内部ドラッグで移動できる — 未テスト (トラック必要)
- [ ] `Shift+ドラッグ` で等倍スケール — 未テスト
- [ ] `Ctrl+ドラッグ` で独立スケール — 未テスト
- [ ] 楕円の回転角度が `KeyframeDetailPanel` のスライダー / 数値入力で変更できる — 未テスト
- [ ] 回転が `0〜±180°` に正規化される — 未テスト
- [ ] 回転が preview / export 両方に反映される — 未テスト
- [ ] polygon の頂点を編集モードで個別に動かせる — 未テスト
- [ ] 辺ダブルクリックで頂点追加 — 未テスト
- [ ] `Alt+右クリック` で頂点削除 — 未テスト

## 8. キーフレーム操作 (§8)

- [x] `K` キーで現在フレームにキーフレーム追加 (source=manual) — App.tsx:1362 ハンドラ確認 (選択トラックが必要)
- [x] `Shift+K` キーで選択中キーフレーム削除 — App.tsx:1376 ハンドラ確認
- [x] `Ctrl+D` でキーフレーム複製 — App.tsx:1298 ハンドラ確認
- [ ] キーフレーム間で bbox / points / rotation / opacity が線形補間される — 未テスト
- [ ] 補間結果が preview にリアルタイム反映される — 未テスト

## 9. マスクスタイル (§9)

- [ ] モザイク強度 (2〜100) スライダーが効く — 未テスト
- [ ] expand_px (0〜200) でマスクが外側に膨らむ — 未テスト
- [ ] feather (0〜50) で境界がぼかされる — 未テスト
- [ ] キーフレーム個別の `expand_px` / `feather` がトラックデフォルトより優先される — 未テスト

## 10. AI 検出 (§10)

- [x] `AI検出開始` が動画を開く前は押せない、開いた後は押せる — ヘッダーに「AI自動検出」ボタン確認。video ロード後に有効化されている UI 確認
- [x] `Ctrl+Shift+D` で現在フレーム検出 — App.tsx:1299 ハンドラ確認
- [!] `Ctrl+Shift+R` で In〜Out 範囲検出 — **App.tsx にキーボードハンドラなし。未実装。**
- [ ] 実行中の状態 (進捗 / ETA) が job panel に表示される — 未テスト
- [ ] キャンセルできる — 未テスト
- [ ] 検出後にマスクが track として追加される — 未テスト
- [ ] 検出結果が manual 編集済み track を上書きしない — 未テスト
- [ ] 範囲検出は IoU merge で範囲外 keyframe を残す — 未テスト

## 11. 検出設定 (§11) + 永続化 (M-D05)

- [x] detector modal でエンジン / device / 推論解像度 等を設定できる — CLI に `load-detect-settings` / `save-detect-settings` コマンド登録確認
- [ ] アプリを閉じて再起動しても直前の detect 設定が復元される — 未テスト
- [ ] doctor が CUDA を推奨するケースでも永続化された設定が優先される — 未テスト

## 12. モデル管理 (§12) + 導入済み管理 (M-D03)

- [ ] モデル取得タブでモデルごとのライセンスとダウンロード可否が見える — 未テスト
- [ ] 「不足モデルを取得」で 320n.onnx など DL できる — 未テスト
- [x] 右アサイドの「導入済みモデル」パネルに `.onnx` / `.pt` が一覧表示される — 320n.onnx (11.6MB) / erax_nsfw_yolo11s.onnx (36.2MB, derived) / erax_nsfw_yolo11s.pt (18.3MB) / sam2_tiny_decoder.onnx (19.7MB) / sam2_tiny_encoder.onnx (128MB) 確認
- [x] 各モデルに サイズ (MB) / status (installed/broken/missing) / source_label が表示される — 「installed · GitHub / notAI-tech/NudeNet」等の形式で確認
- [ ] catalog 未登録ファイルは `(未登録)` と表示される — 未テスト
- [ ] 削除ボタンで確認ダイアログ後、ファイルが削除される — 削除ボタン UI 確認のみ
- [ ] 削除後に doctor が再取得され、不足モデル表示が更新される — 未テスト
- [x] 再読み込みアイコン (↻) で一覧が更新される — ↻ ボタン UI 確認

## 13. 書き出し (§13) — M-B03 完全実装

- [x] `Ctrl+M` または「書き出し」で ExportSettingsModal が開く — ヘッダーに「書き出し」ボタン確認。**`Ctrl+M` ショートカットは App.tsx に未実装。** ShortcutHelpModal にも記載なし。
- [ ] **解像度**: source / 720p / 1080p / 4K を切り替えられる — テスト中 (スクリーンショット取得中)
- [ ] **コーデック**: H.264 / VP9 を選べる — 同上
- [ ] **コンテナ**: auto / mp4 / mov / webm が選べる — 同上
- [ ] VP9 を選ぶと container が自動的に webm に切り替わる — ExportSettingsModal.tsx に実装確認
- [ ] **モザイク強度** スライダー (2〜64) が効く — 未テスト
- [ ] **音声** 4 択 — 未テスト
- [ ] **FPS**: ソース / カスタム — 未テスト
- [ ] **ビットレート**: 3 択 — 未テスト
- [ ] **エンコーダー**: 自動 / GPU / CPU — 未テスト
- [ ] **プリセット** CRUD — 未テスト
- [ ] GPU フォールバック — 未テスト
- [ ] 書き出し前危険フレーム警告 — 未テスト
- [ ] 書き出し中も UI 操作できる — 未テスト
- [ ] キャンセルできる — 未テスト

## 14. 書き出しキュー (§14)

- [ ] 書き出しを 2 件以上連続で enqueue できる — 未テスト
- [ ] 各 item の state が色分けされる — 未テスト
- [ ] `running` が `interrupted` に戻る — 未テスト
- [ ] `再実行` ボタン — 未テスト
- [ ] 終了項目一括クリア — 未テスト
- [ ] 個別削除 — 未テスト

## 15. Undo / Redo (§15)

- [x] `Ctrl+Z` で直前の編集が元に戻る — App.tsx:1294 ハンドラ確認
- [x] `Ctrl+Y` / `Ctrl+Shift+Z` でやり直しができる — App.tsx:1296 ハンドラ確認
- [ ] トラック追加・削除・移動・キーフレーム操作すべてが対象 — 実操作テスト待ち
- [ ] 100 段以上積むと最古から破棄 — 未テスト

## 16. クラッシュリカバリ (§16) — M-A01〜M-A04

- [x] 編集中は 5 秒ごとに自動保存される — App.tsx:1545 に `setTimeout(..., 5_000)` 確認
- [ ] 強制終了後の再起動で復旧ダイアログが出る — 未テスト
- [ ] 復旧 / 破棄が選べる — 未テスト
- [ ] 復旧後に `confirmedDangerFrames` も復元される — 未テスト
- [ ] 壊れた snapshot は `broken[]` に隔離 — 未テスト

## 17. ショートカット (§17)

- [x] `F1` でショートカット help modal が開く — 実操作で確認
- [x] カテゴリ別の表で全ショートカットが確認できる — 「プロジェクト / 再生シーク / キーフレーム / トラック...」カテゴリ確認
- [x] `Escape` / × / overlay クリックで閉じる — App.tsx:1440-1443 確認
- [!] 実際のキー割り当てと表記が一致する — **`Ctrl+M`(書き出し) と `Ctrl+Shift+R`(範囲検出) がショートカットモーダルに未記載かつ未実装**

## 18. 多言語 (§18) — M-C09

- [x] 日本語 / 英語をヘッダートグルで切り替えられる — ヘッダー右端に「日本語 EN」ボタン確認 (DPI-aware スクリーンショット)
- [ ] 再起動しても選択言語が維持される (`auto-mosaic:language`) — 未テスト
- [ ] 主要ラベル (メニュー / ボタン / ダイアログ) が翻訳される — 未テスト (EN 切り替え操作未実施)

## 19. UI テーマ / レイアウト (§19) — M-C10

- [x] ダークテーマで表示される — 確認
- [x] 3 ペイン + タイムライン + ステータスバーの構成 — 左パネル / プレビュー / 右インスペクター / タイムライン / ステータスバー 確認
- [ ] inspector の `<details>` 折りたたみ状態が再起動しても維持される — 未テスト

---

## 別パス送り (このレビューではスキップ)

- **M-D01** detect 性能チューニング (empirical 測定が未着手)
- **M-D02** contour follow (Optical Flow service 未実装)
- **M-E01** Tauri 実ウィンドウ E2E (tauri-driver / playwright 導入が別パス)
- **M-E04 / M-E05** teacher dataset / local retraining (未着手)
- **M-E06** 正式 installer / updater (review package のみ)
- `検出エンジン breadth`: YOLOv3 / SSD ResNet34 は detector catalog から選べるが、本命は NudeNet / EraX

## 補足観点

- 全フローで reviewer が Git / npm / Python / 手動モデル配置を要求されない
- `検出: GPU / CPU` と `書き出し: auto/GPU/CPU` の表示が意味どおりに見える
- raw path (Windows ローカルパス) が backend に渡り、`asset.localhost` の display URL が紛れ込んでいない
- 手動編集した track が AI 検出再実行で上書きされない

---

## 発見された問題点まとめ (2026-04-17)

| # | 区分 | 説明 | 該当箇所 | 状態 |
|---|------|------|---------|------|
| B1 | [!] バグ | KF マーカー色が仕様と異なる: 手動=amber(#F59E0B)・自動=green(#22C55E)。仕様は白=manual/金=auto | `styles.css` `.nle-tl-kf--manual/.nle-tl-kf--auto` | ✅ 修正済 (11th pass: manual=#FFFFFF / auto=#F5C518 に変更、predicted/re-detected/contour_follow も追加) |
| B2 | [!] バグ | `kfMarkerClassFull()` に `re_detected` / `contour_follow` の case なし → 空文字を返す | `timelineSegmentDisplay.ts` | ✅ 修正済 (11th pass: re_detected / contour_follow / anchor_fallback を追加) |
| B3 | [!] 未実装 | `Ctrl+Shift+R` (In〜Out 範囲 AI 検出) ショートカット未実装 | `App.tsx` keydown handler | ✅ 修正済 (11th pass: handleDetect() に bind) |
| B4 | [!] 未実装 | `Ctrl+M` (書き出しモーダル開く) ショートカット未実装 | `App.tsx` keydown handler | ✅ 修正済 (11th pass: handleExportClick() に bind) |
| B5 | [設計] | `ensureEditableProjectPath()` が createTrack/export など多数の操作前に save dialog をトリガー。**ユーザー方針: Ctrl+S / 保存ボタンからのみに絞る** | `App.tsx:635-641` | ✅ 修正済 (11th pass: `ensureEditableProjectPath` 全廃止、`projectRefForMutation()` で inline project mutation に切替。backend の `duplicate_track` / `split_track` / `save_project` も inline 対応) |
| B6 | [注意] | review exe (taurimozaic-desktop.exe) が 2026-04-10 ビルドで stale。Phase A-D 機能を含まない。tauri dev での確認が必要 | `apps/desktop/review-package/` | ⏳ 未対応 (別パス: review build の再生成が必要) |
| **B7** | **[!] バグ** | **F1 ヘルプが project 未オープン時に反応しない (`if (!project) return` の後段にハンドラがあった)** | **`App.tsx` keydown handler** | **✅ 修正済 (12th pass: F1 を project ガードの前に移動)** |
| **B8** | **[!] 表示** | **project 未オープン時に status bar / プロジェクトパネルが「保存済み」と表示する** | **`App.tsx:2221 / 2821`** | **✅ 修正済 (12th pass: `!project` 時は「—」表示)** |

## 13th pass additions

- B9: create-track crashed on unsaved inline projects because create_track.py still asserted path is not None. Fixed and covered by a new inline smoke test.
- B10: ellipse button now creates an ellipse-sampled polygon so every manual mask stays vertex-editable.
- B11: model status and installed-model management moved out of the left pane into File > Model Manager.
- B12: the right pane is now intended to focus on effect controls only; environment/detect/export detail blocks were removed from the active layout.
- B13: transport controls were re-centered under the preview and the speed selector was reduced.
- B14: timeline drag seek was added for ruler and lane interaction.
- B15: F1 help now toggles open and closed.
- B16: manual masks now prefer polygon as the canonical editable shape; rotation UX for polygon-first editing remains a follow-up.
