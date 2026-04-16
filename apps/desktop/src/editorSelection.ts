import type { EditorSessionState, ProjectDocument, ProjectReadModel } from "./types";

export type SelectionCandidate = {
  trackId: string | null;
  frameIndex: number | null;
};

export function resolveSelection(
  readModel: ProjectReadModel | null,
  preferred: SelectionCandidate
): SelectionCandidate {
  if (!readModel?.track_summaries.length) {
    return { trackId: null, frameIndex: null };
  }

  const track =
    (preferred.trackId
      ? readModel.track_summaries.find((item) => item.track_id === preferred.trackId) ?? null
      : null) ?? null;

  if (!track) {
    return { trackId: null, frameIndex: null };
  }

  if (preferred.frameIndex === null) {
    return { trackId: track.track_id, frameIndex: null };
  }

  const keyframe = track.keyframes.find((item) => item.frame_index === preferred.frameIndex) ?? null;
  return {
    trackId: track.track_id,
    frameIndex: keyframe?.frame_index ?? null
  };
}

export function buildEditorState(
  nextProject: ProjectDocument | null,
  nextReadModel: ProjectReadModel | null,
  preferred: SelectionCandidate,
  previousMode: EditorSessionState["editorMode"] = "read-only"
): EditorSessionState {
  const selection = resolveSelection(nextReadModel, preferred);
  return {
    selectedTrackId: selection.trackId,
    selectedKeyframeFrame: selection.frameIndex,
    editorMode: previousMode,
    isDirty: false,
    pendingProjectPath: nextProject?.project_path ?? null,
    writeTracks: (nextProject?.tracks ?? []).map((track) => ({
      track_id: track.track_id,
      label: track.label,
      state: track.state,
      source: track.source,
      visible: track.visible,
      export_enabled: track.export_enabled ?? true,
      keyframes: track.keyframes.map((keyframe) => ({
        frame_index: keyframe.frame_index,
        shape_type: keyframe.shape_type,
        source: keyframe.source
      }))
    }))
  };
}
