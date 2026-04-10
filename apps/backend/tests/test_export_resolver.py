"""
Tests for the export-side W7 resolver integration.

Verifies that export_project_video uses resolve_for_render (W7) to determine
the keyframe shape at each frame.

Unit tests (no video files):
  - exact keyframe → EXPLICIT
  - ellipse interpolation between two keyframes → INTERPOLATED
  - polygon between two keyframes → INTERPOLATED (polygon interpolation)
  - after last keyframe → None (export safety gate preserved)
  - before first keyframe → None

Integration test (real video file):
  - export with two spatially-separated ellipse keyframes: the mid-frame
    uses the INTERPOLATED position, not held-from-prior of the start position.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from auto_mosaic.domain.mask_continuity import ResolveReason, resolve_for_render
from auto_mosaic.domain.project import Keyframe, MaskSegment, MaskTrack, ProjectDocument
from auto_mosaic.infra.video.export import export_project_video


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_TEST_DIR = Path(tempfile.mkdtemp(prefix="taurimozaic-export-resolver-"))
_TEST_DIR.mkdir(parents=True, exist_ok=True)


def _make_video(path: Path, frame_count: int = 10, width: int = 160, height: int = 90) -> None:
    """Write a synthetic colored video for export integration tests."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (width, height))
    for fi in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                frame[y, x, 0] = (x * 3 + fi * 7) % 256
                frame[y, x, 1] = (y * 5 + fi * 11) % 256
                frame[y, x, 2] = ((x + y) * 2 + fi * 13) % 256
        writer.write(frame)
    writer.release()


def _kf(frame: int, shape_type: str, bbox: list[float]) -> Keyframe:
    x1, y1, w, h = bbox
    return Keyframe(
        frame_index=frame,
        shape_type=shape_type,
        points=[
            [x1,     y1    ],
            [x1 + w, y1    ],
            [x1 + w, y1 + h],
            [x1,     y1 + h],
        ],
        bbox=bbox,
        confidence=1.0,
        source="manual",
    )


def _track_with(*keyframes: Keyframe, segments: list[MaskSegment] | None = None) -> MaskTrack:
    t = MaskTrack(
        track_id="t1", label="T", state="active", source="manual", visible=True,
        keyframes=list(keyframes),
    )
    if segments is not None:
        t.segments = segments
    return t


def _minimal_project(source_path: Path, track: MaskTrack, frame_count: int = 10) -> ProjectDocument:
    return ProjectDocument.from_payload({
        "project_id": "export-resolver-test",
        "schema_version": 2,
        "version": "0.1.0",
        "name": "ExportResolverTest",
        "project_path": None,
        "video": {
            "source_path": str(source_path),
            "width": 160,
            "height": 90,
            "fps": 24.0,
            "frame_count": frame_count,
            "duration_sec": frame_count / 24.0,
            "readable": True,
            "warnings": [],
            "errors": [],
            "first_frame_shape": [90, 160, 3],
        },
        "tracks": [],  # replaced below
        "detector_config": {},
        "export_preset": {},
        "paths": {},
    })


# ---------------------------------------------------------------------------
# Unit tests: resolve_for_render behavior for export-relevant scenarios
# (no video file needed)
# ---------------------------------------------------------------------------

def test_resolver_explicit_keyframe() -> None:
    """Frame with an exact keyframe returns EXPLICIT."""
    kf0 = _kf(0, "ellipse", [0.1, 0.1, 0.2, 0.2])
    kf5 = _kf(5, "ellipse", [0.3, 0.1, 0.2, 0.2])
    track = _track_with(kf0, kf5)

    result = resolve_for_render(track, 5)
    assert result is not None
    keyframe, reason = result
    assert reason == ResolveReason.EXPLICIT
    assert keyframe.frame_index == 5
    assert abs(keyframe.bbox[0] - 0.3) < 1e-6


def test_resolver_interpolated_ellipse_between_keyframes() -> None:
    """Frame between two ellipse keyframes within gap ≤ 30 returns INTERPOLATED."""
    kf0 = _kf(0, "ellipse", [0.0, 0.1, 0.2, 0.7])
    kf8 = _kf(8, "ellipse", [0.6, 0.1, 0.2, 0.7])
    track = _track_with(kf0, kf8)

    result = resolve_for_render(track, 4)
    assert result is not None
    keyframe, reason = result
    assert reason == ResolveReason.INTERPOLATED
    # Interpolated x1 should be midpoint of 0.0 and 0.6 → 0.3
    assert abs(keyframe.bbox[0] - 0.3) < 1e-5


def test_resolver_interpolated_when_polygon() -> None:
    """Polygon keyframes within gap limit are interpolated (polygon interpolation)."""
    kf0 = _kf(0, "polygon", [0.1, 0.1, 0.2, 0.2])
    kf8 = _kf(8, "polygon", [0.5, 0.1, 0.2, 0.2])
    track = _track_with(kf0, kf8)

    result = resolve_for_render(track, 4)
    assert result is not None
    keyframe, reason = result
    assert reason == ResolveReason.INTERPOLATED
    # Midpoint x should be approximately (0.1 + 0.5) / 2 = 0.3
    assert abs(keyframe.bbox[0] - 0.3) < 0.05


def test_resolver_held_from_prior_when_gap_exceeds_limit() -> None:
    """Ellipse keyframes with gap > 30 frames fall back to HELD_FROM_PRIOR."""
    kf0 = _kf(0, "ellipse", [0.1, 0.1, 0.2, 0.2])
    kf35 = _kf(35, "ellipse", [0.5, 0.1, 0.2, 0.2])
    track = _track_with(kf0, kf35)

    result = resolve_for_render(track, 17)
    assert result is not None
    keyframe, reason = result
    assert reason == ResolveReason.HELD_FROM_PRIOR
    assert keyframe.frame_index == 0


def test_resolver_after_last_keyframe_returns_none() -> None:
    """Frame after the last keyframe is not renderable → None (export safety gate)."""
    kf0 = _kf(0, "ellipse", [0.1, 0.1, 0.2, 0.2])
    track = _track_with(kf0)  # no explicit segments → synthetic span [0, 0]

    result = resolve_for_render(track, 5)
    assert result is None


def test_resolver_before_first_keyframe_returns_none() -> None:
    """Frame before the first keyframe is not renderable → None."""
    kf5 = _kf(5, "ellipse", [0.1, 0.1, 0.2, 0.2])
    track = _track_with(kf5)

    result = resolve_for_render(track, 2)
    assert result is None


def test_resolver_explicit_segment_controls_renderable_span() -> None:
    """An explicit segment extending past the last keyframe gates correctly."""
    kf0 = _kf(0, "ellipse", [0.1, 0.1, 0.2, 0.2])
    seg = MaskSegment(start_frame=0, end_frame=7, state="confirmed")
    track = _track_with(kf0, segments=[seg])

    # Frame 7 is within the explicit segment → renderable, HELD_FROM_PRIOR.
    result = resolve_for_render(track, 7)
    assert result is not None
    keyframe, reason = result
    assert reason == ResolveReason.HELD_FROM_PRIOR
    assert keyframe.frame_index == 0

    # Frame 8 is outside the explicit segment → None.
    result8 = resolve_for_render(track, 8)
    assert result8 is None


# ---------------------------------------------------------------------------
# Integration test: export ACTUALLY uses interpolated shape at mid-frame
# ---------------------------------------------------------------------------

def test_export_uses_interpolated_ellipse_position_at_midframe() -> None:
    """
    Track: ellipse keyframes at frame 0 (left side) and frame 8 (right side).
    At frame 4 (midpoint), W7 returns the INTERPOLATED bbox (center position).
    The export output must show mosaic at the center — not at the left side.

    Geometry (160×90 video):
      kf0  bbox=[0.00, 0.1, 0.20, 0.7]  ellipse center ≈ (16, 40)  px-col  0-32
      kf8  bbox=[0.60, 0.1, 0.20, 0.7]  ellipse center ≈ (112, 40) px-col 96-128
      mid  bbox=[0.30, 0.1, 0.20, 0.7]  ellipse center ≈ (64, 40)  px-col 48-80
    """
    source_path = _TEST_DIR / "interp-source.mp4"
    output_path = _TEST_DIR / "interp-output.avi"
    _make_video(source_path, frame_count=10)

    kf0 = _kf(0, "ellipse", [0.00, 0.1, 0.20, 0.7])
    kf8 = _kf(8, "ellipse", [0.60, 0.1, 0.20, 0.7])
    track = MaskTrack(
        track_id="t1", label="T", state="active", source="manual", visible=True,
        keyframes=[kf0, kf8],
    )
    project = ProjectDocument.from_payload({
        "project_id": "interp-test",
        "schema_version": 2,
        "version": "0.1.0",
        "name": "InterpTest",
        "project_path": None,
        "video": {
            "source_path": str(source_path),
            "width": 160, "height": 90, "fps": 24.0,
            "frame_count": 10, "duration_sec": 10 / 24.0,
            "readable": True, "warnings": [], "errors": [],
            "first_frame_shape": [90, 160, 3],
        },
        "tracks": [],
        "detector_config": {}, "export_preset": {}, "paths": {},
    })
    project.tracks = [track]
    project.apply_domain_rules()

    response = export_project_video(
        project, str(output_path), mosaic_strength=12, audio_mode="video_only",
    )
    assert response["ok"] is True

    # Read frame 4 from both source and output.
    source_cap = cv2.VideoCapture(str(source_path))
    output_cap = cv2.VideoCapture(str(output_path))

    # Skip to frame 4.
    for _ in range(4):
        source_cap.read()
        output_cap.read()
    src_ok, src_frame = source_cap.read()
    out_ok, out_frame = output_cap.read()
    source_cap.release()
    output_cap.release()

    assert src_ok and out_ok

    def _diff(frame_s: np.ndarray, frame_o: np.ndarray, ys: int, ye: int, xs: int, xe: int) -> float:
        return float(np.mean(np.abs(
            frame_o[ys:ye, xs:xe].astype(np.int16) - frame_s[ys:ye, xs:xe].astype(np.int16)
        )))

    # kf0 region (x 0-32): should NOT be mosaicked at frame 4 (W7 interpolated away from it).
    left_diff = _diff(src_frame, out_frame, 25, 55, 4, 28)
    # Interpolated region (x 48-80): should BE mosaicked at frame 4.
    center_diff = _diff(src_frame, out_frame, 25, 55, 52, 76)
    # kf8 region (x 96-128): should NOT be mosaicked at frame 4.
    right_diff = _diff(src_frame, out_frame, 25, 55, 100, 124)

    assert center_diff > 5.0, (
        f"Expected mosaic at interpolated center (diff={center_diff:.2f} ≤ 5.0). "
        "W7 interpolation may not be used."
    )
    assert left_diff < 10.0, (
        f"Expected no mosaic at kf0 (left) position (diff={left_diff:.2f} > 10.0). "
        "W7 may be holding from prior instead of interpolating."
    )
    assert right_diff < 10.0, (
        f"Expected no mosaic at kf8 (right) position (diff={right_diff:.2f} > 10.0)."
    )


def test_export_polygon_uses_interpolation() -> None:
    """
    Polygon tracks interpolate between keyframes: the mid-frame must show
    mosaic at the interpolated position (center), not only at kf0 (left).

    Geometry (160×90):
      kf0 polygon bbox=[0.0, 0.1, 0.2, 0.7]  left region  (col 0-32)
      kf8 polygon bbox=[0.6, 0.1, 0.2, 0.7]  right region (col 96-128)
      frame 4 interpolated → center region mosaicked.
    """
    source_path = _TEST_DIR / "polygon-source.mp4"
    output_path = _TEST_DIR / "polygon-output.avi"
    _make_video(source_path, frame_count=10)

    kf0 = _kf(0, "polygon", [0.00, 0.1, 0.20, 0.7])
    kf8 = _kf(8, "polygon", [0.60, 0.1, 0.20, 0.7])
    track = MaskTrack(
        track_id="t1", label="T", state="active", source="manual", visible=True,
        keyframes=[kf0, kf8],
    )
    project = ProjectDocument.from_payload({
        "project_id": "polygon-test",
        "schema_version": 2,
        "version": "0.1.0",
        "name": "PolygonTest",
        "project_path": None,
        "video": {
            "source_path": str(source_path),
            "width": 160, "height": 90, "fps": 24.0,
            "frame_count": 10, "duration_sec": 10 / 24.0,
            "readable": True, "warnings": [], "errors": [],
            "first_frame_shape": [90, 160, 3],
        },
        "tracks": [],
        "detector_config": {}, "export_preset": {}, "paths": {},
    })
    project.tracks = [track]
    project.apply_domain_rules()

    response = export_project_video(
        project, str(output_path), mosaic_strength=12, audio_mode="video_only",
    )
    assert response["ok"] is True

    source_cap = cv2.VideoCapture(str(source_path))
    output_cap = cv2.VideoCapture(str(output_path))
    for _ in range(4):
        source_cap.read()
        output_cap.read()
    src_ok, src_frame = source_cap.read()
    out_ok, out_frame = output_cap.read()
    source_cap.release()
    output_cap.release()
    assert src_ok and out_ok

    def _diff(frame_s: np.ndarray, frame_o: np.ndarray, ys: int, ye: int, xs: int, xe: int) -> float:
        return float(np.mean(np.abs(
            frame_o[ys:ye, xs:xe].astype(np.int16) - frame_s[ys:ye, xs:xe].astype(np.int16)
        )))

    # Interpolated center: should be mosaicked (polygon interpolation at midpoint).
    center_diff = _diff(src_frame, out_frame, 25, 55, 52, 76)
    assert center_diff > 5.0, (
        f"Expected polygon interpolation mosaic at center (diff={center_diff:.2f} ≤ 5.0)."
    )


def test_export_after_last_keyframe_no_mosaic() -> None:
    """
    Frames after the last keyframe must not have mosaic applied (export safety gate).
    With a single-keyframe track (no explicit segments), only frame 0 is renderable.
    """
    source_path = _TEST_DIR / "after-last-source.mp4"
    output_path = _TEST_DIR / "after-last-output.avi"
    _make_video(source_path, frame_count=6)

    kf0 = _kf(0, "ellipse", [0.3, 0.2, 0.3, 0.5])
    track = MaskTrack(
        track_id="t1", label="T", state="active", source="manual", visible=True,
        keyframes=[kf0],
    )
    project = ProjectDocument.from_payload({
        "project_id": "after-last-test",
        "schema_version": 2,
        "version": "0.1.0",
        "name": "AfterLastTest",
        "project_path": None,
        "video": {
            "source_path": str(source_path),
            "width": 160, "height": 90, "fps": 24.0,
            "frame_count": 6, "duration_sec": 6 / 24.0,
            "readable": True, "warnings": [], "errors": [],
            "first_frame_shape": [90, 160, 3],
        },
        "tracks": [],
        "detector_config": {}, "export_preset": {}, "paths": {},
    })
    project.tracks = [track]
    project.apply_domain_rules()

    response = export_project_video(
        project, str(output_path), mosaic_strength=12, audio_mode="video_only",
    )
    assert response["ok"] is True

    source_cap = cv2.VideoCapture(str(source_path))
    output_cap = cv2.VideoCapture(str(output_path))
    frames: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(6):
        src_ok, src_f = source_cap.read()
        out_ok, out_f = output_cap.read()
        assert src_ok and out_ok
        frames.append((src_f, out_f))
    source_cap.release()
    output_cap.release()

    # Ellipse bbox=[0.3, 0.2, 0.3, 0.5] → pixel center ≈ (x=72, y=40)
    roi_ys, roi_ye, roi_xs, roi_xe = 25, 55, 57, 87

    def _diff(idx: int) -> float:
        sf, of = frames[idx]
        return float(np.mean(np.abs(
            of[roi_ys:roi_ye, roi_xs:roi_xe].astype(np.int16)
            - sf[roi_ys:roi_ye, roi_xs:roi_xe].astype(np.int16)
        )))

    # Frame 0: mosaic applied (keyframe exists at 0).
    assert _diff(0) > 5.0, "Frame 0 should have mosaic applied."
    # Frame 5: no mosaic (beyond last keyframe, not renderable).
    assert _diff(5) < 8.0, "Frame 5 should NOT have mosaic applied (after last keyframe)."
