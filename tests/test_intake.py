from reel_gen_agent.generate.intake import intake


def test_text_brief_extracts_labeled_assets():
    r = intake("발랄한 15초 언박싱 릴. 제품: https://b/serum 레퍼런스 영상: ./ref.mp4")
    assert r.objective is not None
    assert r.product.present and r.product.source == "https://b/serum"
    assert r.reference_ref == "./ref.mp4"
    assert r.raw_brief is not None


def test_absent_product_is_flagged_not_filled():
    r = intake("브랜드 무드 영상, 제품 없이 분위기만")
    assert r.product.present is False
    assert r.product.absent_reason is None  # ask 단계가 채운다


def test_local_character_image_is_resolved(tmp_path):
    img = tmp_path / "model.png"
    img.write_bytes(b"png")
    r = intake(f"자기 방에서 세럼 써보는 릴 캐릭터: {img}")
    assert r.character_image == str(img.resolve())
    assert r.product_image is None


def test_url_product_is_not_treated_as_local_image():
    r = intake("언박싱 릴 제품: https://shop.example/p/1.png")
    # URL은 로컬 이미지가 아니므로 product_image는 비고, source에는 URL이 남는다.
    assert r.product_image is None
    assert r.product.source == "https://shop.example/p/1.png"
