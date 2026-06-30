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
    return _MATRIX.get(model_id, ModelCapability(model_id=model_id, lane="vertex"))
