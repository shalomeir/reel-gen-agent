from reel_gen_agent.generate.intake import generation_input_to_brief, intake
from reel_gen_agent.generate.schema import (
    GenerationInput,
    InputMeta,
    ModelSpec,
    ProductSpec,
    StyleSpec,
)


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


def test_bare_youtube_url_stays_reference_not_product():
    url = "https://www.youtube.com/shorts/abc123"
    r = intake(f"이런 느낌의 15초 미스트 광고로 만들어줘 {url}")
    assert r.reference_ref == url
    assert r.product.source is None


def test_generation_input_to_brief_preserves_structured_fields():
    gen_input = GenerationInput(
        objective="수분 미스트를 아침 루틴 광고로 소개",
        meta=InputMeta(language="ko"),
        product=ProductSpec(
            name="BIODANCE mist",
            url="https://example.com/product",
            usp="건조한 피부에 빠른 수분감",
        ),
        model=ModelSpec(gender="female", look="clean beauty creator"),
        style=StyleSpec(tone=["fresh", "calm"], pacing="mixed"),
        style_prompt="밝고 산뜻한 K-beauty 톤",
    )

    brief = generation_input_to_brief(gen_input)
    result = intake(brief)

    assert "수분 미스트를 아침 루틴 광고로 소개" in brief
    assert result.product.source.startswith("BIODANCE mist")
    assert result.product_url == "https://example.com/product"
    assert result.character.source.startswith("female")
    assert "clean beauty creator" in result.character.source
    assert result.language == "ko"


def test_generation_input_prompt_behaves_like_freeform_run_brief():
    url = "https://www.youtube.com/shorts/abc123"
    gen_input = GenerationInput(
        prompt=f"이런 영상이었으면 좋겠어요. 밝은 욕실 루틴 톤으로 만들고 레퍼런스는 {url}",
        objective="BIODANCE 미스트 15초 광고",
        product=ProductSpec(name="BIODANCE mist"),
    )

    brief = generation_input_to_brief(gen_input)
    result = intake(brief)

    assert brief.startswith("이런 영상이었으면 좋겠어요.")
    assert "밝은 욕실 루틴 톤" in result.objective.goal
    assert result.reference_ref == url
    assert result.product.source.startswith("BIODANCE mist")


def test_generation_input_prompt_detects_model_product_and_reference_assets(tmp_path):
    model_image = tmp_path / "model.png"
    product_image = tmp_path / "mist.png"
    model_image.write_bytes(b"png")
    product_image.write_bytes(b"png")
    product_url = "https://shop.example/products/mist"
    reference_url = "https://www.youtube.com/shorts/abc123"
    gen_input = GenerationInput(
        prompt=(
            f"이런 영상이면 좋겠어요 {reference_url}\n"
            f"모델 이미지는 {model_image} 참고하고\n"
            f"제품 이미지는 {product_image} 쓰고 제품 url은 {product_url}"
        ),
        objective="BIODANCE 미스트 15초 광고",
        product=ProductSpec(name="BIODANCE mist"),
    )

    result = intake(generation_input_to_brief(gen_input))

    assert result.reference_ref == reference_url
    assert result.character_image == str(model_image.resolve())
    assert result.product_image == str(product_image.resolve())
    assert result.product_url == product_url


def test_generation_input_product_path_becomes_product_image(tmp_path):
    product_image = tmp_path / "demo" / "sample_imgs" / "mist.png"
    product_image.parent.mkdir(parents=True)
    product_image.write_bytes(b"png")
    gen_input = GenerationInput(
        objective="수분 미스트 아침 루틴 광고",
        product=ProductSpec(
            name="BIODANCE mist",
            path="./sample_imgs/mist.png",
            usp="빠른 수분감",
        ),
    )

    brief = generation_input_to_brief(gen_input, base_dir=tmp_path / "demo")
    result = intake(brief)

    assert result.product.source.startswith("BIODANCE mist")
    assert result.product_image == str(product_image.resolve())


def test_generation_input_model_path_becomes_character_image(tmp_path):
    model_image = tmp_path / "demo" / "sample_imgs" / "model.png"
    model_image.parent.mkdir(parents=True)
    model_image.write_bytes(b"png")
    gen_input = GenerationInput(
        objective="수분 미스트 아침 루틴 광고",
        product=ProductSpec(name="BIODANCE mist"),
        model=ModelSpec(path="./sample_imgs/model.png", look="clean beauty creator"),
    )

    brief = generation_input_to_brief(gen_input, base_dir=tmp_path / "demo")
    result = intake(brief)

    assert result.character.source.startswith("clean beauty creator")
    assert result.character_image == str(model_image.resolve())
