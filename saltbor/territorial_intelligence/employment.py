"""Employment & Labor-Market Territorial Analysis Engines (Phase 1.17 Section 7).

Separates verified job vacancies, known employers, sectoral employment estimates,
synthetic labor scenarios, and opportunity hypotheses. Simulates employment
interventions (commercial centers, new businesses, factory hiring, road access,
training centers, employer closures) with strict VerifiableEconomicLedger
conservation and commuter labor-market competition.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from saltbor.conversational.schemas import TerritorialContext
from saltbor.population.human import SyntheticHuman
from saltbor.territory.economic_ledger import (
    AccountType,
    TransactionConcept,
    TransactionEntry,
    VerifiableEconomicLedger,
)

from saltbor.territorial_intelligence.schemas import (
    CommercialCategory,
    CommercialContextReport,
    CommercialEstablishmentRecord,
    EmploymentAnalysisReport,
    EmploymentInterventionResult,
    PopulationFlowReport,
)


class TerritorialLaborMarketEngine:
    """Analyzes labor supply, known employers, sectoral structure, and spatial mismatch."""

    def analyze_labor_market(
        self,
        context: TerritorialContext,
        commercial_report: Optional[CommercialContextReport] = None,
        mobility_report: Optional[PopulationFlowReport] = None,
        humans: Optional[List[SyntheticHuman]] = None,
    ) -> EmploymentAnalysisReport:
        pop = max(0, int(context.approx_population))
        is_urban = context.is_urban
        labor_supply = int(round(pop * (0.56 if is_urban else 0.49)))
        informal_share = 0.62 if is_urban else 0.78
        formal_share = round(1.0 - informal_share, 2)

        # Calibrated Salvadoran EHPM sectoral share priors (urban vs rural)
        if is_urban:
            sectoral_estimates = {
                "comercio_y_servicios": 0.44,
                "industria_y_manufactura": 0.19,
                "construccion_y_transporte": 0.14,
                "educacion_salud_y_sector_publico": 0.15,
                "agricultura_periurbana": 0.08,
            }
        else:
            sectoral_estimates = {
                "agricultura_y_ganaderia": 0.46,
                "comercio_informal_y_tiendas": 0.26,
                "construccion_y_oficios": 0.13,
                "servicios_y_educacion": 0.10,
                "agroindustria_local": 0.05,
            }

        # Known employers from real OSM + P8 establishments (never inventing headcount or vacancies!)
        known_employers: List[CommercialEstablishmentRecord] = []
        if commercial_report is not None:
            known_employers = [
                e for e in commercial_report.establishments
                if not e.is_synthetic
            ]

        # Spatial jobs-workers mismatch: high labor supply vs sparse formal/mapped employers & low accessibility
        mapped_emp_density = len(known_employers) / max(1.0, labor_supply / 1000.0)
        supply_pressure = min(1.0, 1.0 - min(0.85, mapped_emp_density * 0.12))
        access_penalty = 1.0 - float(context.accessibility_index)
        mismatch_idx = round(min(1.0, max(0.05, 0.55 * supply_pressure + 0.45 * access_penalty)), 3)

        barriers: List[str] = [
            f"Alta informalidad laboral estructural estimada (~{int(informal_share * 100)}%)."
        ]
        if context.accessibility_index < 0.55:
            barriers.append("Accesibilidad vial/transporte limitada restringe acceso a centros de empleo externos.")
        if float(context.slope_pct or 0.0) >= 12.0:
            barriers.append("Topografía escarpada incrementa costos y tiempos de traslado laboral.")
        if humans:
            low_edu = sum(1 for h in humans if "primaria" in (h.demographics.education_level or "").lower())
            if low_edu / max(1, len(humans)) > 0.35:
                barriers.append("Brecha de calificación técnica/educativa en cohorte activa.")

        hypotheses = [
            "Las oportunidades de autoempleo y microempresa de servicios/alimentos responden a la densidad residencial y flujo peatonal en corredores.",
        ]
        if len(known_employers) >= 15 and mismatch_idx < 0.65:
            hypotheses.append(
                "La presencia de múltiples nodos comerciales y productivos sugiere demanda complementaria en logística, mantenimiento, ventas y servicios."
            )
        else:
            hypotheses.append(
                "El bajo registro de empleadores formales mapeados indica dependencia de empleo por cuenta propia o traslados diarios (commuting) hacia polos urbanos."
            )

        limitations = [
            "SALTBOR no está conectado a bolsas de empleo activas en vivo: verified_job_vacancies=[] (0 vacantes verificadas).",
            "La presencia de un establecimiento en OSM no confirma el número exacto de empleados contratados ni vacantes abiertas.",
        ]

        return EmploymentAnalysisReport(
            district_id=context.district_id,
            district_name=context.district_name,
            verified_job_vacancies=[],
            verified_vacancies_available=False,
            known_employers=known_employers[:60],
            sectoral_employment_estimates=sectoral_estimates,
            potential_labor_supply_approx=labor_supply,
            formal_employment_share_est=formal_share,
            informal_employment_share_est=informal_share,
            labor_accessibility_score=round(float(context.accessibility_index), 3),
            jobs_workers_spatial_mismatch_index=mismatch_idx,
            estimated_unmet_labor_demand_note=(
                f"Fuerza laboral potencial ~{labor_supply:,} personas; índice de desajuste espacial {mismatch_idx:.2f}/1.0."
            ),
            employment_barriers=barriers,
            synthetic_labor_scenarios=[],
            opportunity_hypotheses=hypotheses,
            limitations=limitations,
        )


class EmploymentOpportunityAnalysisEngine:
    """Evaluates & simulates all 6 employment intervention shocks with ledger conservation."""

    def __init__(self, labor_engine: Optional[TerritorialLaborMarketEngine] = None) -> None:
        self.labor_engine = labor_engine or TerritorialLaborMarketEngine()

    def simulate_employment_intervention(
        self,
        intervention_kind: str,
        context: TerritorialContext,
        humans: List[SyntheticHuman],
        horizon_days: int = 30,
        custom_jobs_delta: Optional[int] = None,
    ) -> EmploymentInterventionResult:
        """Simulate labor, commuter-sharing, and conserved wage/consumption effects."""
        kind = (intervention_kind or "NEW_BUSINESSES").upper()
        ledger = VerifiableEconomicLedger()

        defaults = {
            "COMMERCIAL_CENTER": (65, 14.0, +0.28, +0.35),
            "NEW_BUSINESSES": (15, 12.5, +0.10, +0.14),
            "FACTORY_HIRING": (100, 15.0, +0.24, +0.18),
            "ROAD_ACCESSIBILITY": (12, 13.0, +0.32, +0.22),
            "TRAINING_CENTER": (20, 16.0, +0.08, +0.10),
            "EMPLOYER_CLOSURE": (-45, 14.0, -0.18, -0.22),
        }
        base_jobs, daily_wage, mob_delta, comm_delta = defaults.get(kind, (15, 12.5, 0.10, 0.12))
        jobs_delta = custom_jobs_delta if custom_jobs_delta is not None else base_jobs
        if kind == "EMPLOYER_CLOSURE" and jobs_delta > 0:
            jobs_delta = -jobs_delta

        # Realistic labor-market rule: NOT all jobs go to immediate local residents!
        # Commuter share rises when urban accessibility is high or specialized skills (factory/commercial center) are required.
        access = float(context.accessibility_index)
        if kind in ("FACTORY_HIRING", "COMMERCIAL_CENTER"):
            local_share = round(max(0.38, min(0.72, 0.68 - 0.25 * access)), 3)
        elif kind == "TRAINING_CENTER":
            local_share = 0.82
        elif kind == "ROAD_ACCESSIBILITY":
            local_share = 0.55
        else:
            local_share = round(max(0.50, min(0.80, 0.74 - 0.18 * access)), 3)
        commuter_share = round(1.0 - local_share, 3)

        abs_jobs = abs(jobs_delta)
        local_count = int(round(abs_jobs * local_share))
        commuter_count = abs_jobs - local_count
        if jobs_delta < 0:
            local_count = -local_count
            commuter_count = -commuter_count

        # Double-entry accounting via VerifiableEconomicLedger ($0.00 discrepancy)
        employer_acct = f"employer_{kind.lower()}_{context.district_id}"
        commuter_pool_acct = f"commuter_labor_pool_{context.district_id}"
        local_commerce_acct = f"local_commerce_{context.district_id}"

        eff_days = max(1, min(30, horizon_days))
        total_wages = 0.0
        total_consumption = 0.0
        local_workers = [h for h in humans if 18 <= h.demographics.age <= 64][: max(1, min(len(humans), abs(local_count)))]

        if jobs_delta > 0:
            # Seed employer initial working capital in ledger pool
            capital_need = round(abs_jobs * daily_wage * eff_days * 1.25, 2)
            ledger.initial_currency_pool += capital_need
            ledger.record_transaction(
                concept=TransactionConcept.INITIAL_CAPITAL,
                originating_domain="economy",
                description=f"Capital operativo inicial para intervención laboral {kind}",
                entries=[
                    TransactionEntry(f"{employer_acct}_cash", employer_acct, AccountType.ASSET_CASH, capital_need, 0.0),
                    TransactionEntry(f"{employer_acct}_equity", employer_acct, AccountType.EQUITY, 0.0, capital_need),
                ],
                tick=1,
            )

            # Pay local workers + inbound commuters
            for d in range(1, eff_days + 1):
                if local_workers:
                    per_local = round((local_count * daily_wage) / len(local_workers), 2)
                    for h in local_workers:
                        uid_s = str(h.uid)
                        ledger.record_wage_payment(
                            employer_id=employer_acct,
                            worker_id=uid_s,
                            amount_usd=per_local,
                            tick=d * 96,
                            description=f"Salario local día {d}",
                        )
                        h.physical_state.money = round(h.physical_state.money + per_local, 2)
                        total_wages += per_local

                        # Local workers spend ~42% in local shops/services
                        spend = round(per_local * 0.42, 2)
                        if spend > 0:
                            ledger.record_retail_food_purchase_cash(
                                buyer_id=uid_s,
                                tiendita_id=local_commerce_acct,
                                amount_usd=spend,
                                cost_of_goods_usd=round(spend * 0.55, 2),
                                commodity="consumo_local",
                                quantity_lb=1.0,
                                tick=d * 96 + 1,
                            )
                            h.physical_state.money = round(max(0.0, h.physical_state.money - spend), 2)
                            total_consumption += spend

                commuter_wage = round(commuter_count * daily_wage, 2)
                if commuter_wage > 0:
                    ledger.record_wage_payment(
                        employer_id=employer_acct,
                        worker_id=commuter_pool_acct,
                        amount_usd=commuter_wage,
                        tick=d * 96,
                        description=f"Salario commuters entrantes día {d}",
                    )
                    total_wages += commuter_wage
                    # Commuters spend a smaller ~18% fraction inside the destination zone
                    comm_spend = round(commuter_wage * 0.18, 2)
                    if comm_spend > 0:
                        ledger.record_retail_food_purchase_cash(
                            buyer_id=commuter_pool_acct,
                            tiendita_id=local_commerce_acct,
                            amount_usd=comm_spend,
                            cost_of_goods_usd=round(comm_spend * 0.55, 2),
                            commodity="consumo_commuters",
                            quantity_lb=1.0,
                            tick=d * 96 + 2,
                        )
                        total_consumption += comm_spend
        else:
            # Employer closure: reduced local consumption & wage contraction
            lost_wages = round(abs_jobs * daily_wage * eff_days, 2)
            total_wages = -lost_wages
            total_consumption = round(-lost_wages * 0.42, 2)

        is_valid, _, metrics = ledger.verify_accounting_conservation()
        return EmploymentInterventionResult(
            intervention_type=kind,
            location_name=context.district_name,
            direct_jobs_created_or_lost=jobs_delta,
            local_resident_hire_share=local_share,
            inbound_commuter_hire_share=commuter_share,
            local_residents_hired=local_count,
            inbound_commuters_hired=commuter_count,
            total_wages_disbursed_usd=round(total_wages, 2),
            consumption_spillover_usd=round(total_consumption, 2),
            mobility_delta_pct=round(mob_delta * 100.0, 1),
            commercial_attraction_delta_pct=round(comm_delta * 100.0, 1),
            ledger_conservation_diff_usd=float(metrics.get("cash_conservation_diff", 0.0)),
            conservation_passed=bool(is_valid),
            assumptions=[
                f"Los nuevos empleos se distribuyen ({int(local_share*100)}% residentes locales / {int(commuter_share*100)}% commuters entrantes) según accesibilidad vial y perfil de habilidad.",
                f"Propensión marginal al consumo local modelada en 42% para residentes y 18% para commuters sobre horizonte de {eff_days} días.",
            ],
            limitations=[
                "Escenario sintético de mercado laboral; la contratación real depende de salarios vigentes, competencia empresarial y requisitos técnicos.",
            ],
        )
