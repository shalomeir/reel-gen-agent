# 제품 소스 보강 (product-source)

## 왜

제품 노드는 이 에이전트가 실제로 쓸 만한지를 가르는 핵심이다. 제품을 텍스트 이름만으로
짐작하면 카탈로그, 훅, 스토리보드가 모두 뭉개진다. 그래서 제품 URL 하나만 줘도 실제 판매
페이지를 근거로 정확한 제품 스펙과 참조 이미지를 뽑는다.

관련: [product-design.md](product-design.md) 입력 판별 규칙(제품 URL/이미지 분류),
[prd.md](prd.md) 제품 이해 요구.

## 인터페이스

모듈: `src/reel_gen_agent/generate/product_source.py`

- `collect_materials(url, out_dir) -> ProductMaterials | None`
  - Firecrawl로 판매 페이지를 스크래핑해 제목과 본문(설명, 특징)을 얻는다.
  - 본문에서 대상 제품 사진 URL만 추린다. 기준은 og:image의 이미지 코드다. 같은 코드를
    공유하는 URL만 남겨 아이콘, 배너, 추천 상품 사진을 걸러낸다. og가 없으면 비제품 자산
    (`/cms/`, `/icons/`, `.svg` 등)만 제외하고 앞쪽 몇 장을 쓴다.
  - 추린 사진을 최대 5장 내려받아 JPEG로 정규화 저장한다(백업 자료 겸 렌더 참조).
  - 스크래핑이 안 되면 `None`을 돌려준다(호출 측이 텍스트 경로로 폴백).
- `extract_product(materials, fallback_name) -> ProductSpec | None`
  - 내려받은 제품 사진 여러 장 + 본문 텍스트를 한 번의 멀티모달 호출(Gemini)로 분석해
    `ProductSpec`을 채운다. 이미지 분석과 문서 근거를 함께 대 정확도를 높인다.
  - 백엔드 자격이 없거나 호출이 실패하면 `None`(폴백 신호).

`ProductMaterials`: `title`, `web_context`(제목 + 본문 발췌), `image_paths`(내려받은 사진),
`source_url`.

## 제품 노드 배선 (plan_graph `_product_node`)

1. 입력에 제품 URL이 있으면 `collect_materials`로 근거를 모은다.
2. 참조 이미지 = 스크래핑한 실제 제품 사진 상위 2장 + 사용자가 직접 준 로컬 제품 이미지.
3. `extract_product`로 `ProductSpec`을 뽑는다. 실패하면 `derive_product`(텍스트)로 폴백하되,
   `web_context`가 있으면 그 근거를 함께 대 정확도를 지킨다.
4. `build_product_asset`에 참조 이미지를 넘겨 히어로와 패키지 컷을 실제 제품에 맞춰 렌더한다.

여기서 나온 `ProductSpec`(카테고리, 제형, 용기, 색, 식별 특징, USP, 가능 행동)은 히어로 이미지,
컷 스틸, 영상 프롬프트뿐 아니라 훅과 스토리보드 노드로도 흘러 컷마다 같은 제품을 고정하는
앵커가 된다.

## 원칙

- 브랜드명을 코드에 하드코딩하지 않는다. 어떤 URL이 들어오든 그 페이지를 읽을 뿐이다.
- 식별 특징(`key_features`)은 형태, 용기, 색, 재질 같은 물리적 단서만 담는다. 브랜드명,
  로고, 인쇄된 마케팅 문구는 담지 않는다(렌더에 가짜 브랜드 텍스트가 새는 것을 막는다).
- 정형 근거(스크래핑 본문, 다운로드 사진)와 지각 분석(VLM)을 함께 쓰되, 실패는 조용히
  비워 텍스트 경로로 폴백한다.

## 완료 기준

- 제품 URL만으로 실제 제품의 카테고리, 제형, 용기, 색, 특징, 구성이 반영된 `ProductSpec`이
  나온다.
- 판매 페이지에서 대상 제품 사진만 정확히 골라 내려받는다(아이콘, 배너, 다른 제품 제외).
- 스크래핑/분석 실패 시 텍스트 경로로 폴백해 파이프라인이 멈추지 않는다.
- 결정론 계층(URL 필터, 스펙 매핑, 자료 수집)은 외부 호출을 모킹한 테스트로 덮는다
  (`tests/test_product_source.py`).
