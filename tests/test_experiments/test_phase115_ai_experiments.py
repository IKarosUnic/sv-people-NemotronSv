"""Pytest runner for Phase 1.15 AI Intelligence Layer experiments (EXP_115_A to EXP_115_X)."""

import pytest
from saltbor.simulation.experiments.phase115_ai_experiments import PHASE115_AI_EXPERIMENTS


@pytest.mark.parametrize("exp_id,exp_cls", list(PHASE115_AI_EXPERIMENTS.items()))
def test_phase115_ai_experiments(exp_id: str, exp_cls: type):
    """Execute each Phase 1.15 AI Intelligence experiment and assert success and verified hypotheses."""
    exp = exp_cls()
    result = exp.run()
    assert result.success is True, f"Experiment {exp_id} failed: {result.summary}"
    assert len(result.hypotheses) >= 1
    assert all(h["confirmed"] for h in result.hypotheses), f"Unconfirmed hypothesis in {exp_id}"
    assert result.duration_seconds >= 0.0
