"""
Tests for source_detail plumbing: load path, normalization, save/load round-trip,
and detect write-path tagging.

source_detail is an optional Keyframe field:
  - None        : legacy keyframes (no detail recorded)
  - "detector_accepted"  : WRITE_DETECTED via evaluate_continuity
  - "detector_anchored"  : WRITE_ANCHORED via evaluate_continuity
"""
from __future__ import annotations

import copy
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from auto_mosaic.domain.mask_continuity import (
    CandidateBBox,
    WriteAction,
    WriteDecision,
    apply_write_action,
)
from auto_mosaic.domain.project import Keyframe, MaskTrack, ProjectDocument, _normalize_keyframe_payload
from auto_mosaic.infra.ai.detect_video import _TrackCursor, _apply_frame_detections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL_DIR = Path(tempfile.mkdtemp(prefix="taurimozaic-source-detail-"))
_MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _frame() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


def _det(bbox: list[float], score: float) -> dict:
    return {"bbox_norm": bbox, "score": score}


def _minimal_kf_payload(**overrides) -> dict:
    base = {
        "frame_index": 0,
        "shape_type": "polygon",
        "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        "bbox": [0.1, 0.1, 0.1, 0.1],
        "confidence": 0.9,
        "source": "manual",
    }
    base.update(overrides)
    return base


def _anchor_kf(frame: int = 0) -> Keyframe:
    return Keyframe(
        frame_index=frame,
        shape_type="polygon",
        points=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        bbox=[0.1, 0.1, 0.1, 0.1],
        confidence=0.9,
        source="manual",
        source_detail=None,
    )


# ---------------------------------------------------------------------------
# Load path: legacy payloads without source_detail
# ---------------------------------------------------------------------------

def test_normalize_keyframe_without_source_detail_gives_none() -> None:
    """Legacy payload with no source_detail key normalizes to None."""
    payload = _minimal_kf_payload()
    assert "source_detail" not in payload
    result = _normalize_keyframe_payload(payload)
    assert "source_detail" in result
    assert result["source_detail"] is None


def test_normalize_keyframe_with_null_source_detail_gives_none() -> None:
    """Explicit null in payload also normalizes to None."""
    payload = _minimal_kf_payload(source_detail=None)
    result = _normalize_keyframe_payload(payload)
    assert result["source_detail"] is None


def test_normalize_keyframe_with_empty_string_gives_none() -> None:
    """Empty string normalizes to None (defensive clean-up)."""
    payload = _minimal_kf_payload(source_detail="")
    result = _normalize_keyframe_payload(payload)
    assert result["source_detail"] is None


def test_normalize_keyframe_with_valid_source_detail_preserved() -> None:
    """Non-empty source_detail is preserved verbatim."""
    payload = _minimal_kf_payload(source_detail="detector_accepted")
    result = _normalize_keyframe_payload(payload)
    assert result["source_detail"] == "detector_accepted"


def test_from_payload_legacy_keyframe_source_detail_is_none() -> None:
    """Keyframe.from_payload with no source_detail in payload gives source_detail=None."""
    payload = _minimal_kf_payload()
    kf = Keyframe.from_payload(payload)
    assert kf.source_detail is None


# ---------------------------------------------------------------------------
# Save/load round-trip: source_detail persists through asdict → from_payload
# ---------------------------------------------------------------------------

def test_roundtrip_detector_accepted() -> None:
    kf = Keyframe(
        frame_index=5,
        shape_type="ellipse",
        points=[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
        bbox=[0.1, 0.1, 0.2, 0.2],
        confidence=0.85,
        source="detector",
        source_detail="detector_accepted",
    )
    d = asdict(kf)
    assert d["source_detail"] == "detector_accepted"
    kf2 = Keyframe.from_payload(d)
    assert kf2.source_detail == "detector_accepted"


def test_roundtrip_detector_anchored() -> None:
    kf = Keyframe(
        frame_index=10,
        shape_type="polygon",
        points=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        bbox=[0.1, 0.1, 0.1, 0.1],
        confidence=0.70,
        source="detector",
        source_detail="detector_anchored",
    )
    d = asdict(kf)
    assert d["source_detail"] == "detector_anchored"
    kf2 = Keyframe.from_payload(d)
    assert kf2.source_detail == "detector_anchored"


def test_roundtrip_none_source_detail() -> None:
    """Legacy keyframe with source_detail=None round-trips correctly."""
    kf = Keyframe(
        frame_index=0,
        shape_type="polygon",
        points=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        bbox=[0.1, 0.1, 0.1, 0.1],
        confidence=1.0,
        source="manual",
        source_detail=None,
    )
    d = asdict(kf)
    assert d["source_detail"] is None
    kf2 = Keyframe.from_payload(d)
    assert kf2.source_detail is None


def test_project_roundtrip_preserves_source_detail() -> None:
    """Full ProjectDocument.from_payload round-trip preserves source_detail."""
    project_payload = {
        "project_id": "test-proj",
        "schema_version": 2,
        "version": "0.1.0",
        "name": "Test",
        "project_path": None,
        "video": None,
        "tracks": [
            {
                "track_id": "t1",
                "label": "T1",
                "state": "detected",
                "source": "detector",
                "visible": True,
                "keyframes": [
                    {
                        "frame_index": 3,
                        "shape_type": "ellipse",
                        "points": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
                        "bbox": [0.1, 0.1, 0.2, 0.2],
                        "confidence": 0.88,
                        "source": "detector",
                        "source_detail": "detector_accepted",
                    },
                    {
                        "frame_index": 7,
                        "shape_type": "polygon",
                        "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
                        "bbox": [0.1, 0.1, 0.1, 0.1],
                        "confidence": 0.72,
                        "source": "detector",
                        "source_detail": "detector_anchored",
                    },
                    {
                        "frame_index": 15,
                        "shape_type": "polygon",
                        "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
                        "bbox": [0.1, 0.1, 0.1, 0.1],
                        "confidence": 1.0,
                        "source": "manual",
                        # No source_detail key — legacy keyframe
                    },
                ],
                "segments": [],
            }
        ],
        "detector_config": {},
        "export_preset": {},
        "paths": {},
    }

    project = ProjectDocument.from_payload(project_payload)
    track = project.tracks[0]

    kf3 = next(kf for kf in track.keyframes if kf.frame_index == 3)
    kf7 = next(kf for kf in track.keyframes if kf.frame_index == 7)
    kf15 = next(kf for kf in track.keyframes if kf.frame_index == 15)

    assert kf3.source_detail == "detector_accepted"
    assert kf7.source_detail == "detector_anchored"
    assert kf15.source_detail is None

    # Serialize and reload — values must survive.
    d = project.to_dict()
    project2 = ProjectDocument.from_payload(d)
    track2 = project2.tracks[0]

    kf3b = next(kf for kf in track2.keyframes if kf.frame_index == 3)
    kf7b = next(kf for kf in track2.keyframes if kf.frame_index == 7)
    kf15b = next(kf for kf in track2.keyframes if kf.frame_index == 15)

    assert kf3b.source_detail == "detector_accepted"
    assert kf7b.source_detail == "detector_anchored"
    assert kf15b.source_detail is None


# ---------------------------------------------------------------------------
# Detect write-path tagging: W4 builders set correct source_detail
# ---------------------------------------------------------------------------

def test_apply_write_action_detected_sets_detector_accepted() -> None:
    """apply_write_action(WRITE_DETECTED) produces source_detail='detector_accepted'."""
    track = MaskTrack(
        track_id="t1", label="T", state="detected", source="detector", visible=True,
    )
    cand = CandidateBBox(bbox=(0.1, 0.1, 0.2, 0.2), confidence=0.85, shape_type="ellipse")
    apply_write_action(track, 5, cand, WriteDecision(action=WriteAction.WRITE_DETECTED))
    kf = track.keyframes[0]
    assert kf.source_detail == "detector_accepted"


def test_apply_write_action_anchored_sets_detector_anchored() -> None:
    """apply_write_action(WRITE_ANCHORED) produces source_detail='detector_anchored'."""
    anchor = _anchor_kf(frame=0)
    track = MaskTrack(
        track_id="t1", label="T", state="detected", source="detector", visible=True,
        keyframes=[anchor],
    )
    cand = CandidateBBox(bbox=(0.15, 0.15, 0.2, 0.2), confidence=0.70, shape_type="polygon")
    apply_write_action(track, 5, cand, WriteDecision(action=WriteAction.WRITE_ANCHORED, anchor_frame=0))
    kf = track.keyframes[1]
    assert kf.frame_index == 5
    assert kf.source_detail == "detector_anchored"


def test_apply_write_action_detected_fallback_from_missing_anchor_sets_accepted() -> None:
    """When WRITE_ANCHORED falls back to detected (anchor vanished), result is detector_accepted."""
    track = MaskTrack(
        track_id="t1", label="T", state="detected", source="detector", visible=True,
    )
    cand = CandidateBBox(bbox=(0.1, 0.1, 0.2, 0.2), confidence=0.80, shape_type="ellipse")
    # anchor_frame=99 doesn't exist → _build_anchored_keyframe falls back to _build_detected_keyframe
    apply_write_action(track, 5, cand, WriteDecision(action=WriteAction.WRITE_ANCHORED, anchor_frame=99))
    kf = track.keyframes[0]
    assert kf.source_detail == "detector_accepted"


# ---------------------------------------------------------------------------
# Detect path (via _apply_frame_detections): WRITE_DETECTED sets detector_accepted
# ---------------------------------------------------------------------------

def test_detect_path_write_detected_sets_detector_accepted() -> None:
    """First detection on a new track sets source_detail='detector_accepted'."""
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    kf = tracks[0].keyframes[0]
    assert kf.source == "detector"
    assert kf.source_detail == "detector_accepted"


def test_detect_path_write_detected_subsequent_sets_detector_accepted() -> None:
    """Consistent follow-on detection (ACCEPT) also gets detector_accepted."""
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.92)],
        2, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    kf2 = tracks[0].keyframes[1]
    assert kf2.source_detail == "detector_accepted"


def test_detect_path_write_anchored_sets_detector_anchored() -> None:
    """Marginal detection (ACCEPT_ANCHORED, gap=10+low_conf) sets detector_anchored."""
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # gap=10 soft-fail + confidence=0.30 soft-fail → ACCEPT_ANCHORED → WRITE_ANCHORED
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.30)],
        10, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    kf10 = tracks[0].keyframes[1]
    assert kf10.frame_index == 10
    assert kf10.source_detail == "detector_anchored"


# ---------------------------------------------------------------------------
# Legacy load: project without source_detail must still load cleanly
# ---------------------------------------------------------------------------

def test_legacy_project_loads_without_source_detail() -> None:
    """A project payload with no source_detail on any keyframe loads fine."""
    payload = {
        "project_id": "legacy-proj",
        "schema_version": 2,
        "version": "0.1.0",
        "name": "Legacy",
        "project_path": None,
        "video": None,
        "tracks": [
            {
                "track_id": "t1",
                "label": "T1",
                "state": "detected",
                "source": "detector",
                "visible": True,
                "keyframes": [
                    {
                        "frame_index": 0,
                        "shape_type": "ellipse",
                        "points": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
                        "bbox": [0.1, 0.1, 0.2, 0.2],
                        "confidence": 0.9,
                        "source": "detector",
                        # No source_detail — legacy file
                    },
                ],
                "segments": [],
            }
        ],
        "detector_config": {},
        "export_preset": {},
        "paths": {},
    }
    project = ProjectDocument.from_payload(payload)
    kf = project.tracks[0].keyframes[0]
    assert kf.source_detail is None  # silently normalized to None
