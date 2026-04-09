from __future__ import annotations

from dataclasses import dataclass, field

# Valid first bytes for an ONNX ModelProto (protobuf field tags).
# Each tag encodes (field_number << 3) | wire_type.
# 0x3c ('<') is the HTML open-tag byte and is intentionally excluded.
# Assign this to ModelSpec.valid_magic_bytes for any .onnx model.
ONNX_MAGIC_BYTES: frozenset[int] = frozenset({
    0x08,  # field 1  ir_version       (varint)
    0x12,  # field 2  producer_name    (len)
    0x1a,  # field 3  producer_version (len)
    0x22,  # field 4  domain           (len)
    0x28,  # field 5  model_version    (varint)
    0x32,  # field 6  doc_string       (len)
    0x3a,  # field 7  graph            (len)
    0x42,  # field 8  opset_import     (len)
    0x4a,  # field 9  metadata_props   (len)
    0x72,  # field 14 ir_version_prerelease (len)
})


@dataclass(frozen=True)
class ModelSpec:
    name: str
    # Stable, human-readable identifier independent of the on-disk filename.
    # Never changes even if the file is renamed or the URL changes.
    model_id: str
    required: bool
    url: str | None
    description: str
    source_label: str
    # Resolver metadata — use one of:
    #   "github_release_asset"  GitHub Releases API (api.github.com/repos/…/assets/ID)
    #   "huggingface"           Hugging Face resolve URL
    #   "derived"               Produced locally from another model file
    #   "none"                  Not directly downloadable
    source_type: str
    note: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    # auto_fetch=True: included in the "不足モデルを取得" default fetch even
    # when the model is classified as optional.
    auto_fetch: bool = False
    # expected_size / expected_sha256: used to verify file integrity.
    # Leave None when the value is unknown; only set for stable, versioned assets.
    expected_size: int | None = None
    expected_sha256: str | None = None
    # valid_magic_bytes: frozenset of valid first byte values for this model type.
    #   - Set to ONNX_MAGIC_BYTES for .onnx models.
    #   - Set to None to skip the magic-byte check (e.g. PyTorch .pt files,
    #     or formats where the first byte set is large/undefined).
    valid_magic_bytes: frozenset[int] | None = None


# GitHub release asset downloads require Accept: application/octet-stream to
# bypass the HTML login-redirect that the browser_download_url now triggers.
# Always use api.github.com/repos/…/assets/<ID> — never browser_download_url.
_GH_ASSET_HEADERS: dict[str, str] = {
    "Accept": "application/octet-stream",
    "User-Agent": "auto-mosaic/1.0",
}

MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="320n.onnx",
        model_id="nudenet-320n",
        required=True,
        url="https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/176831997",
        description="NudeNet 320n (required default detector)",
        source_label="GitHub / notAI-tech/NudeNet",
        source_type="github_release_asset",
        request_headers=_GH_ASSET_HEADERS,
        expected_size=12150158,
        expected_sha256="c15d8273adad2d0a92f014cc69ab2d6c311a06777a55545f2c4eb46f51911f0f",
        valid_magic_bytes=ONNX_MAGIC_BYTES,
    ),
    ModelSpec(
        name="640m.onnx",
        model_id="nudenet-640m",
        required=False,
        url="https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/176832019",
        description="NudeNet 640m (optional higher-accuracy detector)",
        source_label="GitHub / notAI-tech/NudeNet",
        source_type="github_release_asset",
        request_headers=_GH_ASSET_HEADERS,
        # expected_size / expected_sha256 not yet confirmed for 640m; add when verified.
        valid_magic_bytes=ONNX_MAGIC_BYTES,
    ),
    ModelSpec(
        name="erax_nsfw_yolo11s.pt",
        model_id="erax-nsfw-pt",
        required=False,
        url="https://huggingface.co/erax-ai/EraX-NSFW-V1.0/resolve/main/erax_nsfw_yolo11s.pt",
        description="EraX NSFW YOLO11s PyTorch checkpoint (optional alternative detector)",
        source_label="Hugging Face / erax-ai/EraX-NSFW-V1.0",
        source_type="huggingface",
        # .pt files use pickle or ZIP format; magic bytes vary by torch version.
        # Leave valid_magic_bytes=None to skip the magic-byte check.
        valid_magic_bytes=None,
    ),
    ModelSpec(
        name="erax_nsfw_yolo11s.onnx",
        model_id="erax-nsfw-onnx",
        required=False,
        url=None,
        description="EraX NSFW YOLO11s ONNX export (derived from erax_nsfw_yolo11s.pt via setup-erax convert)",
        source_label="derived",
        source_type="derived",
        note="Download erax_nsfw_yolo11s.pt first, then run setup-erax action='convert' to produce this file.",
        valid_magic_bytes=ONNX_MAGIC_BYTES,
    ),
    ModelSpec(
        name="sam2_tiny_encoder.onnx",
        model_id="sam2-tiny-encoder",
        required=False,
        url="https://huggingface.co/SharpAI/sam2-hiera-tiny-onnx/resolve/main/encoder.onnx",
        description="SAM2 tiny encoder (optional contour helper)",
        source_label="Hugging Face / SharpAI",
        source_type="huggingface",
        auto_fetch=True,
        valid_magic_bytes=ONNX_MAGIC_BYTES,
    ),
    ModelSpec(
        name="sam2_tiny_decoder.onnx",
        model_id="sam2-tiny-decoder",
        required=False,
        url="https://huggingface.co/SharpAI/sam2-hiera-tiny-onnx/resolve/main/decoder.onnx",
        description="SAM2 tiny decoder (optional contour helper)",
        source_label="Hugging Face / SharpAI",
        source_type="huggingface",
        auto_fetch=True,
        valid_magic_bytes=ONNX_MAGIC_BYTES,
    ),
)


def get_model_specs() -> tuple[ModelSpec, ...]:
    return MODEL_SPECS


def get_model_spec_map() -> dict[str, ModelSpec]:
    return {spec.name: spec for spec in MODEL_SPECS}


def get_required_model_names() -> list[str]:
    return [spec.name for spec in MODEL_SPECS if spec.required]


def get_optional_model_names() -> list[str]:
    return [spec.name for spec in MODEL_SPECS if not spec.required]
