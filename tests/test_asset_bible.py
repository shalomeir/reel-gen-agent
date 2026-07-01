"""에셋 바이블 제품 에셋: 실제 제품 사진(refs)을 참조로 카탈로그 히어로·패키지 샷을 만든다.

현재 구현은 refs를 이미지 모델에 참조로 넘겨 렌더하며, 프롬프트에 원본 충실(_PRODUCT_FAITHFUL)과
패키지 잔글씨 처리(_PACKAGE_TEXT_RULE) 규칙을 실어 원제품을 최대한 보존한다.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from reel_gen_agent.generate.asset_bible import build_product_asset
from reel_gen_agent.generate.schema import ProductSpec


def _write_image(path: Path, size=(400, 700), color=(240, 200, 210)) -> str:
    Image.new("RGB", size, color).save(path)
    return str(path)


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, refs, out, hero=False):
        self.calls.append({"prompt": prompt, "refs": list(refs), "out": out})
        Image.new("RGB", (10, 10), (0, 0, 0)).save(out)
        return out


def test_generates_hero_and_packaging_with_reference(tmp_path):
    real = _write_image(tmp_path / "product_src_1.jpg")
    client = _RecordingClient()
    profile = build_product_asset(
        ProductSpec(name="Pore Perfecting Collagen Peptide Serum"), client, str(tmp_path), refs=[real]
    )
    assert profile.hero_image == "product.png"
    # 히어로 + 패키지 2회 생성, 원본 사진을 참조로 넘긴다.
    assert len(client.calls) == 2
    assert client.calls[0]["refs"] == [real]
    # 참조가 있으면 프롬프트가 원본 충실을 못 박는다(변형 방지).
    assert "Match the reference product image EXACTLY" in client.calls[0]["prompt"]


def test_no_client_yields_no_hero(tmp_path):
    real = _write_image(tmp_path / "product_src_1.jpg")
    profile = build_product_asset(ProductSpec(name="P"), None, str(tmp_path), refs=[real])
    assert profile.hero_image is None


def test_no_reference_prompt_has_no_faithful_clause(tmp_path):
    client = _RecordingClient()
    build_product_asset(ProductSpec(name="X", packaging_desc="clear bottle"), client, str(tmp_path), refs=[])
    # 참조가 없으면 원본 충실 클로즈를 넣지 않는다(참조가 없으니까).
    assert "Match the reference product image EXACTLY" not in client.calls[0]["prompt"]
