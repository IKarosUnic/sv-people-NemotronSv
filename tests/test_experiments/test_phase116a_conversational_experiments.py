"""Pytest runner for Phase 1.16A Conversational Studio experiments (EXP_116A_01 to EXP_116A_12)."""

from __future__ import annotations

import pytest

from saltbor.simulation.experiments.phase116a_conversational_experiments import PHASE116A_EXPERIMENTS


@pytest.mark.parametrize("exp_id,exp_cls", list(PHASE116A_EXPERIMENTS.items()))
def test_phase116a_conversational_experiments(exp_id: str, exp_cls: type):
    """Execute each Phase 1.16A experiment and assert all scientific hypotheses hold."""
    exp = exp_cls()
    result = exp.run()
    assert result.success is True, f"Experiment {exp_id} failed: {result.summary}"
    assert len(result.hypotheses) >= 2
    assert all(h["confirmed"] for h in result.hypotheses), f"Unconfirmed hypothesis in {exp_id}: {result.hypotheses}"
    assert result.duration_seconds >= 0.0
