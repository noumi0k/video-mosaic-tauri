import { useEffect } from "react";

type ShortcutHelpModalProps = {
  open: boolean;
  onClose: () => void;
};

type ShortcutEntry = {
  keys: string;
  description: string;
};

type ShortcutGroup = {
  title: string;
  entries: ShortcutEntry[];
};

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "プロジェクト",
    entries: [
      { keys: "Ctrl+S", description: "保存" },
      { keys: "Ctrl+Shift+S", description: "名前を付けて保存" },
      { keys: "Ctrl+Z", description: "元に戻す" },
      { keys: "Ctrl+Shift+Z / Ctrl+Y", description: "やり直す" },
    ],
  },
  {
    title: "再生 / シーク",
    entries: [
      { keys: "Space", description: "再生 / 一時停止" },
      { keys: "← / →", description: "±1 フレーム (Shift で ±10)" },
      { keys: "Home / End", description: "先頭 / 末尾フレームへ" },
      { keys: "Shift+Home / Shift+End", description: "選択トラックの開始 / 終了フレームへ" },
      { keys: "[ / ] / ↑ / ↓", description: "前 / 次のキーフレームへ移動" },
    ],
  },
  {
    title: "キーフレーム",
    entries: [
      { keys: "K", description: "現在フレームにキーフレーム追加" },
      { keys: "Shift+K", description: "選択中のキーフレーム削除" },
      { keys: "Ctrl+D", description: "キーフレームを複製" },
    ],
  },
  {
    title: "トラック",
    entries: [
      { keys: "N", description: "楕円トラック追加" },
      { keys: "Shift+N", description: "多角形トラック追加" },
      { keys: "H", description: "選択トラックの表示切替" },
      { keys: "Delete", description: "選択トラックを削除" },
    ],
  },
  {
    title: "プレビュー",
    entries: [
      { keys: "M", description: "モザイクプレビューのトグル" },
      { keys: "Shift+M", description: "差分オーバーレイのトグル (モザイク適用領域)" },
    ],
  },
  {
    title: "範囲指定",
    entries: [
      { keys: "I", description: "イン点を設定" },
      { keys: "O", description: "アウト点を設定" },
    ],
  },
  {
    title: "検出 / 書き出し",
    entries: [
      { keys: "Ctrl+Shift+D", description: "現在フレームを AI 検出" },
      { keys: "Ctrl+Shift+R", description: "In〜Out 範囲を AI 検出 (マーカー未設定時は動画全体)" },
      { keys: "Ctrl+M", description: "書き出し設定モーダルを開く" },
    ],
  },
  {
    title: "ヘルプ",
    entries: [{ keys: "F1", description: "このショートカット一覧を表示" }],
  },
];

export function ShortcutHelpModal({ open, onClose }: ShortcutHelpModalProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="nle-modal-overlay" onClick={onClose}>
      <div
        className="nle-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ minWidth: 460, maxWidth: 640, maxHeight: "80vh", overflowY: "auto" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-help-title"
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 id="shortcut-help-title" style={{ margin: 0 }}>キーボードショートカット</h3>
          <button className="nle-btn nle-btn--small" onClick={onClose} aria-label="閉じる">
            ×
          </button>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {SHORTCUT_GROUPS.map((group) => (
            <section key={group.title}>
              <h4 style={{ margin: "0 0 4px", fontSize: 13, color: "var(--text-dim)" }}>{group.title}</h4>
              <table className="nle-shortcut-table">
                <tbody>
                  {group.entries.map((entry) => (
                    <tr key={entry.keys}>
                      <td className="nle-shortcut-table__keys">
                        <code>{entry.keys}</code>
                      </td>
                      <td className="nle-shortcut-table__desc">{entry.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
        </div>
        <div style={{ marginTop: 12, textAlign: "right" }}>
          <button className="nle-btn nle-btn--small" onClick={onClose}>
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
