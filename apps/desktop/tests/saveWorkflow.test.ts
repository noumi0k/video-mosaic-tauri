import test from "node:test";
import assert from "node:assert/strict";

import {
  buildDirtyGuardCopy,
  canOpenVideoWithoutDirtyPrompt,
  hydratePersistedExportQueue,
  isHistoryRestoreDirty,
  shouldProceedAfterDirtyDecision,
  shouldSaveBeforeExport,
  shouldScheduleAutosave,
} from "../src/saveWorkflow.ts";

test("history restore stays dirty when a project snapshot exists", () => {
  assert.equal(isHistoryRestoreDirty(null), false);
  assert.equal(
    isHistoryRestoreDirty({
      project_id: "project-1",
      version: "0.1.0",
      schema_version: 2,
      name: "Sample",
      project_path: "C:/sample.json",
      video: null,
      tracks: [],
      detector_config: {},
      export_preset: { mosaic_strength: 12, audio_mode: "mux_if_possible", last_output_dir: null },
      paths: { project_dir: null, export_dir: null, training_dir: null },
    }),
    true
  );
});

test("autosave only runs for dirty saved projects when the editor is idle", () => {
  const project = {
    project_id: "project-1",
    version: "0.1.0",
    schema_version: 2,
    name: "Sample",
    project_path: "C:/sample.json",
    video: null,
    tracks: [],
    detector_config: {},
    export_preset: { mosaic_strength: 12, audio_mode: "mux_if_possible", last_output_dir: null },
    paths: { project_dir: null, export_dir: null, training_dir: null },
  };

  assert.equal(
    shouldScheduleAutosave({
      project,
      isDirty: true,
      mutationBusy: false,
      exportBusy: false,
      autosaveBusy: false,
    }),
    true
  );
  assert.equal(
    shouldScheduleAutosave({
      project,
      isDirty: true,
      mutationBusy: true,
      exportBusy: false,
      autosaveBusy: false,
    }),
    false
  );
  assert.equal(
    shouldScheduleAutosave({
      project: { ...project, project_path: null },
      isDirty: true,
      mutationBusy: false,
      exportBusy: false,
      autosaveBusy: false,
    }),
    false
  );
});

test("dirty guard copy matches saved and unsaved project contexts", () => {
  assert.match(buildDirtyGuardCopy("C:/sample.json").summary, /保存されていない変更/);
  assert.match(buildDirtyGuardCopy(null).summary, /現在のセッションにしか存在しません/);
});

test("dirty guard decisions proceed only for discard or a successful save", () => {
  assert.equal(shouldProceedAfterDirtyDecision("discard", false), true);
  assert.equal(shouldProceedAfterDirtyDecision("cancel", true), false);
  assert.equal(shouldProceedAfterDirtyDecision("save", true), true);
  assert.equal(shouldProceedAfterDirtyDecision("save", false), false);
});

test("export queue hydration converts abandoned running jobs to interrupted", () => {
  const restored = hydratePersistedExportQueue([
    {
      queue_id: "queue-1",
      job_id: "job-1",
      project_path: "C:/sample.json",
      project_name: "Sample",
      output_path: "C:/out.mp4",
      options: { mosaic_strength: 12, audio_mode: "mux_if_possible" },
      state: "running",
      progress: 42,
      status_text: "Rendering",
      warnings: [],
      audio_status: null,
    },
  ]);

  assert.equal(restored.recoveredInterrupted, true);
  assert.equal(restored.queue[0]?.state, "interrupted");
  assert.equal(restored.queue[0]?.progress, 0);
});

test("export requires a save when the local project is dirty", () => {
  const savedProject = {
    project_id: "project-1",
    version: "0.1.0",
    schema_version: 2,
    name: "Sample",
    project_path: "C:/sample.json",
    video: null,
    tracks: [],
    detector_config: {},
    export_preset: { mosaic_strength: 12, audio_mode: "mux_if_possible", last_output_dir: null },
    paths: { project_dir: null, export_dir: null, training_dir: null },
  };

  assert.equal(shouldSaveBeforeExport(savedProject, true), true);
  assert.equal(shouldSaveBeforeExport(savedProject, false), false);
  assert.equal(shouldSaveBeforeExport({ ...savedProject, project_path: null }, true), false);
});

test("open video skips the dirty prompt for an empty unsaved project", () => {
  const emptyUnsavedProject = {
    project_id: "project-1",
    version: "0.1.0",
    schema_version: 2,
    name: "Sample",
    project_path: null,
    video: null,
    tracks: [],
    detector_config: {},
    export_preset: { mosaic_strength: 12, audio_mode: "mux_if_possible", last_output_dir: null },
    paths: { project_dir: null, export_dir: null, training_dir: null },
  };

  assert.equal(canOpenVideoWithoutDirtyPrompt(emptyUnsavedProject, true), true);
  assert.equal(
    canOpenVideoWithoutDirtyPrompt({ ...emptyUnsavedProject, tracks: [{ track_id: "t1" }] as never[] }, true),
    false
  );
  assert.equal(
    canOpenVideoWithoutDirtyPrompt({ ...emptyUnsavedProject, video: { source_path: "C:/clip.mp4" } as never }, true),
    false
  );
});
