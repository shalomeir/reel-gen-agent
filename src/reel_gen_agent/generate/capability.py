"""모델 능력 표(capability matrix). 코드에 모델을 박지 않고 데이터로 둔다."""

from __future__ import annotations

from .schema import ModelCapability

# 기본 표. 실제 운영 표는 .env/config로 주입·확장한다(모델 비종속).
_MATRIX: dict[str, ModelCapability] = {
    "ken_burns": ModelCapability(
        model_id="ken_burns", lane="local", multishot=True, integrated_voice=False
    ),
}


def capability_for(model_id: str) -> ModelCapability:
    mid = (model_id or "").lower()
    # Veo 3.1은 네이티브 오디오(발화 포함)를 낸다 -> 온카메라 발화가 가능하다.
    if mid.startswith("veo"):
        return ModelCapability(model_id=model_id, lane="vertex", integrated_voice=True)
    # fal 레인(Kling O3 / Seedance). 실제 id는 'fal-ai/kling-...' 또는 'bytedance/seedance-...'
    # 형태라 접두어가 아닌 부분일치로 잡는다. Kling은 네이티브 발화·립싱크가 가능하다. duration을
    # 3~15초 자유로 받으므로 세그먼트를 조금 더 길게 묶어 호출 수를 줄인다(max_clip_sec=10).
    if "kling" in mid or "seedance" in mid or mid.startswith(("fal-ai/", "fal:", "bytedance/")):
        return ModelCapability(
            model_id=model_id, lane="fal", integrated_voice="kling" in mid, max_clip_sec=10.0
        )
    return _MATRIX.get(model_id, ModelCapability(model_id=model_id, lane="vertex"))
