"""Tests for model download specification hardening.

Covers:
  - HTML content rejected by _verify_downloaded_file
  - Size too small rejected
  - Invalid magic bytes rejected
  - SHA-256 mismatch rejected
  - Temp file is deleted and target never promoted when verification fails
  - Doctor: broken file -> status "broken", not "installed"
  - Detect guard: broken/missing model -> failure before spawning worker
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from auto_mosaic.api.commands import fetch_models, start_detect_job
from auto_mosaic.api.commands.doctor import _check_model_file
from auto_mosaic.api.commands.fetch_models import _verify_downloaded_file
from auto_mosaic.infra.ai.model_catalog import ONNX_MAGIC_BYTES, ModelSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_ROOT = Path(tempfile.gettempdir()) / "taurimozaic-test-model-integrity"


def _make_spec(
    name: str = "test.onnx",
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    valid_magic_bytes: frozenset[int] | None = ONNX_MAGIC_BYTES,
) -> ModelSpec:
    return ModelSpec(
        name=name,
        model_id="test-model",
        required=False,
        url=None,
        description="test",
        source_label="test",
        source_type="none",
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        valid_magic_bytes=valid_magic_bytes,
    )


def _valid_onnx_bytes(size: int = 2048) -> bytes:
    """Return bytes that look like a minimal valid ONNX file."""
    # 0x08 = ir_version field tag (varint) — a valid ONNX protobuf first byte.
    return bytes([0x08]) + b"\x00" * (size - 1)


def _td(name: str) -> Path:
    """Return a fresh, empty subdirectory under TEST_ROOT for a test."""
    d = TEST_ROOT / name
    if d.exists():
        for f in d.iterdir():
            f.unlink(missing_ok=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# _verify_downloaded_file: rejection tests
# ---------------------------------------------------------------------------

class TestVerifyDownloadedFile:
    def test_rejects_html_doctype(self):
        d = _td("vdf-html-doctype")
        f = d / "model.onnx"
        f.write_bytes(b"<!DOCTYPE html><html><body>login required</body></html>" + b" " * 2000)
        with pytest.raises(ValueError, match="HTML page"):
            _verify_downloaded_file(f, _make_spec())

    def test_rejects_html_tag(self):
        d = _td("vdf-html-tag")
        f = d / "model.onnx"
        f.write_bytes(b"<html><head></head><body>error</body></html>" + b" " * 2000)
        with pytest.raises(ValueError, match="HTML page"):
            _verify_downloaded_file(f, _make_spec())

    def test_rejects_whitespace_prefixed_html(self):
        """HTML detection must strip leading whitespace."""
        d = _td("vdf-html-ws")
        f = d / "model.onnx"
        f.write_bytes(b"  \r\n<!DOCTYPE html>" + b" " * 2000)
        with pytest.raises(ValueError, match="HTML page"):
            _verify_downloaded_file(f, _make_spec())

    def test_rejects_file_too_small(self):
        d = _td("vdf-too-small")
        f = d / "model.onnx"
        f.write_bytes(b"\x08" * 16)          # valid magic but tiny
        with pytest.raises(ValueError, match="too small"):
            _verify_downloaded_file(f, _make_spec())

    def test_rejects_invalid_magic_bytes(self):
        d = _td("vdf-bad-magic")
        f = d / "model.onnx"
        f.write_bytes(b"\xff" + b"\x00" * 2047)   # 0xff not in ONNX_MAGIC_BYTES
        with pytest.raises(ValueError, match="magic byte"):
            _verify_downloaded_file(f, _make_spec())

    def test_rejects_size_mismatch(self):
        d = _td("vdf-size-mismatch")
        f = d / "model.onnx"
        data = _valid_onnx_bytes(2048)
        f.write_bytes(data)
        spec = _make_spec(expected_size=9999)    # wrong expected size
        with pytest.raises(ValueError, match="size"):
            _verify_downloaded_file(f, spec)

    def test_rejects_sha256_mismatch(self):
        d = _td("vdf-hash-mismatch")
        f = d / "model.onnx"
        f.write_bytes(_valid_onnx_bytes(2048))
        spec = _make_spec(expected_sha256="0" * 64)   # deliberately wrong hash
        with pytest.raises(ValueError, match="SHA-256"):
            _verify_downloaded_file(f, spec)

    def test_accepts_valid_file_no_spec(self):
        d = _td("vdf-no-spec")
        f = d / "model.onnx"
        f.write_bytes(_valid_onnx_bytes(2048))
        _verify_downloaded_file(f, None)   # should not raise

    def test_accepts_valid_file_with_matching_hash(self):
        d = _td("vdf-match-hash")
        data = _valid_onnx_bytes(2048)
        f = d / "model.onnx"
        f.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        spec = _make_spec(expected_size=len(data), expected_sha256=sha)
        _verify_downloaded_file(f, spec)   # should not raise

    def test_skips_magic_check_when_valid_magic_bytes_is_none(self):
        """ModelSpec.valid_magic_bytes=None means 'skip magic check' (e.g. .pt files)."""
        d = _td("vdf-pt-skip-magic")
        f = d / "model.pt"
        # 0x80 is pickle magic — invalid for ONNX but valid for PyTorch.
        f.write_bytes(b"\x80\x02" + b"\x00" * 2046)
        spec = _make_spec(name="model.pt", valid_magic_bytes=None)
        _verify_downloaded_file(f, spec)   # should not raise


# ---------------------------------------------------------------------------
# Verify-then-promote atomicity
# ---------------------------------------------------------------------------

class TestVerifyThenPromoteAtomicity:
    def test_target_not_created_when_verification_fails(self, monkeypatch):
        """If the downloaded bytes fail verification, the target path must
        never be created — the broken temp file must be cleaned up instead."""
        d = _td("atomicity-fail")
        target = d / "model.onnx"
        html_payload = b"<!DOCTYPE html><html>error</html>" + b" " * 2000

        def fake_urlopen(req, timeout):
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.headers.get = lambda key, default="": (
                "text/plain" if key == "Content-Type" else default
            )
            call = {"n": 0}

            def _read(n):
                if call["n"] == 0:
                    call["n"] += 1
                    return html_payload
                return b""

            resp.read = _read
            return resp

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        with pytest.raises(ValueError, match="HTML page"):
            fetch_models._download_to_path(
                "https://example.com/model.onnx",
                target,
                spec=_make_spec(),
            )

        assert not target.exists(), "Target must not be created when verification fails"
        leftovers = list(d.glob("*.download"))
        assert leftovers == [], f"Temp files not cleaned up: {leftovers}"

    def test_target_created_only_after_verification_passes(self, monkeypatch):
        """Valid data -> temp verified -> promoted -> target exists."""
        d = _td("atomicity-pass")
        target = d / "model.onnx"
        valid_data = _valid_onnx_bytes(2048)

        call = {"n": 0}

        def fake_urlopen(req, timeout):
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.headers.get = lambda key, default="": (
                "application/octet-stream" if key == "Content-Type" else default
            )

            def _read(n):
                if call["n"] == 0:
                    call["n"] += 1
                    return valid_data
                return b""

            resp.read = _read
            return resp

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        bytes_written = fetch_models._download_to_path(
            "https://example.com/model.onnx",
            target,
            spec=_make_spec(),
        )
        assert target.exists()
        assert bytes_written == len(valid_data)


# ---------------------------------------------------------------------------
# Doctor: status-based checks
# ---------------------------------------------------------------------------

class TestDoctorCheckModelFile:
    def test_missing_file_returns_missing(self):
        path = TEST_ROOT / "doctor" / "nonexistent.onnx"
        assert _check_model_file(path) == "missing"

    def test_html_file_returns_broken(self):
        d = _td("doctor-html")
        path = d / "model.onnx"
        path.write_bytes(b"<!DOCTYPE html>" + b" " * 2048)
        assert _check_model_file(path) == "broken"

    def test_too_small_returns_broken(self):
        d = _td("doctor-small")
        path = d / "model.onnx"
        path.write_bytes(b"\x08" * 8)
        assert _check_model_file(path) == "broken"

    def test_wrong_magic_returns_broken(self):
        d = _td("doctor-magic")
        path = d / "model.onnx"
        path.write_bytes(b"\xff" + b"\x00" * 2047)
        assert _check_model_file(path) == "broken"

    def test_valid_onnx_no_spec_returns_installed(self):
        d = _td("doctor-valid")
        path = d / "model.onnx"
        path.write_bytes(_valid_onnx_bytes(2048))
        assert _check_model_file(path) == "installed"

    def test_broken_is_not_installed(self):
        """Regression: broken (HTML redirect save) must NOT be 'installed'."""
        d = _td("doctor-broken-not-installed")
        path = d / "model.onnx"
        path.write_bytes(b"<html><body>Forbidden</body></html>" + b" " * 2048)
        status = _check_model_file(path)
        assert status == "broken"
        assert status != "installed"

    def test_size_mismatch_returns_broken(self):
        d = _td("doctor-size")
        path = d / "model.onnx"
        data = _valid_onnx_bytes(2048)
        path.write_bytes(data)
        spec = _make_spec(expected_size=99999)
        assert _check_model_file(path, spec) == "broken"

    def test_sha256_mismatch_returns_broken(self):
        d = _td("doctor-sha256")
        path = d / "model.onnx"
        path.write_bytes(_valid_onnx_bytes(2048))
        spec = _make_spec(expected_sha256="a" * 64)
        assert _check_model_file(path, spec) == "broken"

    def test_correct_spec_returns_installed(self):
        d = _td("doctor-full-spec")
        data = _valid_onnx_bytes(2048)
        path = d / "model.onnx"
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        spec = _make_spec(expected_size=len(data), expected_sha256=sha)
        assert _check_model_file(path, spec) == "installed"

    def test_pt_file_with_none_magic_installed(self):
        """Files with valid_magic_bytes=None skip magic check."""
        d = _td("doctor-pt")
        path = d / "model.pt"
        path.write_bytes(b"\x80\x02" + b"\x00" * 2046)   # pickle magic
        spec = _make_spec(name="model.pt", valid_magic_bytes=None)
        assert _check_model_file(path, spec) == "installed"


# ---------------------------------------------------------------------------
# Detect guard: pre-flight check in start_detect_job
# ---------------------------------------------------------------------------

class TestDetectGuard:
    """start_detect_job.run() must fail BEFORE spawning a worker when the
    required model is missing or broken."""

    def _run(self, model_dir: Path, model_content: bytes | None,
             backend: str = "nudenet_320n", monkeypatch=None,
             extra_patches: dict | None = None) -> dict:
        model_file = model_dir / "320n.onnx"
        model_file.unlink(missing_ok=True)
        if model_content is not None:
            model_file.write_bytes(model_content)
        payload = {
            "paths": {"model_dir": str(model_dir)},
            "backend": backend,
            "project_path": "/fake/project.json",
        }
        return start_detect_job.run(payload)

    def test_missing_model_fails_before_spawn(self):
        """No model file -> failure with MODEL_MISSING, no worker spawned."""
        d = _td("guard-missing")
        result = self._run(d, model_content=None)
        assert result["ok"] is False
        assert result["error"]["code"] == "MODEL_MISSING"

    def test_broken_model_fails_before_spawn(self):
        """HTML-redirect save -> failure with MODEL_BROKEN, no worker spawned."""
        d = _td("guard-broken")
        html = b"<!DOCTYPE html><html><body>Login required</body></html>" + b" " * 2048
        result = self._run(d, model_content=html)
        assert result["ok"] is False
        assert result["error"]["code"] == "MODEL_BROKEN"

    def test_valid_model_proceeds_to_spawn(self, monkeypatch):
        """Valid model -> worker spawn attempted.

        The real 320n.onnx spec has expected_size=12150158 which a small test
        file will not match.  Patch get_model_spec_map to return a spec without
        size/hash constraints so the 2 KB fixture passes.
        """
        d = _td("guard-valid")
        valid = _valid_onnx_bytes(2048)

        fake_spec = _make_spec(name="320n.onnx", valid_magic_bytes=ONNX_MAGIC_BYTES)
        monkeypatch.setattr(
            "auto_mosaic.api.commands.start_detect_job.get_model_spec_map",
            lambda: {"320n.onnx": fake_spec},
        )

        def fake_spawn(job_id, payload):
            return 99999   # fake PID

        monkeypatch.setattr(
            "auto_mosaic.api.commands.start_detect_job._spawn_detect_worker",
            fake_spawn,
        )

        result = self._run(d, model_content=valid)
        assert result["ok"] is True
        assert "job_id" in result["data"]
