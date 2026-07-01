"""유사도 비교와 페이싱 유도의 결정론 테스트."""

from __future__ import annotations

from reel_gen_agent.analysis.profile import Cut, Music, VideoProfile, Visual, Voice
from reel_gen_agent.analysis.similarity import compare_profiles
from reel_gen_agent.generate.pacing import edit_directive, storyboard_energy


def _profile(**kw) -> VideoProfile:
    return VideoProfile(**kw)


def test_identical_profiles_are_maximally_similar() -> None:
    p = _profile(
        cut=Cut(count=9, mean_sec=1.2, mode="fast_montage"),
        visual=Visual(motion="gentle", brightness=110.0, contrast=59.0, palette=["pink", "brown"]),
        voice=Voice(present=True, on_camera=False, tone="calm, soft", pace="slow"),
        music=Music(continuous=True, dynamics="flat", bpm=136.0),
        tone=["sensorial", "fresh"],
    )
    report = compare_profiles(p, p.model_copy(deep=True))
    assert report.passed
    assert report.overall >= 0.95


def test_rhythm_and_voice_drift_lowers_score_and_emits_feedback() -> None:
    ref = _profile(
        cut=Cut(count=9, mean_sec=1.2, mode="fast_montage"),
        voice=Voice(present=True, tone="whispered, soft", pace="slow"),
        music=Music(dynamics="flat", bpm=136.0, continuous=True),
    )
    gen = _profile(
        cut=Cut(count=5, mean_sec=2.4, mode="slow_demo"),
        voice=Voice(present=True, tone="enthusiastic", pace="fast"),
        music=Music(dynamics="flat", bpm=136.0, continuous=True),
    )
    report = compare_profiles(ref, gen)
    assert not report.passed
    keys = {ax.key: ax for ax in report.axes}
    assert keys["rhythm"].score < 0.6
    assert keys["voice"].score < 0.6
    assert keys["music"].score >= 0.95  # 음악은 일치 -> 높은 점수
    fb = report.feedback()
    assert "Cut rhythm" in fb and "Voice delivery" in fb


def test_pacing_directives_differ_by_mode() -> None:
    assert "hard" in edit_directive("fast_montage").lower()
    assert "gentle" in edit_directive("slow_demo").lower()
    assert "fast" in storyboard_energy("fast_montage").lower()
    assert "slow" in storyboard_energy("slow_demo").lower()
    # 미지정/기타는 균형(mixed)로 폴백한다.
    assert "varied" in edit_directive(None).lower()


def test_motion_directive_separates_from_pacing():
    from reel_gen_agent.generate.pacing import motion_directive
    # 샷 내부 모션은 컷 빈도와 별개 축: gentle이면 부드럽게(빠른 컷이어도).
    assert "gentle" in motion_directive("gentle").lower()
    assert "dynamic" in motion_directive("dynamic").lower()
    assert motion_directive(None) == ""


def test_veo_structural_fallback_keeps_scene_skeleton_generically():
    # LLM 없을 때 완화: 도메인 단어 블록리스트 없이 첫 줄 + 샷 목록만 남긴다(일반적).
    from reel_gen_agent.generate.backends.veo import _structural_fallback
    p = "\n".join([
        "A single vertical clip, varied pacing.",
        "Keep the person attractive and photogenic.",
        "Some other descriptive qualifier line.",
        "Shot 1: macro of the product, gentle spray.",
        "Shot 2: medium of the creator applying it.",
    ])
    out = _structural_fallback(p)
    assert out.startswith("A single vertical clip")
    assert "Shot 1" in out and "Shot 2" in out
    assert "photogenic" not in out and "qualifier" not in out


def test_veo_rewrite_prompt_uses_llm_when_available():
    # 원인이 '프롬프트'로 확인됐을 때만 쓰는 재작성: LLM으로 분석·재작성(케이스 특화 블록리스트 아님).
    from reel_gen_agent.generate.backends.veo import VeoBackend

    class _FakeTC:
        def __init__(self):
            self.calls = 0

        def complete(self, prompt: str, temperature: float = 0.3) -> str:
            self.calls += 1
            assert "content-safety filter" in prompt  # 재작성 지시가 전달됨
            return "REWRITTEN neutral prompt"

    tc = _FakeTC()
    b = VeoBackend(model="veo-3.1-fast-generate-001", text_client=tc)
    assert b._rewrite_prompt("original prompt") == "REWRITTEN neutral prompt"
    assert tc.calls == 1


def test_veo_rewrite_prompt_falls_back_without_llm():
    # LLM이 없으면 도메인 단어 블록리스트 없이 구조 기반으로 완화한다.
    from reel_gen_agent.generate.backends.veo import VeoBackend

    b = VeoBackend(model="veo-3.1-fast-generate-001", text_client=None)
    out = b._rewrite_prompt("A clip.\nsome flowery qualifier line.\nShot 1: product macro.")
    assert "Shot 1" in out and "qualifier" not in out
