"""SALTBOR Conversational Orchestrator — Primary Natural-Language Studio Entry Point (Phase 1.16A).

Supports Spanish natural-language territorial problem formulation, two-stage
workflow (Stage A preliminary assessment vs Stage B real simulation execution),
multi-turn conversational continuity, Gemini/Ollama/Offline routing, selective
population activation, and optional map-coordinate input.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from saltbor.ai.budget import AIComputeBudgetManager
from saltbor.ai.privacy import AIPrivacyGuard
from saltbor.ai.providers.base import AIProviderType, AIRequest, AITaskCategory
from saltbor.ai.router import AIModelRouter

from saltbor.conversational.decision_analyst import GeminiDecisionAnalyst
from saltbor.conversational.evidence_engine import SyntheticPopulationEvidenceEngine
from saltbor.conversational.intervention_designer import TerritorialInterventionDesigner
from saltbor.conversational.persistence import ConversationalPersistenceStore
from saltbor.conversational.population_activation import (
    NationalPopulationActivationManager,
    TerritorialPopulationContextEngine,
)
from saltbor.conversational.scenario_comparison import TerritorialScenarioComparisonEngine
from saltbor.conversational.schemas import (
    ActivationLOD,
    AnalysisStage,
    ConversationIntent,
    ConversationSessionState,
    ConversationTurn,
    InterventionCategory,
    InterventionSpec,
    ParsedUserRequest,
    PreliminaryAssessment,
    SimulationStudioResult,
    TerritorialContext,
    TemporalHorizonSpec,
)
from saltbor.conversational.temporal_controller import ConversationalTemporalController
from saltbor.conversational.territorial_context import NationalTerritorialContextEngine

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class SALTBORConversationalOrchestrator:
    """Conversational territorial intelligence orchestrator bridging chat and SALTBOR engines."""

    def __init__(
        self,
        router: Optional[AIModelRouter] = None,
        budget_manager: Optional[AIComputeBudgetManager] = None,
        privacy_guard: Optional[AIPrivacyGuard] = None,
        territorial_engine: Optional[NationalTerritorialContextEngine] = None,
        population_manager: Optional[NationalPopulationActivationManager] = None,
        persistence_path: str | Path = "saltbor.db",
        seed: int = 42,
    ) -> None:
        self.seed = seed
        self.router = router or AIModelRouter()
        self.budget_manager = budget_manager or AIComputeBudgetManager()
        self.privacy_guard = privacy_guard or AIPrivacyGuard()

        self.territorial_engine = territorial_engine or NationalTerritorialContextEngine()
        self.population_manager = population_manager or NationalPopulationActivationManager(seed=seed)
        self.population_context_engine = TerritorialPopulationContextEngine()
        self.temporal_controller = ConversationalTemporalController()
        self.intervention_designer = TerritorialInterventionDesigner()
        self.evidence_engine = SyntheticPopulationEvidenceEngine()
        self.decision_analyst = GeminiDecisionAnalyst(
            router=self.router,
            budget_manager=self.budget_manager,
            privacy_guard=self.privacy_guard,
        )
        self.comparison_engine = TerritorialScenarioComparisonEngine(
            activation_manager=self.population_manager,
            intervention_designer=self.intervention_designer,
            temporal_controller=self.temporal_controller,
            evidence_engine=self.evidence_engine,
        )
        self.persistence = ConversationalPersistenceStore(db_path=persistence_path)

        # Phase 1.17 On-Demand National Territorial Intelligence Engine (shares territorial/population/AI engines)
        from saltbor.territorial_intelligence.on_demand_engine import OnDemandTerritorialSimulationEngine

        self.on_demand_engine = OnDemandTerritorialSimulationEngine(
            territorial_engine=self.territorial_engine,
            population_manager=self.population_manager,
            geography=self.territorial_engine.geography,
            router=self.router,
            budget_manager=self.budget_manager,
            privacy_guard=self.privacy_guard,
            seed=seed,
        )

        # In-memory cache of active conversations & background jobs
        self._sessions: Dict[str, ConversationSessionState] = {}
        self._pending_scenarios: Dict[str, Dict[str, Any]] = {}
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._job_cancels: Dict[str, threading.Event] = {}
        # Bounded cache of immutable static territorial/building/catchment/commerce intelligence per location
        self._ti_static_cache: Dict[Tuple[str, float, float, str], Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def close(self) -> None:
        """Close SQLite connections cleanly."""
        self.territorial_engine.close()
        self.persistence.close()

    def get_or_create_session(self, conversation_id: Optional[str] = None) -> ConversationSessionState:
        """Load an existing session from memory/SQLite or create a new one."""
        if conversation_id:
            if conversation_id in self._sessions:
                return self._sessions[conversation_id]
            loaded = self.persistence.load_session(conversation_id)
            if loaded is not None:
                self._sessions[conversation_id] = loaded
                return loaded

        cid = conversation_id or f"CONV_{uuid4().hex[:10]}"
        session = ConversationSessionState(
            conversation_id=cid,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._sessions[cid] = session
        self.persistence.save_session(session)
        return session

    def parse_user_request(
        self,
        message: str,
        session: ConversationSessionState,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> ParsedUserRequest:
        """Extract structured user intent, intervention, geography, and continuity flags."""
        norm = _norm(message)

        # 1. Detect follow-up continuity signals
        has_active = session.active_intervention is not None or session.active_location_query is not None
        follow_up_cues = (
            "y si ", "que pasa si", "y que pasa", "que pasaria si", "contrato", "empleados", "trabajadores",
            "bajo el precio", "subo el precio", "precio a", "horario", "solo por la tarde",
            "capacidad", "mejor ", "tambien ", "en vez de", "compara eso", "durante un ano",
            "y en ", "el de ", "ese negocio", "esa escuela", "esa farmacia",
            "ahora analiza", "flujo de personas", "flujo peatonal", "oportunidades de empleo",
            "que negocios", "establecimientos",
        )
        is_follow_up = bool(has_active and (any(c in norm for c in follow_up_cues) or norm.startswith(("¿y ", "y "))))

        follow_up_mods: Dict[str, Any] = {}
        if is_follow_up:
            m_add_emp = re.search(
                r"(?:contrato|agrego|sumo|anado|mas)\s+(\d+|un|uno|una|dos|tres|cuatro|cinco)\s+(?:empleados|trabajadores|docentes|personas)?",
                norm,
            )
            if not m_add_emp:
                m_add_emp = re.search(
                    r"(\d+|dos|tres|cuatro|cinco)\s+(?:empleados|trabajadores)\s+mas",
                    norm,
                )
            if m_add_emp:
                w_map = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}
                raw_w = m_add_emp.group(1)
                val = int(raw_w) if raw_w.isdigit() else w_map.get(raw_w, 1)
                if "mas" in norm or "contrato" in norm or "agrego" in norm or "sumo" in norm:
                    follow_up_mods["add_employees"] = val
                else:
                    follow_up_mods["set_employees"] = val

            m_price = re.search(r"\$\s*(\d+(?:\.\d+)?)", message)
            if m_price:
                follow_up_mods["set_price_usd"] = float(m_price.group(1))

        # 2. Extract geographic reference from Spanish text
        geo_ref = self._extract_geographic_reference(message)
        if not geo_ref and is_follow_up and session.active_location_query:
            geo_ref = session.active_location_query

        # Handle short disambiguation replies like "La Paz" or "El Rosario, La Paz"
        if (
            session.active_location_query
            and session.active_district_id is None
            and len(message.strip().split()) <= 5
            and session.active_intervention is not None
        ):
            is_follow_up = True
            combined = f"{session.active_location_query}, {message.strip()}"
            geo_ref = combined

        # 3. Intent & Intervention Type classification
        intent, interv_cat = self._classify_intent_and_intervention(norm, is_follow_up, session)

        # 4. Optional remote LLM enrichment via Flash-Lite (only when remote/local LLM is actually active)
        extraction_provider = AIProviderType.OFFLINE_DETERMINISTIC.value
        extraction_model = "deterministic-spanish-nlu"
        if self.router.allow_remote and self.router.gemini_provider.is_available():
            req = AIRequest(
                task_category=AITaskCategory.SCENARIO_EXTRACTION,
                prompt=(
                    f"Extrae intención, tipo de intervención y referencia geográfica del texto en español: '{message}'. "
                    "Devuelve JSON con keys: intent, geographic_reference, temporal_expression."
                ),
                structured_schema={},
                temperature=0.0,
                max_tokens=300,
            )
            resp = self.router.route_request(req)
            extraction_provider = resp.provider_type.value
            extraction_model = resp.model_name
            if resp.is_valid and isinstance(resp.structured_data, dict):
                llm_geo = resp.structured_data.get("geographic_reference")
                if isinstance(llm_geo, str) and llm_geo.strip() and not geo_ref:
                    geo_ref = llm_geo.strip()

        # 5. Required domains & missing info
        required_domains = self._infer_domains(intent, interv_cat)
        missing_info: List[str] = []
        if not geo_ref and (lat is None or lon is None):
            missing_info.append("Ubicación geográfica en El Salvador (departamento, distrito, cantón o coordenada).")

        depth = "comparative" if intent == ConversationIntent.TERRITORIAL_COMPARISON or "compara" in norm else "standard"
        if "detallado" in norm or "profundo" in norm or "un ano" in norm or "cinco anos" in norm:
            depth = "deep"

        return ParsedUserRequest(
            raw_message=message,
            intent=intent,
            intervention_type=interv_cat,
            geographic_reference=geo_ref,
            map_coordinates=(lat, lon) if (lat is not None and lon is not None) else session.active_coordinates,
            target_entities=[interv_cat.value] if interv_cat else [],
            temporal_expression=message,
            required_domains=required_domains,
            expected_outcomes=self._infer_expected_outcomes(intent),
            constraints=[],
            missing_information=missing_info,
            analysis_depth=depth,
            is_follow_up=is_follow_up,
            follow_up_modifications=follow_up_mods,
            referenced_scenario_id=session.active_scenario_id if is_follow_up else None,
            extraction_provider=extraction_provider,
            extraction_model=extraction_model,
        )

    def _extract_geographic_reference(self, message: str) -> Optional[str]:
        """Extract Spanish place phrase from natural text without hardcoding defaults."""
        # Check explicit prepositional phrases first ("en Santa Tecla", "cerca de ...", "en el cantón ...")
        patterns = [
            r"(?:en\s+el\s+|en\s+la\s+|en\s+|sobre\s+la\s+|sobre\s+el\s+)((?:[A-ZÁÉÍÓÚÑa-záéíóúñ0-9]+\s*){1,5}?)(?=\s+(?:durante|por|con|para|que|y|a\s+\$)|[?,.;!]|$)",
            r"(?:cerca\s+de\s+la\s+|cerca\s+del\s+|cerca\s+de\s+)((?:[A-ZÁÉÍÓÚÑa-záéíóúñ0-9]+\s*){1,5}?)(?=\s+(?:durante|por|con|para|que|y)|[?,.;!]|$)",
        ]
        generic_stops = {
            "esta comunidad", "este canton", "esta ubicacion", "este lugar",
            "esta zona", "la comunidad", "el canton", "un ano", "15 dias", "30 dias",
        }
        for pat in patterns:
            for m in re.finditer(pat, message, flags=re.IGNORECASE):
                cand = m.group(1).strip(" .,;?!¿¡")
                cand_norm = _norm(cand)
                if not cand or cand_norm in generic_stops:
                    continue
                if cand_norm.startswith(("un ", "una ", "dos ", "tres ", "15 ", "30 ", "los proximos")):
                    continue
                return cand

        # Direct lookup against known departments, districts, and cantones anywhere in message
        msg_norm = _norm(message)
        for d_name in self.territorial_engine._dept_by_norm:
            if len(d_name) >= 4 and re.search(rf"\b{re.escape(d_name)}\b", msg_norm):
                return d_name
        for dist_norm, d_list in self.territorial_engine._district_by_norm.items():
            if len(dist_norm) >= 4 and re.search(rf"\b{re.escape(dist_norm)}\b", msg_norm):
                return d_list[0].name
        for c_norm, c_list in self.territorial_engine._canton_by_norm.items():
            if len(c_norm) >= 5 and c_norm in msg_norm:
                return c_list[0][0]
        return None

    @staticmethod
    def _classify_intent_and_intervention(
        norm: str,
        is_follow_up: bool,
        session: ConversationSessionState,
    ) -> Tuple[ConversationIntent, Optional[InterventionCategory]]:
        if "compara" in norm or "comparar" in norm or "frente a" in norm:
            cat = session.active_intervention.category if session.active_intervention else (
                InterventionCategory.SCHOOL if "escuela" in norm else None
            )
            return ConversationIntent.TERRITORIAL_COMPARISON, cat

        if is_follow_up and session.active_intervention is not None:
            return ConversationIntent.FOLLOW_UP, session.active_intervention.category

        # Specific sector detections BEFORE generic action verbs ("abrir/poner/instalar una")
        if any(w in norm for w in ("escuela", "colegio", "educa", "desercion", "capacitacion", "escolar")):
            cat = InterventionCategory.TRAINING_CENTER if "capacitacion" in norm else InterventionCategory.SCHOOL
            return ConversationIntent.EDUCATIONAL_INFRASTRUCTURE, cat

        if any(w in norm for w in ("clinica", "hospital", "salud", "unidad de salud")):
            cat = InterventionCategory.HOSPITAL if "hospital" in norm else InterventionCategory.CLINIC
            return ConversationIntent.HEALTH_INFRASTRUCTURE, cat

        if any(w in norm for w in ("pupuser", "negocio", "tienda", "pulperia", "farmacia", "restaurante", "comedor", "mercado")):
            cat = TerritorialInterventionDesigner._infer_category_from_intent(
                ConversationIntent.BUSINESS_PLACEMENT, norm
            )
            return ConversationIntent.BUSINESS_PLACEMENT, cat

        if any(w in norm for w in ("carretera", "calle", "camino", "puente", "transporte", "bus", "interrumpe", "bloqueo")):
            cat = InterventionCategory.PUBLIC_TRANSPORT if "transporte" in norm or "bus" in norm else InterventionCategory.ROAD
            return ConversationIntent.TRANSPORT_INFRASTRUCTURE, cat

        if any(w in norm for w in ("agua potable", "electricidad", "luz electrica", "alcantarillado", "servicio publico")):
            cat = InterventionCategory.ELECTRICITY_INFRASTRUCTURE if "electric" in norm else InterventionCategory.WATER_INFRASTRUCTURE
            return ConversationIntent.PUBLIC_SERVICES, cat

        if any(w in norm for w in ("agricola", "cosecha", "maiz", "frijol", "cafe", "cultivo", "riego")):
            return ConversationIntent.AGRICULTURAL_INTERVENTION, InterventionCategory.AGRICULTURAL_BUSINESS

        if any(w in norm for w in ("deslave", "inundacion", "sequia", "clima", "epoca lluviosa", "ambiental", "reforest")):
            return ConversationIntent.ENVIRONMENTAL_SCENARIO, InterventionCategory.ENVIRONMENTAL_PROJECT

        if any(w in norm for w in ("abrir una", "poner una", "instalar una")):
            cat = TerritorialInterventionDesigner._infer_category_from_intent(
                ConversationIntent.BUSINESS_PLACEMENT, norm
            )
            return ConversationIntent.BUSINESS_PLACEMENT, cat

        if any(w in norm for w in ("poblacion", "demograf", "habitantes", "migracion", "commuter")):
            return ConversationIntent.DEMOGRAPHIC_ANALYSIS, None

        if any(w in norm for w in ("economia", "ingresos", "empleo", "pobreza", "fiado", "desigualdad", "gini")):
            return ConversationIntent.ECONOMIC_ANALYSIS, None

        if any(w in norm for w in ("social", "adesco", "comunidad", "cohesion", "cuchubal")):
            return ConversationIntent.SOCIAL_ANALYSIS, None

        if any(w in norm for w in ("que es", "como funciona", "explica", "ayuda", "cuales son")):
            return ConversationIntent.INFORMATION_REQUEST, None

        return ConversationIntent.GENERAL_SCENARIO, InterventionCategory.COMMERCIAL_ESTABLISHMENT

    @staticmethod
    def _infer_domains(intent: ConversationIntent, cat: Optional[InterventionCategory]) -> List[str]:
        base = ["demographics", "territory", "economy"]
        if intent in (ConversationIntent.BUSINESS_PLACEMENT, ConversationIntent.ECONOMIC_ANALYSIS):
            base.extend(["commerce", "labor_market"])
        if intent == ConversationIntent.EDUCATIONAL_INFRASTRUCTURE or cat == InterventionCategory.SCHOOL:
            base.extend(["education", "mobility"])
        if intent == ConversationIntent.HEALTH_INFRASTRUCTURE or cat in (InterventionCategory.CLINIC, InterventionCategory.HOSPITAL, InterventionCategory.PHARMACY):
            base.append("health")
        if intent == ConversationIntent.TRANSPORT_INFRASTRUCTURE:
            base.extend(["mobility", "commerce"])
        return list(dict.fromkeys(base))

    @staticmethod
    def _infer_expected_outcomes(intent: ConversationIntent) -> List[str]:
        mapping = {
            ConversationIntent.BUSINESS_PLACEMENT: ["demanda_estimada", "tasa_conversion", "ingresos", "rentabilidad_neta", "competencia"],
            ConversationIntent.EDUCATIONAL_INFRASTRUCTURE: ["cobertura_escolar", "riesgo_desercion", "distancia_traslado", "demanda_insatisfecha"],
            ConversationIntent.HEALTH_INFRASTRUCTURE: ["atencion_primaria", "tiempo_espera", "demanda_insatisfecha"],
            ConversationIntent.TRANSPORT_INFRASTRUCTURE: ["friccion_movilidad", "acceso_comercio_escuela", "impacto_precios"],
        }
        return mapping.get(intent, ["impacto_hogares", "servicios", "equilibrio_contable"])

    # =========================================================================
    # Stage A — Preliminary Conversational Assessment
    # =========================================================================

    def handle_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        map_visible: bool = False,
        auto_execute: bool = False,
        seed: Optional[int] = None,
        temporal_days_override: Optional[int] = None,
    ) -> PreliminaryAssessment | SimulationStudioResult:
        """Stage A entry point: understands intent, resolves territory & context without auto-running costly sims."""
        session = self.get_or_create_session(conversation_id)
        parsed = self.parse_user_request(message, session, lat=lat, lon=lon)

        # Resolve geography
        if lat is not None and lon is not None:
            use_lat, use_lon = lat, lon
        elif parsed.is_follow_up and session.active_coordinates and not parsed.geographic_reference:
            use_lat, use_lon = session.active_coordinates
        else:
            use_lat, use_lon = None, None

        geo_ctx = self.territorial_engine.resolve_location(
            query=parsed.geographic_reference,
            lat=use_lat,
            lon=use_lon,
        )
        if geo_ctx.resolved:
            geo_ctx.question_data_quality = self.territorial_engine.evaluate_question_data_quality(
                geo_ctx,
                question_type=parsed.intent.value,
            )

        # Resolve temporal horizon
        used_seed = seed if seed is not None else self.seed
        temporal = self.temporal_controller.parse_temporal_horizon(
            text=message if not parsed.is_follow_up or any(
                w in _norm(message) for w in ("dia", "semana", "mes", "ano", "lluviosa", "seca")
            ) else None,
            intent=parsed.intent,
            seed=used_seed,
            explicit_days=temporal_days_override,
        )
        if parsed.is_follow_up and session.active_temporal_horizon and temporal_days_override is None and not any(
            w in _norm(message) for w in ("dia", "semana", "mes", "ano", "lluviosa", "seca")
        ):
            temporal = session.active_temporal_horizon

        # Design or update intervention
        intervention: Optional[InterventionSpec] = None
        if parsed.intervention_type is not None or session.active_intervention is not None:
            intervention = self.intervention_designer.design_intervention(
                parsed=parsed,
                context=geo_ctx,
                temporal=temporal,
                existing_spec=session.active_intervention if parsed.is_follow_up else None,
            )

        scenario_id = f"SCEN_{uuid4().hex[:8]}"
        pop_ctx = (
            self.population_context_engine.build_population_context(geo_ctx)
            if geo_ctx.resolved
            else {"uncertainties": ["Ubicación pendiente de resolución o aclaración."]}
        )

        clarification_needed = False
        clarification_questions: List[str] = []
        if geo_ctx.is_ambiguous:
            clarification_needed = True
            cand_labels = [f"{c.matched_label} ({c.department_name})" for c in geo_ctx.candidates[:4]]
            clarification_questions.append(
                f"La ubicación '{parsed.geographic_reference}' aparece en varios lugares: {', '.join(cand_labels)}. ¿A cuál te refieres?"
            )
        elif not geo_ctx.resolved:
            clarification_needed = True
            clarification_questions.append(
                "Indica el departamento, municipio, distrito o cantón de El Salvador (o marca un punto en el mapa) para evaluar el territorio."
            )

        if temporal.requires_confirmation:
            clarification_questions.append(temporal.confirmation_reason or "Confirma si deseas ejecutar este horizonte largo.")

        # Update session state while preserving existing scenario context on ambiguity
        session.active_scenario_id = scenario_id
        if geo_ctx.resolved:
            session.active_district_id = geo_ctx.district_id
            session.active_location_query = geo_ctx.canton_name or geo_ctx.district_name
        elif parsed.geographic_reference and not session.active_location_query:
            session.active_location_query = parsed.geographic_reference
        if lat is not None and lon is not None:
            session.active_coordinates = (lat, lon)
        if intervention is not None:
            session.active_intervention = intervention
        session.active_temporal_horizon = temporal
        if scenario_id not in session.scenario_ids:
            session.scenario_ids.append(scenario_id)

        user_turn_idx = len(session.turns)
        user_turn = ConversationTurn(
            turn_index=user_turn_idx,
            role="user",
            message=message,
            timestamp=time.time(),
            stage=AnalysisStage.STAGE_A_PRELIMINARY,
            scenario_id=scenario_id,
            intent=parsed.intent.value,
        )
        session.turns.append(user_turn)
        self.persistence.save_session(session)
        self.persistence.append_turn(session.conversation_id, user_turn)

        required_engines = self._determine_required_engines(parsed.intent, intervention)
        comp_est = {
            "recommended_active_agents": 40,
            "lod_level": ActivationLOD.LOD_3_INDIVIDUAL_FULL.name,
            "resolution_mode": temporal.resolution_mode,
            "effective_engine_ticks": temporal.effective_engine_ticks,
            "estimated_runtime_seconds": temporal.estimated_runtime_seconds,
            "map_required": False,
        }

        if geo_ctx.resolved:
            q_conf = geo_ctx.question_data_quality.confidence_score if geo_ctx.question_data_quality else geo_ctx.data_quality_score
            reply = (
                f"Evaluación preliminar (Etapa A) lista para {geo_ctx.district_name}, {geo_ctx.department_name} "
                f"(población aprox. {geo_ctx.approx_population:,}, confianza para pregunta {q_conf:.2f}/1.0, base geográfica {geo_ctx.data_quality_score:.2f}/1.0). "
                f"Horizonte propuesto: {temporal.horizon_days} días ({temporal.resolution_mode}). "
                f"Cuando confirmes, ejecutaré la simulación con agentes sintéticos y motores reales de SALTBOR."
            )
        else:
            reply = clarification_questions[0]

        assistant_turn = ConversationTurn(
            turn_index=user_turn_idx + 1,
            role="assistant",
            message=reply,
            timestamp=time.time(),
            stage=AnalysisStage.STAGE_A_PRELIMINARY,
            scenario_id=scenario_id,
            intent=parsed.intent.value,
        )
        session.turns.append(assistant_turn)
        self.persistence.save_session(session)
        self.persistence.append_turn(session.conversation_id, assistant_turn)

        # Store pending scenario for Stage B approval
        with self._lock:
            self._pending_scenarios[scenario_id] = {
                "conversation_id": session.conversation_id,
                "parsed": parsed,
                "context": geo_ctx,
                "temporal": temporal,
                "intervention": intervention,
            }

        self.persistence.save_scenario_definition(
            scenario_id=scenario_id,
            conversation_id=session.conversation_id,
            district_id=geo_ctx.district_id,
            geo_context_summary={
                "district_id": geo_ctx.district_id,
                "district_name": geo_ctx.district_name,
                "department_name": geo_ctx.department_name,
                "data_quality_score": geo_ctx.data_quality_score,
            },
            temporal=temporal,
            intervention=intervention,
        )

        # Phase 1.17: Grounded territorial intelligence snapshot (observed only in Stage A, never fabricated outcomes)
        ti_snapshot: Dict[str, Any] = {}
        if geo_ctx.resolved:
            ti_snapshot = self._build_stage_a_intelligence_snapshot(
                geo_ctx=geo_ctx,
                message=message,
                intervention=intervention,
            )

        assessment = PreliminaryAssessment(
            conversation_id=session.conversation_id,
            scenario_id=scenario_id,
            parsed_request=parsed,
            territorial_context=geo_ctx,
            population_context=pop_ctx,
            proposed_intervention=intervention,
            temporal_horizon=temporal,
            required_engines=required_engines,
            missing_data=list(dict.fromkeys(parsed.missing_information + geo_ctx.missing_data)),
            clarification_needed=clarification_needed,
            clarification_questions=clarification_questions,
            computational_estimate=comp_est,
            capabilities_summary=[
                "Resolución territorial en 14 departamentos, 44 municipios, 262 distritos y 795,877 capas OSM con índice R-Tree.",
                "Comportamiento de compra con racionalidad limitada (sin conversión automática) y conservación contable $0.00.",
                "Inteligencia de edificaciones, comercio real vs no verificado, áreas de influencia adaptativas y flujos de movilidad.",
            ],
            limitations_summary=geo_ctx.uncertainties[:4] or [
                "Los resultados provienen de población sintética y están sujetos a la cobertura OSM/D.L. 762 local."
            ],
            territorial_intelligence=ti_snapshot,
            ready_to_execute=geo_ctx.resolved,
            assistant_reply=reply,
        )

        if auto_execute and geo_ctx.resolved:
            return self.execute_stage_b(
                conversation_id=session.conversation_id,
                scenario_id=scenario_id,
                seed=used_seed,
                compare_alternatives=(parsed.intent == ConversationIntent.TERRITORIAL_COMPARISON or bool(intervention and intervention.compare_alternatives)),
                map_visible=map_visible,
            )
        return assessment

    # =========================================================================
    # Stage B — Evidence-Driven Simulation Execution
    # =========================================================================

    def execute_stage_b(
        self,
        conversation_id: str,
        scenario_id: Optional[str] = None,
        seed: int = 42,
        compare_alternatives: bool = False,
        max_active_agents: int = 40,
        target_lod: ActivationLOD = ActivationLOD.LOD_3_INDIVIDUAL_FULL,
        map_visible: bool = False,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> SimulationStudioResult:
        """Execute Stage B simulation on real engines, collect evidence, and interpret with Gemini/Offline."""
        def _emit(code: str, label: str) -> None:
            if progress_callback is not None:
                try:
                    progress_callback(code, label)
                except Exception:
                    pass

        _emit("VALIDATING_SCENARIO", "Configurando simulación y validando escenario")
        session = self.get_or_create_session(conversation_id)
        sid = scenario_id or session.active_scenario_id
        pending = self._pending_scenarios.get(sid or "")

        _emit("RESOLVING_LOCATION", "Resolviendo ubicación y contexto territorial")
        if pending is None:
            # Reconstruct cleanly from persisted session state
            geo_ctx = self.territorial_engine.resolve_location(
                query=session.active_location_query,
                lat=session.active_coordinates[0] if session.active_coordinates else None,
                lon=session.active_coordinates[1] if session.active_coordinates else None,
            )
            temporal = session.active_temporal_horizon or self.temporal_controller.parse_temporal_horizon(None, seed=seed)
            intervention = session.active_intervention or InterventionSpec(
                intervention_id=f"INT_GEN_{uuid4().hex[:6]}",
                category=InterventionCategory.COMMERCIAL_ESTABLISHMENT,
                name=f"Escenario en {geo_ctx.district_name or 'El Salvador'}",
                district_id=geo_ctx.district_id,
                duration_days=temporal.horizon_days,
            )
            sid = sid or f"SCEN_{uuid4().hex[:8]}"
        else:
            geo_ctx = pending["context"]
            temporal = pending["temporal"].model_copy(update={"seed": seed})
            intervention = pending["intervention"] or InterventionSpec(
                intervention_id=f"INT_GEN_{uuid4().hex[:6]}",
                category=InterventionCategory.COMMERCIAL_ESTABLISHMENT,
                name=f"Escenario en {geo_ctx.district_name or 'El Salvador'}",
                district_id=geo_ctx.district_id,
                duration_days=temporal.horizon_days,
            )

        # Enforce hard resource budget cap
        safe_agent_cap = max(8, min(250, int(max_active_agents)))

        _emit("PREPARING_POPULATION", "Preparando e hidratando población sintética")
        if geo_ctx.resolved:
            self.population_manager.activate_region(
                context=geo_ctx,
                target_lod=target_lod,
                max_active_agents=safe_agent_cap,
                seed=seed,
            )
            # Snapshot AFTER regional activation so cohort registries stay intact on restore
            baseline_snap = self.population_manager.capture_baseline_snapshot()
            humans = self.population_manager.get_active_humans_for_district(geo_ctx.district_id)
            pop_acc = self.population_manager.get_district_population_accounting(geo_ctx.district_id)
        else:
            baseline_snap = self.population_manager.capture_baseline_snapshot()
            humans = []
            pop_acc = {"district_id": "UNKNOWN", "unique_individuals_present": 0}

        _emit("RUNNING_SIMULATION", "Ejecutando simulación en motores reales de SALTBOR")
        if humans and geo_ctx.resolved:
            sim_output = self.intervention_designer.execute_intervention_simulation(
                spec=intervention,
                context=geo_ctx,
                humans=humans,
                temporal=temporal,
                temporal_controller=self.temporal_controller,
                seed=seed,
                include_intervention=True,
                cancel_event=cancel_event,
            )
        else:
            sim_output = {
                "active_engines": [],
                "totals": {},
                "temporal_execution": {"simulated_ticks_equivalent": 0, "wall_clock_seconds": 0.0, "history": []},
                "ledger_conservation": {"conservation_passed": True, "cash_conservation_diff": 0.0, "total_transactions": 0},
            }

        _emit("COLLECTING_EVIDENCE", "Recopilando evidencia y trazabilidad de agentes")
        evidence = self.evidence_engine.collect_evidence(
            scenario_id=sid,
            seed=seed,
            context=geo_ctx,
            temporal=temporal,
            intervention=intervention,
            sim_output=sim_output,
            humans=humans,
            pop_accounting=pop_acc,
        )

        # Restore persistent baseline state so repeated scenarios never corrupt persistent identities
        self.population_manager.restore_baseline_snapshot(baseline_snap)

        comparison = None
        if compare_alternatives and geo_ctx.resolved and humans:
            _emit("COMPARING_SCENARIOS", "Comparando escenarios alternativos con múltiples semillas")
            comparison = self.comparison_engine.compare_scenarios(
                context=geo_ctx,
                base_intervention=intervention,
                temporal=temporal,
                seeds=[seed, seed + 59, seed + 160],
                max_active_agents=min(32, safe_agent_cap),
            )

        _emit("ANALYZING_RESULTS", "Analizando resultados y generando recomendaciones")
        recommendation = self.decision_analyst.analyze(
            evidence=evidence,
            context=geo_ctx,
            intervention=intervention,
            comparison=comparison,
        )

        # Save checkpoint & execution provenance
        execution_id = f"EXEC_{uuid4().hex[:10]}"
        ckpt = sim_output.get("temporal_execution", {}).get("checkpoint")
        checkpoint_id = None
        if ckpt is not None:
            checkpoint_id = f"CKPT_{sid}_{seed}"
            self.persistence.save_checkpoint(
                checkpoint_id=checkpoint_id,
                scenario_id=sid,
                seed=seed,
                completed_steps=ckpt.completed_steps,
                total_steps=ckpt.total_steps,
                simulated_days=ckpt.simulated_days_elapsed,
                state_summary=ckpt.state_summary,
            )

        provenance_record = {
            "conversation_id": session.conversation_id,
            "scenario_id": sid,
            "execution_id": execution_id,
            "seed": seed,
            "map_visible": map_visible,
            "district_id": geo_ctx.district_id,
            "active_engines": evidence.active_engines,
            "ledger_conservation": evidence.ledger_audit,
            "analyst_provider": recommendation.provider_used,
            "analyst_model": recommendation.model_used,
            "timestamp": time.time(),
        }

        self.persistence.save_execution_record(
            execution_id=execution_id,
            conversation_id=session.conversation_id,
            scenario_id=sid,
            seed=seed,
            evidence=evidence,
            recommendation=recommendation,
            provenance_record=provenance_record,
            checkpoint_id=checkpoint_id,
        )

        # Phase 1.17: Enrich Stage B with complete territorial intelligence & partitioned A–G evidence package
        ti_stage_b: Dict[str, Any] = {}
        if geo_ctx.resolved:
            ti_stage_b = self._build_stage_b_intelligence_package(
                scenario_id=sid,
                seed=seed,
                geo_ctx=geo_ctx,
                temporal=temporal,
                intervention=intervention,
                humans=humans,
                sim_evidence=evidence,
                recommendation=recommendation,
            )

        turn_msg = (
            f"[{recommendation.verdict.value}] {recommendation.executive_summary}"
        )
        stage_b_turn = ConversationTurn(
            turn_index=len(session.turns),
            role="assistant",
            message=turn_msg,
            timestamp=time.time(),
            stage=AnalysisStage.STAGE_B_SIMULATED,
            scenario_id=sid,
            intent="SIMULATION_EXECUTION",
        )
        session.turns.append(stage_b_turn)
        self.persistence.save_session(session)
        self.persistence.append_turn(session.conversation_id, stage_b_turn)

        res = SimulationStudioResult(
            conversation_id=session.conversation_id,
            scenario_id=sid,
            execution_id=execution_id,
            map_visible=map_visible,
            territorial_context=geo_ctx,
            temporal_horizon=temporal,
            intervention=intervention,
            evidence=evidence,
            recommendation=recommendation,
            comparison=comparison,
            checkpoint_id=checkpoint_id,
            provenance_record=provenance_record,
            territorial_intelligence=ti_stage_b,
            assistant_reply=turn_msg,
        )
        from saltbor.conversational.progressive_reports import ProgressiveReportBuilder

        res.progressive_report = ProgressiveReportBuilder.build_from_studio_result(res)
        return res

    # =========================================================================
    # Background Execution & Cancellation
    # =========================================================================

    def start_background_stage_b(
        self,
        conversation_id: str,
        scenario_id: Optional[str] = None,
        seed: int = 42,
        compare_alternatives: bool = False,
        max_active_agents: int = 40,
        map_visible: bool = False,
    ) -> str:
        """Launch Stage B simulation in a cancellable background thread."""
        job_id = f"JOB_{uuid4().hex[:10]}"
        cancel_evt = threading.Event()
        with self._lock:
            self._job_cancels[job_id] = cancel_evt
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "RUNNING",
                "stage_code": "VALIDATING_SCENARIO",
                "stage_label": "Configurando simulación",
                "stage_history": [{"code": "VALIDATING_SCENARIO", "label": "Configurando simulación"}],
                "conversation_id": conversation_id,
                "scenario_id": scenario_id,
                "result": None,
                "error": None,
            }

        def _on_progress(code: str, label: str) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["stage_code"] = code
                    job["stage_label"] = label
                    hist = job.setdefault("stage_history", [])
                    if not hist or hist[-1]["code"] != code:
                        hist.append({"code": code, "label": label})

        def _worker() -> None:
            try:
                res = self.execute_stage_b(
                    conversation_id=conversation_id,
                    scenario_id=scenario_id,
                    seed=seed,
                    compare_alternatives=compare_alternatives,
                    max_active_agents=max_active_agents,
                    map_visible=map_visible,
                    cancel_event=cancel_evt,
                    progress_callback=_on_progress,
                )
                with self._lock:
                    if cancel_evt.is_set():
                        self._jobs[job_id]["status"] = "CANCELLED"
                        self._jobs[job_id]["stage_code"] = "CANCELLED"
                        self._jobs[job_id]["stage_label"] = "Cancelado por el usuario"
                    elif res.recommendation.verdict.value == "INSUFFICIENT_EVIDENCE":
                        self._jobs[job_id]["status"] = "COMPLETED"
                        self._jobs[job_id]["stage_code"] = "INSUFFICIENT_DATA"
                        self._jobs[job_id]["stage_label"] = "Datos insuficientes"
                    else:
                        self._jobs[job_id]["status"] = "COMPLETED"
                        self._jobs[job_id]["stage_code"] = "COMPLETED"
                        self._jobs[job_id]["stage_label"] = "Completado"
                    self._jobs[job_id]["result"] = res.model_dump(mode="json")
            except Exception as exc:
                with self._lock:
                    self._jobs[job_id]["status"] = "FAILED"
                    self._jobs[job_id]["stage_code"] = "FAILED"
                    self._jobs[job_id]["stage_label"] = "Error en simulación"
                    self._jobs[job_id]["error"] = str(exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return job_id

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._jobs[job_id]) if job_id in self._jobs else None

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            evt = self._job_cancels.get(job_id)
            if evt is None:
                return False
            evt.set()
            if job_id in self._jobs and self._jobs[job_id]["status"] == "RUNNING":
                self._jobs[job_id]["status"] = "CANCELLING"
            return True

    @staticmethod
    def _determine_required_engines(
        intent: ConversationIntent,
        intervention: Optional[InterventionSpec],
    ) -> List[str]:
        engines = ["NationalTerritorialContextEngine", "NationalPopulationActivationManager", "VerifiableEconomicLedger"]
        if intent == ConversationIntent.BUSINESS_PLACEMENT or (
            intervention and intervention.category in (
                InterventionCategory.PUPUSERIA,
                InterventionCategory.RESTAURANT,
                InterventionCategory.SHOP,
                InterventionCategory.MARKET,
                InterventionCategory.PHARMACY,
                InterventionCategory.COMMERCIAL_ESTABLISHMENT,
                InterventionCategory.AGRICULTURAL_BUSINESS,
            )
        ):
            engines.extend(["CommercialEngine", "BusinessEnterprise", "LaborMarketEngine"])
        if intent in (ConversationIntent.EDUCATIONAL_INFRASTRUCTURE, ConversationIntent.HEALTH_INFRASTRUCTURE, ConversationIntent.PUBLIC_SERVICES):
            engines.append("PublicServiceCapacityEngine")
        if intent == ConversationIntent.TRANSPORT_INFRASTRUCTURE:
            engines.extend(["IntegratedWorldSimulationEngine", "PublicServiceCapacityEngine"])
        engines.extend([
            "NationalBuildingIntelligenceEngine",
            "CommercialActivityIntelligenceEngine",
            "TerritorialCatchmentAnalysisEngine",
            "HumanMobilityFlowEngine",
            "TerritorialLaborMarketEngine",
            "TerritorialEvidenceEngine",
            "SyntheticPopulationEvidenceEngine",
            "GeminiDecisionAnalyst",
        ])
        return list(dict.fromkeys(engines))

    def _infer_service_type(self, message: str, intervention: Optional[InterventionSpec]) -> str:
        if intervention is not None:
            return intervention.category.value.lower()
        norm = _norm(message)
        if "pupus" in norm:
            return "pupuseria"
        if "farmac" in norm:
            return "pharmacy"
        if "escuel" in norm or "coleg" in norm:
            return "school"
        if "hospital" in norm:
            return "hospital"
        if "centro comercial" in norm:
            return "commercial_center"
        if "empleo" in norm or "fabrica" in norm or "trabajo" in norm:
            return "employment_center"
        return "general"

    def _get_static_territorial_bundle(
        self,
        geo_ctx: TerritorialContext,
        service_type: str,
        include_landuse: bool = False,
    ) -> Dict[str, Any]:
        """Return cached static territorial intelligence (catchment/buildings/commerce/coverage/landuse)."""
        cache_key = (
            geo_ctx.district_id or "",
            round(float(geo_ctx.lat), 5),
            round(float(geo_ctx.lon), 5),
            service_type,
        )
        entry = self._ti_static_cache.get(cache_key)
        if entry is None:
            catchment = self.on_demand_engine.catchment_engine.analyze_catchment(
                context=geo_ctx,
                service_type=service_type,
            )
            bldg = self.on_demand_engine.building_engine.analyze_buildings(
                lat=geo_ctx.lat,
                lon=geo_ctx.lon,
                radius_km=min(1.5, catchment.effective_radius_km),
                limit=100,
                include_sample_limit=40,
            )
            comm = self.on_demand_engine.economic_context_engine.build_economic_context(
                context=geo_ctx,
                radius_km=catchment.effective_radius_km,
                area_km2=catchment.effective_area_km2,
                building_report=bldg,
            )
            cov = self.on_demand_engine.coverage_registry.get_district_coverage(geo_ctx.district_id)
            entry = {
                "catchment": catchment,
                "bldg": bldg,
                "comm": comm,
                "cov": cov,
                "lu": None,
            }
            if len(self._ti_static_cache) >= 64:
                oldest_key = next(iter(self._ti_static_cache))
                self._ti_static_cache.pop(oldest_key, None)
            self._ti_static_cache[cache_key] = entry

        if include_landuse and entry["lu"] is None:
            entry["lu"] = self.on_demand_engine.land_use_engine.analyze_land_use(
                context=geo_ctx,
                radius_km=entry["catchment"].effective_radius_km,
            )
        return entry

    def _build_stage_a_intelligence_snapshot(
        self,
        geo_ctx: TerritorialContext,
        message: str,
        intervention: Optional[InterventionSpec],
    ) -> Dict[str, Any]:
        """Collect observed Phase 1.17 territorial intelligence for Stage A without simulating outcomes."""
        try:
            service_type = self._infer_service_type(message, intervention)
            bundle = self._get_static_territorial_bundle(
                geo_ctx=geo_ctx,
                service_type=service_type,
                include_landuse=False,
            )
            catchment = bundle["catchment"]
            bldg = bundle["bldg"]
            comm = bundle["comm"]
            cov = bundle["cov"]
            labor = self.on_demand_engine.labor_engine.analyze_labor_market(
                context=geo_ctx,
                commercial_report=comm,
            )
            return {
                "coverage_tier": cov.coverage_tier.value if cov else "PARTIAL",
                "coverage_confidence": cov.overall_confidence if cov else geo_ctx.data_quality_score,
                "catchment": {
                    "service_type": catchment.service_type,
                    "scale": catchment.scale.value,
                    "method": catchment.primary_method.value,
                    "effective_radius_km": catchment.effective_radius_km,
                    "effective_area_km2": catchment.effective_area_km2,
                    "circuity_factor": catchment.circuity_factor,
                    "barriers_detected": catchment.barriers_detected,
                    "methodology": catchment.methodology_explanation,
                    "isochrone_polygon_geojson": catchment.isochrone_polygon_geojson,
                },
                "buildings": {
                    "total_observed": bldg.total_buildings_observed,
                    "counts_by_use": bldg.counts_by_use,
                    "counts_by_origin": bldg.counts_by_origin,
                    "is_partial_coverage": bldg.is_partial_coverage,
                },
                "commerce": {
                    "confirmed_establishments": comm.concentration_metrics.confirmed_establishments_count,
                    "unverified_commercial_buildings": comm.concentration_metrics.unverified_commercial_buildings_count,
                    "business_density_per_km2": comm.concentration_metrics.business_density_per_km2,
                    "diversity_shannon_norm": comm.concentration_metrics.commercial_diversity_shannon_norm,
                    "category_counts": comm.category_counts,
                    "top_establishments": [e.model_dump(mode="json") for e in comm.establishments[:12]],
                },
                "employment": {
                    "verified_job_vacancies_count": len(labor.verified_job_vacancies),
                    "known_employers_count": len(labor.known_employers),
                    "potential_labor_supply_approx": labor.potential_labor_supply_approx,
                    "jobs_workers_spatial_mismatch": labor.jobs_workers_spatial_mismatch_index,
                    "sectoral_estimates": labor.sectoral_employment_estimates,
                    "opportunity_hypotheses": labor.opportunity_hypotheses,
                },
            }
        except Exception as exc:
            logger.debug("Stage A territorial intelligence enrichment fallback: %s", exc)
            return {}

    def _build_stage_b_intelligence_package(
        self,
        scenario_id: str,
        seed: int,
        geo_ctx: TerritorialContext,
        temporal: TemporalHorizonSpec,
        intervention: Optional[InterventionSpec],
        humans: List[Any],
        sim_evidence: Any,
        recommendation: Any,
    ) -> Dict[str, Any]:
        """Assemble full Phase 1.17 intelligence, A–G evidence package, and SQLite WAL persistence."""
        try:
            from saltbor.territorial_intelligence.schemas import (
                LifecycleTransition,
                OnDemandScenarioRecord,
                TerritorialSimulationState,
            )

            service_type = self._infer_service_type(
                intervention.name if intervention else "",
                intervention,
            )
            bundle = self._get_static_territorial_bundle(
                geo_ctx=geo_ctx,
                service_type=service_type,
                include_landuse=True,
            )
            catchment = bundle["catchment"]
            bldg = bundle["bldg"]
            lu = bundle["lu"]
            comm = bundle["comm"]
            cov = bundle["cov"]
            pop_dist = self.on_demand_engine.population_dist_engine.activate_for_territory(
                context=geo_ctx,
                building_report=bldg,
                max_active_agents=max(8, len(humans)),
                seed=seed,
            )
            mobility = self.on_demand_engine.mobility_engine.analyze_mobility(
                context=geo_ctx,
                humans=humans,
                catchment=catchment,
                commercial_report=comm,
            )
            labor = self.on_demand_engine.labor_engine.analyze_labor_market(
                context=geo_ctx,
                commercial_report=comm,
                mobility_report=mobility,
                humans=humans,
            )
            pkg = self.on_demand_engine.evidence_engine.build_evidence_package(
                scenario_id=scenario_id,
                seed=seed,
                context=geo_ctx,
                horizon_days=temporal.horizon_days,
                building_report=bldg,
                land_use_report=lu,
                commercial_report=comm,
                catchment=catchment,
                mobility_report=mobility,
                employment_report=labor,
                coverage_record=cov,
                humans=humans,
                sim_evidence=sim_evidence,
                recommendation=recommendation,
            )

            now = time.time()
            rec = OnDemandScenarioRecord(
                scenario_id=scenario_id,
                state=TerritorialSimulationState.COMPLETED,
                state_history=[
                    LifecycleTransition(state=TerritorialSimulationState.COMPLETED, timestamp=now, detail="Stage B Studio completed")
                ],
                query=geo_ctx.query or geo_ctx.district_name,
                objective=intervention.name if intervention else "Análisis territorial",
                resolved_location={
                    "department_code": geo_ctx.department_code,
                    "department_name": geo_ctx.department_name,
                    "municipality_id": geo_ctx.municipality_id,
                    "municipality_name": geo_ctx.municipality_name,
                    "district_id": geo_ctx.district_id,
                    "district_name": geo_ctx.district_name,
                    "lat": geo_ctx.lat,
                    "lon": geo_ctx.lon,
                },
                coverage_assessment=cov,
                building_intelligence=bldg,
                land_use_intelligence=lu,
                commercial_context=comm,
                catchment=catchment,
                mobility_flow=mobility,
                employment_analysis=labor,
                population_activation=pop_dist,
                activated_engines=list(sim_evidence.active_engines),
                evidence_package=pkg,
                seed=seed,
                horizon_days=temporal.horizon_days,
                created_at=now,
                updated_at=now,
            )
            self.persistence.save_territorial_scenario(rec)
            active_uids = {str(h.identity.uid) for h in humans}
            self.persistence.save_population_assignments(
                [
                    a
                    for a in self.on_demand_engine.population_dist_engine.get_all_spatial_assignments()
                    if a.get("uid") in active_uids
                ]
            )

            return {
                "coverage_tier": cov.coverage_tier.value if cov else "PARTIAL",
                "coverage_confidence": cov.overall_confidence if cov else geo_ctx.data_quality_score,
                "buildings": {
                    "total_observed": bldg.total_buildings_observed,
                    "counts_by_use": bldg.counts_by_use,
                    "counts_by_origin": bldg.counts_by_origin,
                },
                "commerce": {
                    "confirmed_establishments": comm.concentration_metrics.confirmed_establishments_count,
                    "unverified_commercial_buildings": comm.concentration_metrics.unverified_commercial_buildings_count,
                    "business_density_per_km2": comm.concentration_metrics.business_density_per_km2,
                    "diversity_shannon_norm": comm.concentration_metrics.commercial_diversity_shannon_norm,
                    "category_counts": comm.category_counts,
                    "top_establishments": [e.model_dump(mode="json") for e in comm.establishments[:15]],
                },
                "catchment": {
                    "scale": catchment.scale.value,
                    "method": catchment.primary_method.value,
                    "effective_radius_km": catchment.effective_radius_km,
                    "effective_area_km2": catchment.effective_area_km2,
                    "circuity_factor": catchment.circuity_factor,
                    "barriers_detected": catchment.barriers_detected,
                    "methodology": catchment.methodology_explanation,
                    "isochrone_polygon_geojson": catchment.isochrone_polygon_geojson,
                },
                "mobility": {
                    "time_period": mobility.time_period.value,
                    "day_type": mobility.day_type.value,
                    "role_breakdown": mobility.role_breakdown,
                    "estimated_pedestrian_activity_index": mobility.estimated_pedestrian_activity_index,
                    "estimated_daily_arrivals": mobility.estimated_daily_arrivals,
                    "estimated_daily_departures": mobility.estimated_daily_departures,
                    "corridors": [c.model_dump(mode="json") for c in mobility.mobility_corridors[:5]],
                    "measured_flows_available": mobility.measured_flows_available,
                    "measured_flows_note": mobility.measured_flows_note,
                },
                "employment": {
                    "verified_job_vacancies_count": len(labor.verified_job_vacancies),
                    "known_employers_count": len(labor.known_employers),
                    "potential_labor_supply_approx": labor.potential_labor_supply_approx,
                    "jobs_workers_spatial_mismatch": labor.jobs_workers_spatial_mismatch_index,
                    "opportunity_hypotheses": labor.opportunity_hypotheses,
                },
                "evidence_tiers": pkg.model_dump(mode="json"),
            }
        except Exception as exc:
            logger.debug("Stage B territorial intelligence enrichment fallback: %s", exc)
            return {}
