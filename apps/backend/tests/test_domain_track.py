"""Unit tests for MaskTrack domain rules — track lifetime and shape resolution."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from auto_mosaic.domain.project import Keyframe, MaskSegment, MaskTrack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kf(frame: int, source: str = "manual") -> Keyframe:
    return Keyframe(
        frame_index=frame,
        shape_type="polygon",
        points=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        bbox=[0.1, 0.1, 0.1, 0.1],
        confidence=1.0,
        source=source,
    )


def _track(*frames_and_sources, explicit_segments=None) -> MaskTrack:
    """Build a MaskTrack from (frame, source) pairs."""
    keyframes = [_kf(f, s) for f, s in frames_and_sources]
    track = MaskTrack(
        track_id="t1",
        label="Test",
        state="active",
        source="manual",
        keyframes=keyframes,
        segments=explicit_segments or [],
    )
    return track


# ---------------------------------------------------------------------------
# render_segments — span synthesis
# ---------------------------------------------------------------------------

class TestRenderSegments:
    def test_empty_track_returns_empty(self):
        track = _track()
        assert track.render_segments() == []

    def test_single_keyframe_is_single_frame_span(self):
        track = _track((10, "manual"))
        segs = track.render_segments()
        assert len(segs) == 1
        assert segs[0].start_frame == 10
        assert segs[0].end_frame == 10
        assert segs[0].state == "confirmed"

    def test_multi_keyframe_synthesises_single_span(self):
        track = _track((10, "manual"), (20, "manual"), (30, "manual"))
        segs = track.render_segments()
        assert len(segs) == 1
        assert segs[0].start_frame == 10
        assert segs[0].end_frame == 30

    def test_auto_only_keyframes_state_is_detected(self):
        track = _track((5, "detector"), (15, "detector"))
        segs = track.render_segments()
        assert segs[0].state == "detected"

    def test_mixed_sources_state_is_confirmed(self):
        track = _track((5, "detector"), (15, "manual"))
        segs = track.render_segments()
        assert segs[0].state == "confirmed"

    def test_explicit_segments_take_precedence(self):
        explicit = [MaskSegment(start_frame=0, end_frame=100, state="interpolated")]
        track = _track((10, "manual"), (50, "manual"), explicit_segments=explicit)
        segs = track.render_segments()
        assert len(segs) == 1
        assert segs[0].start_frame == 0
        assert segs[0].end_frame == 100
        assert segs[0].state == "interpolated"

    def test_held_segments_do_not_hide_detector_keyframe_span(self):
        track = MaskTrack(
            track_id="t1",
            label="detector",
            state="detected",
            source="detector",
            keyframes=[_kf(0, "detector"), _kf(6, "detector")],
            segments=[MaskSegment(start_frame=2, end_frame=4, state="held")],
        )

        segs = track.render_segments()

        assert any(seg.start_frame == 0 and seg.end_frame == 6 and seg.state == "detected" for seg in segs)
        assert track.frame_is_renderable(0)
        assert track.frame_is_renderable(3)
        assert track.frame_is_renderable(6)


# ---------------------------------------------------------------------------
# frame_is_renderable
# ---------------------------------------------------------------------------

class TestFrameIsRenderable:
    def test_empty_track_never_renderable(self):
        track = _track()
        assert not track.frame_is_renderable(0)
        assert not track.frame_is_renderable(50)

    def test_before_first_keyframe_not_renderable(self):
        track = _track((10, "manual"), (20, "manual"))
        assert not track.frame_is_renderable(9)

    def test_first_keyframe_frame_is_renderable(self):
        track = _track((10, "manual"), (20, "manual"))
        assert track.frame_is_renderable(10)

    def test_between_keyframes_is_renderable(self):
        # Previously this returned False (per-point segments); now the span covers it.
        track = _track((10, "manual"), (20, "manual"))
        assert track.frame_is_renderable(15)

    def test_last_keyframe_frame_is_renderable(self):
        track = _track((10, "manual"), (20, "manual"))
        assert track.frame_is_renderable(20)

    def test_beyond_last_keyframe_not_renderable(self):
        # Export pipeline must NOT apply mosaic beyond the last keyframe unless
        # explicit segments extend further.
        track = _track((10, "manual"), (20, "manual"))
        assert not track.frame_is_renderable(21)
        assert not track.frame_is_renderable(100)


# ---------------------------------------------------------------------------
# resolve_active_keyframe (export-facing, stays gated by renderable span)
# ---------------------------------------------------------------------------

class TestResolveActiveKeyframe:
    def test_empty_track_returns_none(self):
        track = _track()
        assert track.resolve_active_keyframe(5) is None

    def test_before_span_returns_none(self):
        track = _track((10, "manual"), (20, "manual"))
        assert track.resolve_active_keyframe(9) is None

    def test_at_first_keyframe_returns_it(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_active_keyframe(10)
        assert kf is not None
        assert kf.frame_index == 10

    def test_between_keyframes_returns_most_recent(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_active_keyframe(15)
        assert kf is not None
        assert kf.frame_index == 10

    def test_at_last_keyframe_returns_it(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_active_keyframe(20)
        assert kf is not None
        assert kf.frame_index == 20

    def test_beyond_last_keyframe_returns_none(self):
        # Export gate: no keyframe resolved beyond the span.
        track = _track((10, "manual"), (20, "manual"))
        assert track.resolve_active_keyframe(21) is None
        assert track.resolve_active_keyframe(100) is None


# ---------------------------------------------------------------------------
# resolve_shape_for_editing (editing-facing, NOT gated by renderable span)
# ---------------------------------------------------------------------------

class TestResolveShapeForEditing:
    def test_empty_track_returns_none(self):
        track = _track()
        assert track.resolve_shape_for_editing(5) is None

    def test_before_first_keyframe_returns_none(self):
        track = _track((10, "manual"))
        assert track.resolve_shape_for_editing(9) is None

    def test_at_first_keyframe_returns_it(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_shape_for_editing(10)
        assert kf is not None
        assert kf.frame_index == 10

    def test_between_keyframes_returns_most_recent(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_shape_for_editing(15)
        assert kf is not None
        assert kf.frame_index == 10

    def test_at_last_keyframe_returns_it(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_shape_for_editing(20)
        assert kf is not None
        assert kf.frame_index == 20

    def test_beyond_last_keyframe_returns_last_kf(self):
        # Core fix: held editing beyond detection span.
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_shape_for_editing(21)
        assert kf is not None
        assert kf.frame_index == 20

    def test_far_beyond_last_keyframe_returns_last_kf(self):
        track = _track((10, "manual"), (20, "manual"))
        kf = track.resolve_shape_for_editing(500)
        assert kf is not None
        assert kf.frame_index == 20

    def test_detector_source_track_held_beyond_span(self):
        track = _track((5, "detector"), (15, "detector"))
        kf = track.resolve_shape_for_editing(100)
        assert kf is not None
        assert kf.frame_index == 15

    def test_single_keyframe_held_indefinitely(self):
        track = _track((0, "manual"))
        kf = track.resolve_shape_for_editing(999)
        assert kf is not None
        assert kf.frame_index == 0


# ---------------------------------------------------------------------------
# Invariant: resolve_active_keyframe and resolve_shape_for_editing agree
# within the renderable span
# ---------------------------------------------------------------------------

class TestResolutionConsistency:
    def test_within_span_both_methods_agree(self):
        track = _track((10, "manual"), (20, "manual"), (30, "manual"))
        for frame in [10, 12, 15, 20, 25, 30]:
            active = track.resolve_active_keyframe(frame)
            editing = track.resolve_shape_for_editing(frame)
            assert active is not None, f"frame {frame}: resolve_active_keyframe returned None"
            assert editing is not None, f"frame {frame}: resolve_shape_for_editing returned None"
            assert active.frame_index == editing.frame_index, (
                f"frame {frame}: methods disagree — "
                f"active={active.frame_index} editing={editing.frame_index}"
            )

    def test_beyond_span_methods_diverge(self):
        track = _track((10, "manual"), (20, "manual"))
        # resolve_active_keyframe gates export — must return None after span
        assert track.resolve_active_keyframe(21) is None
        # resolve_shape_for_editing enables editing — must return last kf
        kf = track.resolve_shape_for_editing(21)
        assert kf is not None
        assert kf.frame_index == 20


# ---------------------------------------------------------------------------
# export_enabled flag — independent from visible, default True for legacy data
# ---------------------------------------------------------------------------

class TestExportEnabledFlag:
    def _base_payload(self) -> dict:
        return {
            "track_id": "t1",
            "label": "Test",
            "state": "active",
            "source": "manual",
            "keyframes": [
                {
                    "frame_index": 0,
                    "shape_type": "polygon",
                    "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                    "bbox": [0.1, 0.1, 0.1, 0.1],
                    "confidence": 1.0,
                    "source": "manual",
                }
            ],
        }

    def test_default_is_true_for_fresh_track(self):
        track = MaskTrack(track_id="t1", label="Test", state="active", source="manual")
        assert track.export_enabled is True

    def test_legacy_payload_without_flag_defaults_to_true(self):
        track = MaskTrack.from_payload(self._base_payload())
        assert track.export_enabled is True

    def test_payload_false_is_preserved(self):
        payload = self._base_payload()
        payload["export_enabled"] = False
        track = MaskTrack.from_payload(payload)
        assert track.export_enabled is False

    def test_export_enabled_roundtrips_through_asdict(self):
        track = MaskTrack(
            track_id="t1",
            label="Test",
            state="active",
            source="manual",
            export_enabled=False,
        )
        data = asdict(track)
        assert data["export_enabled"] is False
        restored = MaskTrack.from_payload(data)
        assert restored.export_enabled is False

    def test_export_enabled_is_independent_from_visible(self):
        track = MaskTrack(
            track_id="t1",
            label="Test",
            state="active",
            source="manual",
            visible=True,
            export_enabled=False,
        )
        assert track.visible is True
        assert track.export_enabled is False
