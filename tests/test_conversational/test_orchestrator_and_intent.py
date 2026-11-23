"""Tests for Spanish natural-language intent extraction, continuity, and Two-Stage workflow."""

from __future__ import annotations

import pytest

from saltbor.conversational import (
    AnalysisStage,
    ConversationIntent,
    InterventionCategory,
    PreliminaryAssessment,
    SALTBORConversationalOrchestrator,
    SimulationStudioResult,
)


@pytest.fixture()
def orchestrator(tmp_path):
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "conv_test.db", seed=42)
    try:
        yield orch
    finally:
        orch.close()


def test_spanish_intent_and_entity_extraction_examples(orchestrator):
    cases = [
        ("Quiero abrir una pupusería en Santa Tecla.", ConversationIntent.BUSINESS_PLACEMENT, InterventionCategory.PUPUSERIA, "Santa Tecla"),
        ("Analiza si hace falta una escuela en Cantón San José Las Flores.", ConversationIntent.EDUCATIONAL_INFRASTRUCTURE, InterventionCategory.SCHOOL, "San José Las Flores"),
        ("Quiero instalar una farmacia cerca de la Carretera Panamericana en Santa Tecla.", ConversationIntent.BUSINESS_PLACEMENT, InterventionCategory.PHARMACY, "Santa Tecla"),
        ("¿Qué ocurre si se interrumpe esta carretera en Soyapango durante 15 días?", ConversationIntent.TRANSPORT_INFRASTRUCTURE, InterventionCategory.ROAD, "Soyapango"),
        ("Compara construir una escuela con mejorar el transporte escolar en Ilobasco.", ConversationIntent.TERRITORIAL_COMPARISON, InterventionCategory.SCHOOL, "Ilobasco"),
    ]
    for prompt, expected_intent, expected_cat, expected_place in cases:
        res = orchestrator.handle_message(prompt)
        assert isinstance(res, PreliminaryAssessment)
        assert res.stage == AnalysisStage.STAGE_A_PRELIMINARY
        assert res.parsed_request.intent == expected_intent
        if expected_cat is not None:
            assert res.proposed_intervention is not None
            assert res.proposed_intervention.category == expected_cat
        assert res.territorial_context.resolved is True
        assert expected_place.lower() in (
            (res.territorial_context.district_name + " " + (res.territorial_context.canton_name or "")).lower()
        )


def test_all_14_intent_categories_covered(orchestrator):
    prompts = {
        ConversationIntent.BUSINESS_PLACEMENT: "Quiero abrir una tienda en Santa Ana",
        ConversationIntent.EDUCATIONAL_INFRASTRUCTURE: "Necesitamos una escuela en Chalatenango",
        ConversationIntent.HEALTH_INFRASTRUCTURE: "Instalar una clínica en San Vicente",
        ConversationIntent.TRANSPORT_INFRASTRUCTURE: "Mejorar el transporte de buses en Soyapango",
        ConversationIntent.PUBLIC_SERVICES: "Proyecto de agua potable en Sensuntepeque",
        ConversationIntent.AGRICULTURAL_INTERVENTION: "Apoyo para cosecha de maíz en Metapán",
        ConversationIntent.ENVIRONMENTAL_SCENARIO: "Riesgo de sequía en San Miguel",
        ConversationIntent.DEMOGRAPHIC_ANALYSIS: "Analiza la población y migración en Usulután",
        ConversationIntent.ECONOMIC_ANALYSIS: "Evalúa ingresos y empleo en Ahuachapán",
        ConversationIntent.SOCIAL_ANALYSIS: "Analiza cohesión social y ADESCO en Cojutepeque",
        ConversationIntent.TERRITORIAL_COMPARISON: "Compara soluciones educativas en Zacatecoluca",
        ConversationIntent.GENERAL_SCENARIO: "Evalúa este territorio en La Unión",
        ConversationIntent.INFORMATION_REQUEST: "¿Cómo funciona el modelo en Santa Tecla?",
    }
    observed = set()
    for expected, text in prompts.items():
        res = orchestrator.handle_message(text)
        observed.add(res.parsed_request.intent)
        assert res.parsed_request.intent == expected

    # Follow-up covers the 14th intent
    s = orchestrator.handle_message("Quiero poner una pupusería en Santa Tecla.")
    fu = orchestrator.handle_message("¿Y si contrato dos empleados más?", conversation_id=s.conversation_id)
    observed.add(fu.parsed_request.intent)
    assert fu.parsed_request.intent == ConversationIntent.FOLLOW_UP
    assert len(observed) == 14


def test_follow_up_conversation_continuity_preserves_location_and_business(orchestrator):
    turn1 = orchestrator.handle_message("Quiero poner una pupusería en Santa Tecla.")
    assert isinstance(turn1, PreliminaryAssessment)
    cid = turn1.conversation_id
    assert turn1.proposed_intervention is not None
    orig_staff = turn1.proposed_intervention.workforce_count
    orig_dist = turn1.territorial_context.district_id

    turn2 = orchestrator.handle_message("¿Y si contrato dos empleados más?", conversation_id=cid)
    assert isinstance(turn2, PreliminaryAssessment)
    assert turn2.conversation_id == cid
    assert turn2.parsed_request.is_follow_up is True
    assert turn2.territorial_context.district_id == orig_dist
    assert turn2.proposed_intervention is not None
    assert turn2.proposed_intervention.category == InterventionCategory.PUPUSERIA
    assert turn2.proposed_intervention.workforce_count == orig_staff + 2


def test_two_stage_workflow_and_headless_map_optional(orchestrator):
    # Stage A must NOT run full simulation automatically
    stage_a = orchestrator.handle_message("Quiero abrir una pupusería en Santa Tecla.", map_visible=False)
    assert isinstance(stage_a, PreliminaryAssessment)
    assert stage_a.ready_to_execute is True
    assert orchestrator.persistence.list_executions_for_conversation(stage_a.conversation_id) == []

    # Stage B executes real engines with map hidden
    stage_b = orchestrator.execute_stage_b(
        conversation_id=stage_a.conversation_id,
        scenario_id=stage_a.scenario_id,
        seed=42,
        map_visible=False,
    )
    assert isinstance(stage_b, SimulationStudioResult)
    assert stage_b.stage == AnalysisStage.STAGE_B_SIMULATED
    assert stage_b.map_visible is False
    assert "CommercialEngine" in stage_b.evidence.active_engines
    assert stage_b.evidence.ledger_audit["conservation_passed"] is True
    assert stage_b.evidence.ledger_audit["cash_conservation_diff_usd"] == 0.0
    assert len(orchestrator.persistence.list_executions_for_conversation(stage_a.conversation_id)) == 1
