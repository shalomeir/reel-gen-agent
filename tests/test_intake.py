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


def test_bare_product_url_without_label_is_treated_as_product():
    # 라벨 없는 맨 제품 URL도 제품 판매 페이지로 잡아야 한다(spec 판별 규칙: 제품 URL→제품).
    url = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000229692&dispCatNo=1"
    r = intake(f"이 제품으로 데일리 샤워 루틴 숏폼 광고 {url}")
    assert r.product.present and r.product.source == url
    assert r.reference_ref is None  # 영상이 아니므로 레퍼런스로 잡히지 않는다


def test_bare_video_url_stays_reference_not_product():
    # 맨 영상 URL은 레퍼런스로만 잡히고 제품으로 넘어가지 않는다.
    r = intake("이 스타일로 만들어줘 https://cdn.example/clip.mp4")
    assert r.reference_ref == "https://cdn.example/clip.mp4"
    assert r.product.source is None
