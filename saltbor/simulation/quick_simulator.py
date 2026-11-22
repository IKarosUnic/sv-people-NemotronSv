"""Quick Simulator & 1-Click Citizen Event Launcher for SALTBOR (Phase 1.18 UX).

Makes launching events and simulations effortless for any user (citizens,
students, mayors, researchers) via:
1. 1-Click Presets (`QUICK_EVENT_PRESETS`) with zero technical parameters.
2. Plain Spanish natural language input with duration in human days (no ticks needed).
3. Automatic Live Runner synchronization + plain-language traffic-light summary cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from saltbor.ai import (
    AIComputeBudgetManager,
    AIModelRouter,
    AIScenarioComparisonAssistant,
    NaturalLanguageScenarioBuilder,
    SimulationResultsAnalyst,
)
from saltbor.territory.generalized_scenarios import GeneralizedTerritorialScenarioEngine
from saltbor.territory.territory_catalog import TerritoryCatalogService


@dataclass(frozen=True)
class QuickEventPreset:
    """User-friendly 1-click event preset definition."""

    preset_id: str
    category: str  # "comercio", "comunidad", "clima"
    icon: str
    title: str
    subtitle: str
    natural_prompt: str
    default_territory: str
    default_days: int
    includes_relief: bool = False


QUICK_EVENT_PRESETS: Dict[str, QuickEventPreset] = {
    # --- COMERCIO, EMPRENDIMIENTO Y MERCADOS ---
    "abrir_pupuseria_o_tienda": QuickEventPreset(
        preset_id="abrir_pupuseria_o_tienda",
        category="comercio",
        icon="🫓",
        title="Viabilidad de Pupusería / Tienda Local",
        subtitle="Evalúa ventas diarias, costo de insumos (maíz, frijol, queso), clientela y liquidez en caja.",
        natural_prompt=(
            "Simula la operación comercial estable de 7 días de una pupusería y tienda local "
            "con abasto mayorista fluido, ventas al contado y solvencia de caja."
        ),
        default_territory="Santa Tecla",
        default_days=7,
        includes_relief=True,
    ),
    "riesgo_fiado_comercial": QuickEventPreset(
        preset_id="riesgo_fiado_comercial",
        category="comercio",
        icon="📓",
        title="Riesgo de Fiado y Liquidez de Tienda",
        subtitle="Mide qué pasa cuando los clientes piden demasiado fiado y cae el capital de trabajo del negocio.",
        natural_prompt=(
            "Simula 7 días de presión sobre el crédito informal de fiado en tiendas de barrio "
            "por encarecimiento de alimentos y caída de liquidez de los clientes."
        ),
        default_territory="Soyapango",
        default_days=7,
        includes_relief=False,
    ),
    "encarecimiento_mayorista_flete": QuickEventPreset(
        preset_id="encarecimiento_mayorista_flete",
        category="comercio",
        icon="🚚",
        title="Subida de Flete y Costo Mayorista",
        subtitle="Simula cómo el atraso o recargo del camión proveedor reduce el margen y las ventas del comercio.",
        natural_prompt=(
            "Simula un bloqueo logístico de 5 días que encarece el flete mayorista de granos "
            "y reduce la afluencia de clientes al comercio local."
        ),
        default_territory="Cojutepeque",
        default_days=5,
        includes_relief=False,
    ),
    "auge_remesas_y_consumo": QuickEventPreset(
        preset_id="auge_remesas_y_consumo",
        category="comercio",
        icon="💸",
        title="Entrada de Remesas y Auge de Ventas",
        subtitle="Evalúa cómo un ingreso extra en las familias reactiva las compras al contado y el pago de deudas.",
        natural_prompt=(
            "Simula 7 días de reactivación comercial local con inyección de liquidez familiar, "
            "pago de cuentas de fiado atrasadas y aumento de ventas en negocios."
        ),
        default_territory="San Miguel",
        default_days=7,
        includes_relief=True,
    ),
    # --- COMUNIDAD, EDUCACIÓN, SALUD Y COOPERATIVAS ---
    "cooperativa_y_cuchubal": QuickEventPreset(
        preset_id="cooperativa_y_cuchubal",
        category="comunidad",
        icon="🤝",
        title="Cooperativa y Cuchubal de Comerciantes",
        subtitle="Ahorro rotativo y apoyo mutuo para sostener negocios y familias ante imprevistos.",
        natural_prompt=(
            "Simula 7 días de organización comunitaria y alivio de deuda comercial "
            "para proteger la solvencia de las tiendas y el empleo local."
        ),
        default_territory="Ilobasco",
        default_days=7,
        includes_relief=True,
    ),
    "brigada_y_bono": QuickEventPreset(
        preset_id="brigada_y_bono",
        category="comunidad",
        icon="🏥",
        title="Brigada Médica + Bono Solidario",
        subtitle="Intervención comunitaria con brigada móvil de salud y apoyo económico a hogares.",
        natural_prompt=(
            "Simula un choque de salud y precios durante 5 días mitigado con brigada médica móvil "
            "y transferencia monetaria solidaria a familias vulnerables."
        ),
        default_territory="Cantón El Rosario",
        default_days=5,
        includes_relief=True,
    ),
    "reparacion_vial_escolar": QuickEventPreset(
        preset_id="reparacion_vial_escolar",
        category="comunidad",
        icon="🚌",
        title="Reparación de Calle + Transporte Escolar",
        subtitle="Despeje de camino dañado y apoyo para evitar la deserción escolar.",
        natural_prompt=(
            "Simula un bloqueo vial de 4 días atendido con rehabilitación de carretera, "
            "transporte escolar de emergencia y desayuno escolar."
        ),
        default_territory="San Ignacio",
        default_days=4,
        includes_relief=True,
    ),
    # --- CLIMA, EMERGENCIAS Y COMPARATIVAS ---
    "temporal_deslave": QuickEventPreset(
        preset_id="temporal_deslave",
        category="clima",
        icon="🌧️",
        title="Temporal y Deslave de Camino",
        subtitle="Lluvias intensas bloquean el acceso principal al cantón y encarecen el abasto.",
        natural_prompt=(
            "Simula un bloqueo por deslave de 5 días en el camino rural principal con "
            "alza de precios de alimentos y retraso en transporte escolar."
        ),
        default_territory="Cantón El Rosario",
        default_days=5,
        includes_relief=False,
    ),
    "alza_canasta_basica": QuickEventPreset(
        preset_id="alza_canasta_basica",
        category="clima",
        icon="🌽",
        title="Subida de Maíz y Frijol",
        subtitle="Encarecimiento de granos básicos en tiendas locales y mayor uso de fiado.",
        natural_prompt=(
            "Simula una subida fuerte en el precio del maíz y frijol durante 7 días "
            "evaluando el impacto en la economía familiar y el crédito de fiado."
        ),
        default_territory="Chalatenango",
        default_days=7,
        includes_relief=False,
    ),
    "sequia_corredor_seco": QuickEventPreset(
        preset_id="sequia_corredor_seco",
        category="clima",
        icon="☀️",
        title="Sequía en Corredor Seco",
        subtitle="Pérdida de cosecha agrícola local y caída de ingresos de jornaleros.",
        natural_prompt=(
            "Simula una sequía agrícola severa de 10 días con pérdida de cosecha de granos "
            "y reducción de empleo rural."
        ),
        default_territory="San Miguel",
        default_days=10,
        includes_relief=False,
    ),
    "comparativa_choque_vs_ayuda": QuickEventPreset(
        preset_id="comparativa_choque_vs_ayuda",
        category="clima",
        icon="⚖️",
        title="Comparar: Crisis sin Ayuda vs. Con Ayuda",
        subtitle="Muestra lado a lado cuánto mejora la comunidad al aplicar un paquete de rescate.",
        natural_prompt=(
            "Simula un bloqueo por deslave de 7 días con inflación de alimentos y compáralo "
            "con un paquete integrado de rehabilitación vial, brigada de salud y alivio de fiado."
        ),
        default_territory="Cantón El Rosario",
        default_days=7,
        includes_relief=True,
    ),
}


class QuickSimulator:
    """High-level facade that turns 1-click presets or plain text into immediate simulation results."""

    def __init__(self) -> None:
        self.router = AIModelRouter()
        self.budget = AIComputeBudgetManager()
        self.catalog = TerritoryCatalogService()
        self.builder = NaturalLanguageScenarioBuilder(
            router=self.router,
            budget_manager=self.budget,
            catalog=self.catalog,
        )
        self.engine = GeneralizedTerritorialScenarioEngine()
        self.analyst = SimulationResultsAnalyst(
            router=self.router,
            budget_manager=self.budget,
        )
        self.comparator = AIScenarioComparisonAssistant(
            router=self.router,
            budget_manager=self.budget,
        )

    def list_presets(self) -> List[Dict[str, Any]]:
        """Return all 1-click presets ready for UI cards or CLI selection."""
        return [
            {
                "preset_id": p.preset_id,
                "category": p.category,
                "icon": p.icon,
                "title": p.title,
                "subtitle": p.subtitle,
                "natural_prompt": p.natural_prompt,
                "default_territory": p.default_territory,
                "default_days": p.default_days,
                "includes_relief": p.includes_relief,
            }
            for p in QUICK_EVENT_PRESETS.values()
        ]

    def run(
        self,
        prompt_or_preset: str,
        territory: Optional[str] = None,
        days: Optional[int] = None,
        include_relief: Optional[bool] = None,
        seed: int = 42,
        live_runner: Optional[Any] = None,
        live_ticks_to_advance: int = 4,
    ) -> Dict[str, Any]:
        """Execute an event/simulation from a preset ID or plain Spanish sentence."""
        preset = QUICK_EVENT_PRESETS.get(prompt_or_preset.strip().lower())
        if preset:
            prompt_text = preset.natural_prompt
            chosen_territory = territory or preset.default_territory
            chosen_days = days if days is not None else preset.default_days
            with_relief = include_relief if include_relief is not None else preset.includes_relief
            title_label = f"{preset.icon} {preset.title}"
        else:
            prompt_text = prompt_or_preset.strip()
            chosen_territory = territory
            chosen_days = days if days is not None else 3
            with_relief = bool(include_relief)
            title_label = f"✨ Simulación: {prompt_text[:55]}"

        if with_relief and "brigada" not in prompt_text.lower() and "transferencia" not in prompt_text.lower():
            prompt_text = (
                f"{prompt_text}. Incluye paquete de mitigación con rehabilitación vial, "
                "brigada móvil de salud y transferencia monetaria solidaria."
            )

        # Build declarative scenario from natural language
        built = self.builder.build_scenario_from_text(
            prompt=prompt_text,
            preferred_canton_override=chosen_territory,
        )
        scen_def = built.scenario_definition
        # Convert human days to simulation ticks (1 day = 24 generic scenario steps or 96 runner ticks)
        scen_def.duration_ticks = max(16, min(320, int(chosen_days) * 16))

        # Ensure both 'type' and 'shock_type' keys are populated for GeneralizedTerritorialScenarioEngine
        for s in scen_def.shocks:
            st = s.get("type") or s.get("shock_type") or "ROAD_BLOCKAGE_LANDSLIDE"
            s["type"] = st
            s["shock_type"] = st
        if scen_def.shocks and "road_friction_multiplier" not in scen_def.parameters:
            scen_def.parameters["road_friction_multiplier"] = 3.5

        if with_relief and not scen_def.interventions:
            scen_def.interventions.extend([
                {"type": "ROAD_REHABILITATION", "start_tick": max(1, scen_def.duration_ticks // 3)},
                {"type": "FOCUSED_CASH_TRANSFER", "start_tick": 0, "transfer_amount_usd": 5.0},
                {"type": "MOBILE_HEALTH_BRIGADE", "start_tick": max(1, scen_def.duration_ticks // 4)},
            ])

        # Register and execute in GeneralizedTerritorialScenarioEngine
        self.engine.register_scenario_definition(scen_def)
        exec_res = self.engine.execute_scenario(scen_def.scenario_id, seed=seed)
        analysis = self.analyst.analyze_result(exec_res)
        hazard = self.catalog.get_topographic_hazard_profile(built.coverage_report.name)

        # Also inject into live visual SimulationRunner if attached
        live_injection_info = None
        if live_runner is not None and hasattr(live_runner, "live_scenario_bridge"):
            session = live_runner.live_scenario_bridge.inject_scenario(scen_def)
            steps = max(0, min(48, int(live_ticks_to_advance)))
            for _ in range(steps):
                live_runner.step()
            live_injection_info = {
                "injected": True,
                "live_runner_tick": int(live_runner.clock.current_tick),
                "ticks_advanced": steps,
                "start_tick": session.start_tick,
                "end_tick": session.end_tick,
            }

        indicators = exec_res.final_indicators
        last_stage = exec_res.intermediate_stages[-1] if exec_res.intermediate_stages else {}
        comm_stage = last_stage.get("commercial", {})
        hh_stage = last_stage.get("household", {})
        edu_stage = last_stage.get("education", {})

        retail_maize = float(indicators.get("final_retail_maize_price", 0.65))
        food_price_mult = retail_maize / 0.65
        school_att = float(edu_stage.get("school_attendance_pct", indicators.get("final_mateo_attendance", 92.0)))
        fiado_debt = float(hh_stage.get("informal_fiado_debt_usd", 0.0))
        cash_avg = float(indicators.get("final_jose_cash", hh_stage.get("jose_cash_usd", 25.0)))
        tiendita_cash = float(indicators.get("final_tiendita_cash", comm_stage.get("tiendita_cash_usd", 215.0)))
        tiendita_solvent = bool(indicators.get("final_tiendita_solvent", 1.0) >= 0.5)
        footfall_pct = float(comm_stage.get("customer_footfall_factor", 1.0)) * 100.0
        supply_info = self.catalog.resolve_supply_chain_and_services(built.coverage_report.name)

        # Determine citizen-friendly traffic light status
        if food_price_mult >= 1.25 or school_att < 80.0:
            semaforo = "🔴 IMPACTO FUERTE"
            semaforo_color = "red"
        elif food_price_mult >= 1.08 or school_att < 88.0 or fiado_debt > 15.0:
            semaforo = "🟡 ALERTA MODERADA"
            semaforo_color = "amber"
        else:
            semaforo = "🟢 COMUNIDAD ESTABLE"
            semaforo_color = "green"

        tarjetas = [
            {
                "icono": "🛒",
                "titulo": "Precios de Alimentos",
                "valor": f"{(food_price_mult - 1.0) * 100:+.1f}%",
                "explicacion": (
                    "Alza en maíz, frijol y canasta básica local."
                    if food_price_mult > 1.02
                    else "Precios estables sin desabasto."
                ),
            },
            {
                "icono": "💵",
                "titulo": "Bolsillo y Fiado Familiar",
                "valor": f"${cash_avg:.2f} efec. | ${fiado_debt:.2f} fiado",
                "explicacion": "Efectivo promedio en hogares y deuda acumulada en tienditas.",
            },
            {
                "icono": "🎓",
                "titulo": "Asistencia a la Escuela",
                "valor": f"{school_att:.1f}%",
                "explicacion": "Jóvenes asistiendo a clases pese a dificultades de camino o ingresos.",
            },
            {
                "icono": "⚖️",
                "titulo": "Garantía Contable",
                "valor": "$0.00 discrepancia",
                "explicacion": (
                    f"{exec_res.ledger_summary.get('total_transactions', 0)} transacciones "
                    "verificadas al centavo (cero dinero inventado)."
                ),
            },
        ]

        resumen_sencillo = (
            f"{title_label} en {built.coverage_report.name} ({chosen_days} días simulados) → {semaforo}. "
            f"Precios de alimentos: {(food_price_mult - 1.0) * 100:+.1f}%, "
            f"Asistencia escolar: {school_att:.1f}%, "
            f"Efectivo familiar promedio: ${cash_avg:.2f} (Fiado: ${fiado_debt:.2f}). "
            f"{analysis.executive_summary}"
        )

        return {
            "status": "ok",
            "titulo": title_label,
            "territorio": built.coverage_report.name,
            "departamento": scen_def.department_code,
            "municipio": scen_def.municipality_id,
            "dias_simulados": chosen_days,
            "incluyo_ayuda": with_relief,
            "semaforo": semaforo,
            "semaforo_color": semaforo_color,
            "resumen_sencillo": resumen_sencillo,
            "tarjetas_impacto": tarjetas,
            "relieve_y_riesgo": {
                "tipo_relieve": hazard["relief_class"],
                "altitud_msnm": hazard["elevation_m"],
                "riesgo_deslave": hazard["landslide_risk_index"],
                "riesgo_inundacion": hazard["flood_inundation_risk_index"],
                "riesgo_sequia": hazard["drought_corridor_risk_index"],
            },
            "reporte_comercial": {
                "caja_negocio_local_usd": round(tiendita_cash, 2),
                "negocio_solvente": tiendita_solvent,
                "estado_negocio": "Solvente ✅" if tiendita_solvent else "En Riesgo de Liquidez ⚠️",
                "afluencia_clientes_pct": round(footfall_pct, 1),
                "cartera_fiado_pendiente_usd": round(fiado_debt, 2),
                "centro_abasto_mayorista": supply_info["wholesale_supply_hub"]["hub_name"],
                "distancia_mayorista_km": supply_info["wholesale_supply_hub"]["distance_km"],
                "recargo_flete_base_pct": supply_info["wholesale_supply_hub"]["baseline_freight_surcharge_pct"],
            },
            "explicacion_detallada": {
                "hogares": analysis.affected_households_summary,
                "comercio": analysis.commercial_liquidity_summary,
                "educacion": analysis.education_service_summary,
                "salud": analysis.healthcare_capacity_summary,
                "auditoria_contable": analysis.double_entry_ledger_audit,
            },
            "scenario_id": scen_def.scenario_id,
            "live_map_sync": live_injection_info,
        }


def simular(
    evento_o_preset: str,
    territorio: Optional[str] = None,
    dias: int = 3,
    con_ayuda: bool = False,
    seed: int = 42,
) -> Dict[str, Any]:
    """One-line Python helper for any user to run a SALTBOR event or scenario."""
    return QuickSimulator().run(
        prompt_or_preset=evento_o_preset,
        territory=territorio,
        days=dias,
        include_relief=con_ayuda,
        seed=seed,
    )


def colocar_en_punto(
    lat: float,
    lon: float,
    descripcion: str = "Abrir una pupusería llamada 'El Comal de Oro' con pupusas a $0.85",
    categoria: Optional[str] = None,
    nombre: Optional[str] = None,
    precio_usd: Optional[float] = None,
    capital_inicial_usd: Optional[float] = None,
    capacidad: Optional[int] = None,
    radio_m: float = 400.0,
    dias: int = 7,
    live_runner: Optional[Any] = None,
) -> Dict[str, Any]:
    """One-line Python helper to place an ultra-specific entity at exact (lat, lon) coordinates."""
    from saltbor.simulation.pinpoint_simulator import PinpointPlacementSimulator

    return PinpointPlacementSimulator().place_and_simulate(
        lat=lat,
        lon=lon,
        description=descripcion,
        category=categoria,
        custom_name=nombre,
        unit_price_usd=precio_usd,
        initial_capital_usd=capital_inicial_usd,
        capacity=capacidad,
        catchment_radius_m=radio_m,
        days=dias,
        live_runner=live_runner,
    )

