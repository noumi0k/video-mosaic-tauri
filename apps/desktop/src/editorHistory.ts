import type { ProjectDocument, ProjectReadModel } from "./types";
import type { SelectionCandidate } from "./editorSelection";

export type EditorHistorySnapshot = {
  project: ProjectDocument | null;
  readModel: ProjectReadModel | null;
  selection: SelectionCandidate;
};

export type EditorHistoryState = {
  past: EditorHistorySnapshot[];
  present: EditorHistorySnapshot | null;
  future: EditorHistorySnapshot[];
};

export function createEmptyHistory(): EditorHistoryState {
  return {
    past: [],
    present: null,
    future: []
  };
}

export function createHistorySnapshot(
  project: ProjectDocument | null,
  readModel: ProjectReadModel | null,
  selection: SelectionCandidate
): EditorHistorySnapshot {
  return {
    project,
    readModel,
    selection
  };
}

export function resetHistory(snapshot: EditorHistorySnapshot | null): EditorHistoryState {
  return {
    past: [],
    present: snapshot,
    future: []
  };
}

export function pushHistory(state: EditorHistoryState, snapshot: EditorHistorySnapshot): EditorHistoryState {
  return {
    past: state.present ? [...state.past, state.present] : state.past,
    present: snapshot,
    future: []
  };
}

export function undoHistory(state: EditorHistoryState): EditorHistoryState {
  if (!state.past.length || !state.present) {
    return state;
  }
  const previous = state.past[state.past.length - 1]!;
  return {
    past: state.past.slice(0, -1),
    present: previous,
    future: [state.present, ...state.future]
  };
}

export function redoHistory(state: EditorHistoryState): EditorHistoryState {
  if (!state.future.length || !state.present) {
    return state;
  }
  const next = state.future[0]!;
  return {
    past: [...state.past, state.present],
    present: next,
    future: state.future.slice(1)
  };
}
