# PySide6 UI構成参照
最終更新: 2026-04-15

この文書は、PySide6版Auto MosaicのUI構成、ボタン配置、メニュー構成をTauri版の設計参考として記録するものです。Tauri版で同じ見た目や同じQtウィジェット構造を再現するための仕様ではありません。

## 参照方針

- PySide6版は「どの操作が、どの文脈で、どの頻度で露出していたか」を知るために参照する。
- Tauri版では、Web UIとして自然な情報設計、操作導線、レスポンシブ性を優先する。
- ボタン名や配置は、機能の重要度を判断する材料として扱う。
- Qt固有の都合、ダイアログ中心の構造、固定幅前提の細部はそのまま移植しない。
- Backend contract、project schema、job state、manual edit保護のほうをUI再現より優先する。

## 参照元

| 領域 | PySide6側ファイル |
| --- | --- |
| メインウィンドウ、メニュー、ツールバー | `H:\mosicprogect\mosic2\app\ui\main_window.py` |
| プレビューキャンバス | `H:\mosicprogect\mosic2\app\ui\preview_canvas.py` |
| 左トラック一覧 | `H:\mosicprogect\mosic2\app\ui\track_list_panel.py` |
| 右プロパティパネル | `H:\mosicprogect\mosic2\app\ui\property_panel.py` |
| タイムライン | `H:\mosicprogect\mosic2\app\ui\timeline_widget.py` |
| 書き出し設定 | `H:\mosicprogect\mosic2\app\ui\export_settings_dialog.py` |
| 書き出しキュー | `H:\mosicprogect\mosic2\app\ui\export_queue_dialog.py` |
| モデル管理 | `H:\mosicprogect\mosic2\app\ui\model_management_dialog.py` |
| GPU、推論設定 | `H:\mosicprogect\mosic2\app\ui\gpu_settings_dialog.py` |
| 危険フレーム | `H:\mosicprogect\mosic2\app\ui\danger_warnings_section.py`, `dangerous_frames_dialog.py` |
| クラッシュ復旧 | `H:\mosicprogect\mosic2\app\ui\recovery_dialog.py` |
| ショートカット一覧 | `H:\mosicprogect\mosic2\app\ui\shortcuts.py`, `shortcut_help_dialog.py` |
| 文言 | `H:\mosicprogect\mosic2\app\ui\i18n.py` |

## 全体レイアウト

PySide6版のメイン画面は、上からメニューバー、ツールバー、中央編集領域、下タイムライン、ステータスバーで構成される。

```text
[メニューバー]
[ツールバー]
+--------------------+---------------------------+----------------------+
| 左: トラック一覧   | 中央: プレビューキャンバス | 右: プロパティ       |
| 幅目安 200         | 幅目安 920                | 幅目安 240           |
+--------------------+---------------------------+----------------------+
| 下: タイムライン、トランスポート、ズーム、スクロール               |
| 高さ目安 240                                                        |
+----------------------------------------------------------------------+
[ステータスバー]
```

実装上は、横方向の`QSplitter`に左トラック一覧、中央プレビュー、右プロパティを並べ、その下に縦方向の`QSplitter`でタイムラインを置いている。初期サイズは左200、中央920、右240、上段560、下段240。

Tauri版ではこの骨格を参考にしてよいが、固定幅の再現は不要。重要なのは、プレビュー、トラック、プロパティ、タイムラインを同時に見ながら編集できること。

## メニュー構成

### ファイル

| 表示 | ショートカット | 役割 | Tauri版での扱い |
| --- | --- | --- | --- |
| 動画を開く... | Ctrl+O | 新しい動画を読み込む | 必須。dirty guardとraw path保持を必ず通す |
| プロジェクトを保存... | Ctrl+S | 現在プロジェクト保存 | 必須。backend project stateを保存元にする |
| プロジェクトを読み込む... | Ctrl+Shift+O | 既存プロジェクト読み込み | 必須。schema migration込みで扱う |
| 終了 | Ctrl+Q | アプリ終了 | Tauri版ではウィンドウclose時のdirty guardに統合してよい |

### 編集

| 表示 | ショートカット | 役割 | Tauri版での扱い |
| --- | --- | --- | --- |
| 元に戻す | Ctrl+Z | Undo | 必須 |
| やり直し | Ctrl+Y, Ctrl+Shift+Z | Redo | 必須 |
| 多角形トラックを追加 | なし | 現在フレームに手動polygon trackを作る | 必須。Tauriではキャンバス操作や左パネルボタンでもよい |
| 追加 (K) | K | 現在フレームにkeyframe追加 | 必須 |
| 削除 (Shift+K) | Shift+K | 現在フレームのkeyframe削除 | 必須 |
| キーフレームを複製 | Ctrl+D | keyframe複製 | 必須 |
| 前のキーフレーム | [ | 選択trackの前keyframeへ移動 | 必須 |
| 次のキーフレーム | ] | 選択trackの次keyframeへ移動 | 必須 |
| パスを平滑化 | なし | polygon点列の平滑化 | 編集効率機能。主フロー後でよい |
| パスを間引き | なし | polygon点数の削減 | 編集効率機能。主フロー後でよい |

### 表示

| 表示 | ショートカット | 役割 | Tauri版での扱い |
| --- | --- | --- | --- |
| モザイクプレビュー | M | モザイク適用後表示の切替 | 必須 |
| 補間を表示 | なし | interpolated stateの表示切替 | 必須寄り |
| 予測を表示 | なし | predicted stateの表示切替 | 必須寄り |
| デバッグ表示 | なし | 内部状態確認 | 開発者向けとして残すか、review build限定にする |
| 差分オーバーレイ（実験的） | Shift+M | 前後keyframe差分表示 | 後回し。初期同等体験には不要 |

### 検出

| 表示 | ショートカット | 役割 | Tauri版での扱い |
| --- | --- | --- | --- |
| マスクを自動検出... | なし | 全区間検出 | 必須 |
| 選択区間のみ検出... | Ctrl+Shift+R | In/Out区間だけ検出 | 必須 |
| 現在フレームを検出 | Ctrl+Shift+D | 現在フレームだけ検出 | 必須 |

### 書き出し

| 表示 | ショートカット | 役割 | Tauri版での扱い |
| --- | --- | --- | --- |
| 動画を書き出す... | Ctrl+M | 書き出し設定を開いてexport | 必須 |
| 書き出しキューを表示 | Ctrl+E | queue dialogを開く | Phase 3以降の運用機能 |

### 設定

| 表示 | 役割 | Tauri版での扱い |
| --- | --- | --- |
| 検出モデル管理... | モデル配置、導入状態、EraX変換、導入済みモデル選択 | 必須寄り。検出が不透明にならないよう状態表示が必要 |
| デバイス / 推論設定... | GPU/CPU、検出間隔、推論解像度、batch、confidence、輪郭設定 | 必須寄り。GPUは起動要件にしない |

### ヘルプ

| 表示 | ショートカット | 役割 | Tauri版での扱い |
| --- | --- | --- | --- |
| ショートカット一覧 | F1 | 検索可能なshortcut help | 必須寄り。AI実装時の迷いを減らす |
| バージョン情報 | なし | about表示 | 任意 |

## ツールバー構成

PySide6版のツールバーは、使用頻度の高い操作を左から順に並べている。

| 順序 | UI | 役割 | 備考 |
| --- | --- | --- | --- |
| 1 | 開く | 動画を開く | ファイル操作 |
| 2 | 保存 | project保存 | ファイル操作 |
| 3 | 元に戻す | Undo | 編集操作 |
| 4 | やり直し | Redo | 編集操作 |
| 5 | 検出エンジン: combo | backend選択 | 160px程度のcombo |
| 6 | 対象カテゴリ dropdown | 検出カテゴリ選択 | `QToolButton`のpopup menu |
| 7 | 詳細設定... | GPU/推論設定dialog | 設定メニューにも存在 |
| 8 | 自動検出 dropdown | 全区間検出、選択区間のみ検出 | main detect action |
| 9 | フレーム検出 | 現在フレーム検出 | dropdown外に直接露出 |
| 10 | 書き出し | export dialog | danger warning gateが必要 |
| 11 | KF追加 | keyframe追加 | 高頻度操作 |
| 12 | KF削除 | keyframe削除 | 高頻度操作 |

Tauri版では、メニューとツールバーを完全に分ける必要はない。上部アクションバー、右パネル、コマンドパレットなどに再配置してよい。ただし「検出エンジン」「対象カテゴリ」「検出開始」「書き出し」「KF追加/削除」は、作業中に探さず使える位置に必要。

## 左パネル: トラック一覧

左パネルは編集対象の選択、危険フレーム確認、track visibility/export対象、表示補助設定、動画情報をまとめている。

### 上部構成

| 領域 | UI | 役割 |
| --- | --- | --- |
| 危険フレーム警告 | 警告件数header、折りたたみ、警告行 | warningがある時だけ表示 |
| 編集対象 | 折りたたみsection | track listの主領域 |
| 表示mode | combo | 現在フレーム、同一ラベル、全トラック、デバッグ |
| summary | label | 現在のtrack表示概要 |
| track scroll | grouped track rows | track選択、group開閉 |
| 多角形追加 | button | manual polygon track追加 |

### Track row

各track rowは高さ46px前後で、以下を横並びにしている。

| 位置 | UI | 内容 |
| --- | --- | --- |
| 左端 | color bar | track色 |
| 中央上 | track名 | manual/user locked時は`[M]`表示 |
| 中央中 | frame state | 現在フレームでの状態 |
| 中央下 | range | 検出範囲、予測延長範囲 |
| 右1 | 書出/除外 button | export対象切替 |
| 右2 | 非表示/表示 button | preview/timeline表示切替 |

### Track context menu

左パネルのtrack row右クリックでは次を出す。

| 表示 | 役割 |
| --- | --- |
| KF を追加 | 対象trackに現在フレームkeyframe追加 |
| 複製 | track複製 |
| 分割（現在フレーム） | 現在フレームでtrack split |
| 非表示にする / 表示する | track visibility切替 |
| 削除 | track削除 |

### 下部section

| Section | UI | 役割 |
| --- | --- | --- |
| トラック | 選択track名、type、range、state、confidence | 詳細確認 |
| 表示設定 | 頂点ハンドルサイズ、onion skin切替/range、diff overlay切替/range | 表示補助 |
| 位置調整 | 上、下、左、右、拡大、縮小 | 選択trackを小刻みに調整 |
| 動画情報 | video summary、detect summary、未保存表示 | 状態確認 |

Tauri版では、危険フレームを左パネルに固定する必要はないが、常時見える領域か、明確なreview panelとして扱う必要がある。

## 中央: プレビューキャンバス

プレビューは動画フレームとmask overlayを表示し、直接編集の主操作を受ける。PySide6版では`QGraphicsView`上で編集している。

### 直接操作

| 操作 | 対象 | 役割 |
| --- | --- | --- |
| 左クリック | mask内部 | track選択 |
| 左ドラッグ | mask内部 | track移動 |
| corner handle drag | ellipse/polygon bbox | uniform scale |
| edge handle drag | ellipse | 横または縦方向resize |
| polygon vertex drag | polygon | 単一頂点移動 |
| Shift + vertex click | polygon | 複数頂点選択 |
| 複数頂点選択後drag | polygon | 複数頂点移動 |
| edge付近double click | polygon edge | 頂点追加 |
| Alt + right click on vertex | polygon vertex | 頂点削除 |
| 空白右クリック | canvas | ここに多角形track追加 |
| mask右クリック | track | context menu |

### Canvas context menu

空白右クリック:

| 表示 | 役割 |
| --- | --- |
| ここに多角形トラックを追加 | クリック位置中心でmanual polygon作成 |

mask右クリック:

| 表示 | 役割 |
| --- | --- |
| キーフレームを追加 | 現在フレームにkeyframe追加 |
| キーフレームを削除 | 現在フレームのkeyframe削除 |
| ここに頂点を追加 | polygonのみ |
| 最近傍の頂点を削除 | polygonのみ |
| トラックを複製 | track複製 |
| トラックを非表示 | visibility off |
| ここでトラックを分割 | split |
| トラックを削除 | delete |

Tauri版では、同じ操作をCanvas上で再現する価値が高い。ただしcontext menuの文言や表示順はWeb UIとして調整してよい。

## 右パネル: プロパティ

右パネルは選択中track/keyframeに対する高頻度編集を置く。低頻度のtrack情報や表示設定はPySide6版では左パネルへ寄せられている。

| Section | UI | 役割 |
| --- | --- | --- |
| 選択中track header | label | track名、export除外badge |
| モザイク設定 | preview checkbox、強度spin、拡張px spin | style編集 |
| キーフレーム | 状態label、追加、削除、前、次、複製、keyframe list | keyframe操作 |
| 輪郭追従 | interval combo、forward/backward button、status | polygon補助 |
| マスク編集 | status、hint、平滑化、間引き、warning | polygon編集補助 |

Tauri版では、右パネルを「選択対象の詳細と編集」に集中させる方がよい。動画情報、検出summary、危険警告などは別のstatus/review領域に分けてもよい。

## 下部: タイムライン

PySide6版のタイムラインは、transport barとtimeline canvasを同じwidget内に持つ。

### Transport bar

左から以下の順で配置される。

| 位置 | UI | 役割 |
| --- | --- | --- |
| 左 | frame label | 現在frame/総frame |
| 左 | timecode label | 現在timecode |
| 左 | x button | In/Out区間clear |
| 左 | range label | 現在の選択区間 |
| 中央左 | `[` button | In点設定 |
| 中央左 | 前KF | 選択trackの前keyframeへ |
| 中央 | 10f戻る、1f戻る、再生/停止、1f進む、10f進む | transport |
| 中央右 | 次KF | 選択trackの次keyframeへ |
| 中央右 | `]` button | Out点設定 |
| 右 | speed combo | 0.25x、0.5x、1.0x、2.0x |
| 右 | info label | 解像度、fps、duration |
| 右 | zoom slider | timeline zoom |
| 右 | zoom value | zoom倍率 |

### Timeline canvas

| UI | 役割 |
| --- | --- |
| track rows | trackごとのbar、keyframe marker、segment stateを表示 |
| playhead | 現在frame |
| danger marker | 危険frame表示 |
| In/Out marker | 選択区間表示 |
| vertical scrollbar | track数が多い場合の縦スクロール |
| horizontal scrollbar | zoom時の横スクロール |
| undetected zone context | 未検出区間から検出、区間選択 |

未検出区間の右クリックでは、「この区間を検出」「この区間を選択 (In/Out)」を出す。

Tauri版でもtimelineは下部固定が自然。重要なのは、track stateとdanger markerとIn/Out範囲が同じ時間軸上で見えること。

## 危険フレームUI

PySide6版には2種類の危険フレームUIがある。

| UI | 場所 | 内容 |
| --- | --- | --- |
| DangerWarningsSection | 左パネル上部 | 件数header、折りたたみ、warning row、確認button |
| DangerousFramesDialog | export前 | 「確認する」「無視して書き出す」「キャンセル」 |

Warning rowはframe番号、理由、track label、確認buttonを持つ。行クリックで該当frameへseekし、確認済みでもseekできる。確認buttonは再クリックで解除できる。

Tauri版では、export前のwarning gateを特に優先する。未確認warningがある場合、ユーザーが確認へ戻るか、明示的に無視してexportするかを選べる必要がある。

## 書き出し設定

書き出し設定dialogは、縦方向に以下のgroupを並べる。

| Group | UI | 内容 |
| --- | --- | --- |
| プリセット | combo、保存、削除 | built-in/user preset |
| 映像 | 保存形式、codec、解像度、bitrate mode、手動bitrate slider/spin、目標file size、予想file size、GPU checkbox | export video settings |
| 音声 | 音声mode、音声bitrate | copy/AACなど |
| 保存先 | folder input、参照、file name input | output path |
| footer | 書き出し開始、キャンセル | accept/reject |

解像度は入力より大きい項目を無効化する。bitrate modeは自動、手動、サイズ指定を持つ。手動時はsliderと数値入力が連動し、サイズ指定時はtarget sizeからbitrateを計算する。

Tauri版では、書き出し設定はdialogでもside panelでもよい。必須なのは、設定値がproject/backendへ明示的に渡り、export jobのprogress/cancel/fallbackと結び付くこと。

## 書き出しキュー

書き出しキューdialogは非modalで、上部button、左table、右detail panel、footerで構成される。

### Top buttons

| 表示 | 役割 |
| --- | --- |
| 現在のプロジェクトを追加 | 現在projectをqueueへ追加 |
| 選択ジョブ開始 | selected job開始 |
| 全体開始 | queued jobsを順次実行 |
| 中止 | selected/running job中止 |
| 削除 | selected job削除 |

### Table columns

| 列 | 内容 |
| --- | --- |
| 入力動画 | source video name |
| 出力ファイル名 | output file name |
| 保存先 | output dir |
| 形式 | container |
| コーデック | codec |
| 解像度 | resolved resolution |
| ビットレート | bitrate label |
| GPU | GPU setting |
| ステータス | queued/running/completed/error/canceled/interrupted |
| 進捗 | progress bar |
| 操作 | 開始、中止、削除 |

### Detail panel

選択jobのpreset、format、codec、resolution、bitrate、GPU、保存先、file nameを編集できる。状態groupには状態、現在の処理、残り時間、メッセージを表示する。

Tauri版ではPhase 3以降でよいが、長時間exportを扱うならqueueとinterrupted recoveryは重要。

## モデル管理

モデル管理dialogはtab構成。

| Tab | UI | 役割 |
| --- | --- | --- |
| モデルの取得 | intro、model folder表示、モデルフォルダを開く、再チェック、model table、EraX変換section | モデル導入案内 |
| 導入済みモデル | installed table、選択したモデルに切替 | backend選択 |

モデル取得tableは、モデル名、説明、取得アクション、導入状況、対応対象カテゴリを表示する。EraXは通常一覧と別sectionで、`.pt`からONNXへの変換buttonを持つ。

Tauri版では、モデルの有無、broken状態、license注意、backend未対応をユーザーが判断できる表示が必要。

## デバイス / 推論設定

GPU設定dialogはgroup boxを縦に並べる。

| Group | UI | 内容 |
| --- | --- | --- |
| デバイス状態 | 使用デバイス、CUDA、VRAM、ONNX Runtime GPU | 現在状態 |
| デバイス選択 | device combo | auto、cuda、cpu |
| 検出設定 | sample every、max samples、inference resolution、batch size、confidence threshold | detection runtime設定 |
| 輪郭抽出 | contour mode、顔の精密輪郭checkbox | polygon/contour品質 |
| VRAM節約 | VRAM節約mode checkbox | 自動調整 |
| footer | 適用、キャンセル | 保存 |

Tauri版では、GPU失敗をstartup blockerにしてはいけない。設定画面は「現在使えるもの」「選択中」「fallback理由」を分けて表示する。

## ショートカット

PySide6版は`shortcuts.py`を単一の表示元としてF1 dialogに使う。F1 dialogは検索box、カテゴリsection、該当なし表示、閉じるbuttonを持つ。

| カテゴリ | ショートカット |
| --- | --- |
| ファイル | Ctrl+O, Ctrl+S, Ctrl+Shift+O, Ctrl+Q |
| 編集 | Ctrl+Z, Ctrl+Y/Ctrl+Shift+Z, Delete |
| 再生・移動 | Space, 左右, Shift+左右, Home/End, Shift+Home/End, 上下, `[`/`]` |
| マーカー | I, O |
| トラック | N, H |
| キーフレーム | K, Shift+K, Ctrl+D |
| 検出 | Ctrl+Shift+D, Ctrl+Shift+R |
| 表示 | M, Shift+M |
| 書き出し | Ctrl+M, Ctrl+E |
| ヘルプ | F1 |

Tauri版でも、ショートカット定義は一箇所に集約し、メニュー表示、F1 help、実キーハンドラの不一致を避ける。

## 復旧、進捗、補助dialog

| Dialog | UI | 役割 |
| --- | --- | --- |
| クラッシュリカバリ | autosave候補list、復元、削除、後で決める、閉じる | file-backed recovery候補の処理 |
| 進捗dialog | title、step label、progress bar、cancel | detection/exportなどのjob進捗 |
| カテゴリ詳細 | groupごとのcheckbox、閉じる | model category確認 |

Tauri版では、復旧候補はlocalStorageだけに置かず、backend/file-backedに寄せる。進捗はmodalに閉じ込めず、job panelやtoastでもよいが、cancel可能であることが必要。

## Tauri版へ持ち込む優先度

| 優先度 | 持ち込むもの |
| --- | --- |
| 高 | 4領域の編集モデル、メニュー上の主要機能、toolbar相当の高頻度操作、canvas直接編集、timeline transport、danger warning gate |
| 中 | model management、GPU/inference settings、F1 help、export settings、track context menu、timeline context menu |
| 低 | onion skin、diff overlay、平滑化、間引き、contour follow、export queue |
| 移植しない | Qt widget構造、固定px幅、dialog中心の画面遷移、PySide6固有の描画実装 |

## Tauri UI設計時の注意

- PySide6版の左パネル、右パネル配置は参考になるが、情報が分散している部分はTauriで整理してよい。
- 「表示/非表示」と「書き出し対象/除外」は別概念としてUI上も分ける。
- 危険フレームは通常編集時とexport前の両方で見える必要がある。
- keyframe操作は、menu、toolbar、右パネル、canvas context menu、shortcutが同じbackend commandへ集約されるべき。
- detection engine、category、GPU/CPU状態は検出開始前に見える場所に置く。
- raw local pathとdisplay URLをUI都合で混ぜない。
- manual track、manual keyframe、user locked stateはUIからも保護状態が分かるようにする。
- PySide6版で「実験的」とされる差分オーバーレイなどは、初期同等体験の必須条件にしない。
