import { useEffect, useState } from "react";
import type { ResolveReason } from "../maskShapeResolver";
import type {
  CreateKeyframePayload,
  Keyframe,
  KeyframeShapeType,
  KeyframeSummary,
  TrackSummary,
  UpdateKeyframePayload,
} from "../types";
import {
  buildInspectorState,
  getBBoxLabel,
  getFrameIndexLabel,
  getPrimaryActionLabel,
  getSecondaryCreateLabel,
  parseInspectorInput,
  syncInspectorState,
  type KeyframeInspectorFieldErrors,
  type KeyframeInspectorState,
} from "../keyframeInspector";
import {
  resolveReasonBadgeVariant,
  resolveReasonLabel,
  sourceDetailLabel,
} from "../keyframeResolveDisplay";

type KeyframeDetailPanelProps = {
  track: TrackSummary | null;
  keyframe: KeyframeSummary | null;
  keyframeDocument: Keyframe | null;
  /** W9: resolve reason for the current frame — threaded for future badge UI. */
  resolvedReason?: ResolveReason | null;
  suggestedCreateFrame: number;
  onCreateKeyframe: (payload: Omit<CreateKeyframePayload, "project_path" | "track_id">) => Promise<void>;
  onDeleteKeyframe: () => void;
  onSaveKeyframe: (patch: UpdateKeyframePayload["patch"]) => Promise<boolean>;
  onReportError: (message: string) => void;
  onClearRemoteError: () => void;
  busy: boolean;
  remoteError: string;
};

export function KeyframeDetailPanel({
  track,
  keyframe,
  keyframeDocument,
  resolvedReason,
  suggestedCreateFrame,
  onCreateKeyframe,
  onDeleteKeyframe,
  onSaveKeyframe,
  onReportError,
  onClearRemoteError,
  busy,
  remoteError,
}: KeyframeDetailPanelProps) {
  const [formState, setFormState] = useState<KeyframeInspectorState>(buildInspectorState(keyframeDocument, suggestedCreateFrame));
  const [saving, setSaving] = useState<boolean>(false);
  const [localError, setLocalError] = useState<string>("");
  const [fieldErrors, setFieldErrors] = useState<KeyframeInspectorFieldErrors>({});
  const [frameIndexDirty, setFrameIndexDirty] = useState<boolean>(false);

  useEffect(() => {
    const nextBase = buildInspectorState(keyframeDocument, suggestedCreateFrame);
    setFormState((current) => syncInspectorState(current, nextBase, { preserveFrameIndex: frameIndexDirty }));
    setLocalError("");
    setFieldErrors({});
  }, [frameIndexDirty, keyframeDocument, suggestedCreateFrame]);

  function updateForm(patch: Partial<KeyframeInspectorState>) {
    setFormState((current) => ({ ...current, ...patch }));
    setLocalError("");
    onClearRemoteError();
    setFieldErrors((current) => ({
      ...current,
      ...(patch.frameIndexText !== undefined ? { frameIndex: undefined } : {}),
      ...(patch.bboxText !== undefined ? { bbox: undefined } : {}),
      ...(patch.pointsText !== undefined ? { points: undefined } : {}),
      ...(patch.rotationText !== undefined ? { rotation: undefined } : {}),
    }));
  }

  async function handleCreate() {
    if (busy) return;
    const parsed = parseInspectorInput(formState, keyframeDocument);
    if (parsed.error) {
      setLocalError(parsed.error);
      setFieldErrors(parsed.fieldErrors);
      onReportError(parsed.error);
      return;
    }

    setSaving(true);
    setLocalError("");
    setFieldErrors({});
    try {
      await onCreateKeyframe(parsed.value!);
      setFrameIndexDirty(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (busy) return;
    const parsed = parseInspectorInput(formState, keyframeDocument);
    if (parsed.error) {
      setLocalError(parsed.error);
      setFieldErrors(parsed.fieldErrors);
      onReportError(parsed.error);
      return;
    }

    setSaving(true);
    setLocalError("");
    setFieldErrors({});
    try {
      const { source, shape_type, bbox, points, rotation } = parsed.value!;
      await onSaveKeyframe({ source, shape_type, bbox, points, rotation });
    } finally {
      setSaving(false);
    }
  }

  function renderInspectorFields(mode: "create" | "update") {
    const disabled = saving || busy;
    return (
      <>
        <div className="nle-field">
          <span className="nle-field__label">{getFrameIndexLabel(mode)}</span>
          <input
            className="nle-field__input"
            disabled={disabled}
            value={formState.frameIndexText}
            onChange={(event) => {
              setFrameIndexDirty(true);
              updateForm({ frameIndexText: event.target.value });
            }}
          />
          {fieldErrors.frameIndex ? <span className="nle-field__error">{fieldErrors.frameIndex}</span> : null}
        </div>
        <div className="nle-field">
          <span className="nle-field__label">Shape</span>
          <select
            className="nle-field__select"
            disabled={disabled}
            value={formState.shapeType}
            onChange={(event) => updateForm({ shapeType: event.target.value as KeyframeShapeType })}
          >
            <option value="polygon">polygon</option>
            <option value="ellipse">ellipse</option>
          </select>
        </div>
        <div className="nle-field">
          <span className="nle-field__label">Source</span>
          <select
            className="nle-field__select"
            disabled={disabled}
            value={formState.source}
            onChange={(event) => updateForm({ source: event.target.value as "manual" | "detector" })}
          >
            <option value="manual">manual</option>
            <option value="detector">detector</option>
          </select>
        </div>
        <div className="nle-field">
          <span className="nle-field__label">{getBBoxLabel(formState.shapeType)}</span>
          <input
            className="nle-field__input"
            disabled={disabled}
            value={formState.bboxText}
            onChange={(event) => updateForm({ bboxText: event.target.value })}
          />
          {fieldErrors.bbox ? <span className="nle-field__error">{fieldErrors.bbox}</span> : null}
          {!fieldErrors.bbox ? <span className="nle-field__hint">x, y, w, h (normalized)</span> : null}
        </div>
        {formState.shapeType === "polygon" ? (
          <div className="nle-field">
            <span className="nle-field__label">Points JSON</span>
            <textarea
              className="nle-field__textarea"
              disabled={disabled}
              rows={4}
              value={formState.pointsText}
              onChange={(event) => updateForm({ pointsText: event.target.value })}
            />
            {fieldErrors.points ? <span className="nle-field__error">{fieldErrors.points}</span> : null}
          </div>
        ) : null}
        {formState.shapeType === "ellipse" ? (
          <div className="nle-field">
            <span className="nle-field__label">回転 (度)</span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                className="nle-field__input"
                type="range"
                min={-180}
                max={180}
                step={1}
                disabled={disabled}
                value={Number(formState.rotationText) || 0}
                onChange={(event) => updateForm({ rotationText: event.target.value })}
                style={{ flex: 1 }}
              />
              <input
                className="nle-field__input"
                type="number"
                min={-180}
                max={180}
                step={1}
                disabled={disabled}
                value={formState.rotationText}
                onChange={(event) => updateForm({ rotationText: event.target.value })}
                style={{ width: 72 }}
              />
            </div>
            {fieldErrors.rotation ? <span className="nle-field__error">{fieldErrors.rotation}</span> : null}
            {!fieldErrors.rotation ? <span className="nle-field__hint">-180〜180 度 (時計回り正)</span> : null}
          </div>
        ) : null}
        {localError ? <p className="nle-inspector-error">{localError}</p> : null}
        {remoteError ? <p className="nle-inspector-error">{remoteError}</p> : null}
      </>
    );
  }

  if (!track) {
    return <div className="nle-empty">トラックを選択するとキーフレーム編集を表示できます。</div>;
  }

  if (!keyframe && keyframeDocument) {
    // Resolved (held or interpolated) shape: no explicit keyframe at current frame,
    // but a prior/interpolated shape is displayed for editing.
    // Saving creates a new keyframe at currentFrame (handled by App.tsx).
    const reasonVariant = resolveReasonBadgeVariant(resolvedReason);
    const reasonText = resolveReasonLabel(resolvedReason) ?? "held";
    const sdLabel = sourceDetailLabel(keyframeDocument.source_detail);
    return (
      <div>
        <div style={{ marginBottom: 4, display: "flex", gap: 6, alignItems: "center" }}>
          <span className="nle-mode-badge nle-mode-badge--update">EDIT</span>
          <span className={`nle-mode-badge nle-mode-badge--${reasonVariant}`}>{reasonText}</span>
          {resolvedReason !== "interpolated" && (
            <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
              ← F{keyframeDocument.frame_index}
            </span>
          )}
        </div>
        {sdLabel !== null && (
          <div className="nle-resolve-info">
            <span className="nle-resolve-info__label">source_detail</span>
            <span className="nle-resolve-info__value">{sdLabel}</span>
          </div>
        )}
        {renderInspectorFields("update")}
        <div style={{ marginTop: 8, display: "flex", gap: 4 }}>
          <button className="nle-btn nle-btn--small nle-btn--accent" onClick={() => void handleSave()} disabled={saving || busy}>
            {getPrimaryActionLabel(formState.shapeType, "create", saving || busy)}
          </button>
        </div>
      </div>
    );
  }

  if (!keyframe) {
    return (
      <div>
        <div style={{ marginBottom: 6 }}>
          <span className="nle-mode-badge nle-mode-badge--create">NEW</span>
        </div>
        {renderInspectorFields("create")}
        <div style={{ marginTop: 8, display: "flex", gap: 4 }}>
          <button className="nle-btn nle-btn--small nle-btn--accent" onClick={() => void handleCreate()} disabled={saving || busy}>
            {getPrimaryActionLabel(formState.shapeType, "create", saving || busy)}
          </button>
        </div>
      </div>
    );
  }

  const sdLabel = sourceDetailLabel(keyframeDocument?.source_detail);
  return (
    <div>
      <div style={{ marginBottom: 4, display: "flex", gap: 6, alignItems: "center" }}>
        <span className="nle-mode-badge nle-mode-badge--update">EDIT</span>
        <span className="nle-mode-badge nle-mode-badge--explicit">explicit</span>
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
          F{keyframe.frame_index} / {keyframe.shape_type} / {keyframe.source}
        </span>
      </div>
      {sdLabel !== null && (
        <div className="nle-resolve-info">
          <span className="nle-resolve-info__label">source_detail</span>
          <span className="nle-resolve-info__value">{sdLabel}</span>
        </div>
      )}
      {renderInspectorFields("update")}
      <div style={{ marginTop: 8, display: "flex", gap: 4, flexWrap: "wrap" }}>
        <button className="nle-btn nle-btn--small nle-btn--accent" onClick={() => void handleSave()} disabled={saving || busy}>
          {getPrimaryActionLabel(formState.shapeType, "update", saving || busy)}
        </button>
        <button className="nle-btn nle-btn--small nle-btn--gold" onClick={() => void handleCreate()} disabled={saving || busy}>
          {getSecondaryCreateLabel(formState.shapeType, saving || busy)}
        </button>
        <button className="nle-btn nle-btn--small" onClick={onDeleteKeyframe} disabled={busy}>
          キーフレーム削除
        </button>
      </div>
    </div>
  );
}
