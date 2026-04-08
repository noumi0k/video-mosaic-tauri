from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    name: str
    required: bool
    url: str | None
    description: str
    source_label: str
    note: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    # auto_fetch=True: included in the "不足モデルを取得" default fetch even
    # when the model is classified as optional.
    auto_fetch: bool = False
    # expected_size / expected_sha256: used by doctor to verify file integrity.
    # Leave None when the value is unknown; only set for stable, versioned assets.
    expected_size: int | None = None
    expected_sha256: str | None = None


# GitHub release asset downloads require Accept: application/octet-stream to
# bypass the HTML login-redirect that the browser_download_url now triggers.
_GH_ASSET_HEADERS: dict[str, str] = {
    "Accept": "application/octet-stream",
    "User-Agent": "auto-mosaic/1.0",
}

MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="320n.onnx",
        required=True,
        url="https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/176831997",
        description="NudeNet 320n (required default detector)",
        source_label="GitHub / notAI-tech/NudeNet",
        request_headers=_GH_ASSET_HEADERS,
        expected_size=12150158,
        expected_sha256="c15d8273adad2d0a92f014cc69ab2d6c311a06777a55545f2c4eb46f51911f0f",
    ),
    ModelSpec(
        name="640m.onnx",
        required=False,
        url="https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/176832019",
        description="NudeNet 640m (optional higher-accuracy detector)",
        source_label="GitHub / notAI-tech/NudeNet",
        request_headers=_GH_ASSET_HEADERS,
    ),
    ModelSpec(
        name="erax_nsfw_yolo11s.pt",
        required=False,
        url="https://huggingface.co/erax-ai/EraX-NSFW-V1.0/resolve/main/erax_nsfw_yolo11s.pt",
        description="EraX NSFW YOLO11s PyTorch checkpoint (optional alternative detector)",
        source_label="Hugging Face / erax-ai/EraX-NSFW-V1.0",
    ),
    ModelSpec(
        name="erax_nsfw_yolo11s.onnx",
        required=False,
        url=None,
        description="EraX NSFW YOLO11s ONNX export (derived from erax_nsfw_yolo11s.pt via setup-erax convert)",
        source_label="derived",
        note="Download erax_nsfw_yolo11s.pt first, then run setup-erax action='convert' to produce this file.",
    ),
    ModelSpec(
        name="sam2_tiny_encoder.onnx",
        required=False,
        url="https://huggingface.co/SharpAI/sam2-hiera-tiny-onnx/resolve/main/encoder.onnx",
        description="SAM2 tiny encoder (optional contour helper)",
        source_label="Hugging Face / SharpAI",
        auto_fetch=True,
    ),
    ModelSpec(
        name="sam2_tiny_decoder.onnx",
        required=False,
        url="https://huggingface.co/SharpAI/sam2-hiera-tiny-onnx/resolve/main/decoder.onnx",
        description="SAM2 tiny decoder (optional contour helper)",
        source_label="Hugging Face / SharpAI",
        auto_fetch=True,
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
