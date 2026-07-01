"""패널 스틸 생성의 캐릭터 일관성 검증.

배경: 예전엔 캐릭터 이미지를 subject_lock 컷에만 참조로 넣어, 제품 강조 컷(product_lock)의
인물이 캐릭터 레퍼런스 없이 생성돼 컷마다 다른 인종/얼굴로 드리프트했다(한 영상에 흑인·백인이
섞임). 이제 캐릭터를 모든 컷 참조에 넣고 '같은 사람 유지'를 프롬프트에 명시한다.
"""

from __future__ import annotations

from PIL import Image

from reel_gen_agent.generate.schema import (
    Objective,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
)
from reel_gen_agent.generate.stills import _panel_refs, ensure_panel_stills


def test_character_ref_included_on_product_lock_cut():
    panel = StoryboardPanel(index=0, product_lock=True, subject_lock=False)
    refs = _panel_refs(panel, "char.png", "prod.png", None)
    assert "char.png" in refs  # 제품 컷에도 캐릭터가 들어간다(인물 드리프트 방지)
    assert "prod.png" in refs


def test_character_ref_always_included():
    panel = StoryboardPanel(index=1, subject_lock=True, product_lock=False)
    assert _panel_refs(panel, "char.png", "prod.png", None) == ["char.png"]
    # 잠금이 하나도 없어도 캐릭터가 들어간다.
    bare = StoryboardPanel(index=2, subject_lock=False, product_lock=False)
    assert "char.png" in _panel_refs(bare, "char.png", None, None)


class _CapturingImageClient:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, refs, out, hero=False):
        self.calls.append({"prompt": prompt, "refs": list(refs), "out": out})
        Image.new("RGB", (10, 10), (0, 0, 0)).save(out)
        return out


def test_still_prompt_locks_character_and_passes_ref(tmp_path):
    char = tmp_path / "char.png"
    Image.new("RGB", (64, 64), (200, 180, 170)).save(char)
    profile = ReelProfile(
        objective=Objective(goal="g"),
        product=ProductSpec(name="P"),
        storyboard=Storyboard(
            panels=[StoryboardPanel(index=0, product_lock=True, subject_lock=False)]
        ),
    )
    client = _CapturingImageClient()
    filled = ensure_panel_stills(
        profile, str(tmp_path / "out"), client, str(char), None, anchor_indices={0}
    )
    assert filled == 1
    call = client.calls[0]
    assert str(char) in call["refs"]  # 캐릭터 참조가 제품 컷에도 들어간다
    assert "SAME individual" in call["prompt"]  # 같은 사람 유지 지시


def test_key_visual_used_as_identity_base(tmp_path):
    # i2v 세그먼트 간 인물 일관성: 모든 앵커 스틸이 key_visual(인물 대표 프레임)을 정체성 base로
    # 삼아 '같은 사람, 샷만 변형'으로 생성돼야 한다(veo i2v 포함).
    char = tmp_path / "char.png"
    Image.new("RGB", (64, 64), (200, 180, 170)).save(char)
    kv = tmp_path / "key_visual.png"
    Image.new("RGB", (64, 114), (210, 190, 180)).save(kv)
    profile = ReelProfile(
        objective=Objective(goal="g"),
        product=ProductSpec(name="P"),
        storyboard=Storyboard(panels=[StoryboardPanel(index=4, subject_lock=True)]),
    )
    client = _CapturingImageClient()
    ensure_panel_stills(
        profile, str(tmp_path / "out"), client, str(char), None,
        anchor_indices={4}, key_visual=str(kv),
    )
    call = client.calls[0]
    assert str(kv) in call["refs"]  # key_visual이 참조로 들어간다
    assert "identity and style base" in call["prompt"]  # 정체성 base로 사용
    assert "face must be clearly visible" in call["prompt"]  # 인물이 잘 드러나야 함
