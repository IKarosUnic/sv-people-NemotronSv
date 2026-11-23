"""Conversation & Experiment Persistence Store (SQLite WAL, Phase 1.16A).

Separates conversational turns and session continuity state from simulation
scenario definitions, execution records, checkpoints, and provenance references.
Never duplicates large simulation logs inside chat history.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from saltbor.conversational.schemas import (
    AnalysisStage,
    ConversationSessionState,
    ConversationTurn,
    DecisionRecommendation,
    EvidenceBundle,
    InterventionSpec,
    TemporalHorizonSpec,
)


class ConversationalPersistenceStore:
    """SQLite WAL persistence backend for Conversational Studio sessions and experiments."""

    def __init__(self, db_path: str | Path = "saltbor_studio.db") -> None:
        self.db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._ensure_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                if self.db_path != ":memory:":
                    Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(
                    self.db_path,
                    timeout=30.0,
                    check_same_thread=False,
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA busy_timeout=30000;")
                self._conn.execute("PRAGMA journal_mode=WAL;")
                self._conn.execute("PRAGMA synchronous=NORMAL;")
                self._conn.execute("PRAGMA foreign_keys=ON;")
            return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _ensure_schema(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS conv_sessions (
                conversation_id         TEXT PRIMARY KEY,
                active_scenario_id      TEXT,
                active_district_id      TEXT,
                active_location_query   TEXT,
                active_coordinates_json TEXT NOT NULL DEFAULT 'null',
                active_intervention_json TEXT NOT NULL DEFAULT 'null',
                active_temporal_json    TEXT NOT NULL DEFAULT 'null',
                scenario_ids_json       TEXT NOT NULL DEFAULT '[]',
                created_at              REAL NOT NULL,
                updated_at              REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conv_turns (
                turn_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                turn_index      INTEGER NOT NULL,
                role            TEXT NOT NULL,
                message         TEXT NOT NULL,
                timestamp       REAL NOT NULL,
                stage           TEXT NOT NULL,
                scenario_id     TEXT,
                intent          TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conv_sessions(conversation_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conv_scenarios (
                scenario_id         TEXT PRIMARY KEY,
                conversation_id     TEXT NOT NULL,
                district_id         TEXT,
                geo_context_json    TEXT NOT NULL DEFAULT '{}',
                temporal_json       TEXT NOT NULL DEFAULT '{}',
                intervention_json   TEXT NOT NULL DEFAULT '{}',
                created_at          REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conv_sessions(conversation_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conv_executions (
                execution_id        TEXT PRIMARY KEY,
                conversation_id     TEXT NOT NULL,
                scenario_id         TEXT NOT NULL,
                seed                INTEGER NOT NULL,
                active_engines_json TEXT NOT NULL DEFAULT '[]',
                evidence_ref_json   TEXT NOT NULL DEFAULT '{}',
                analysis_json       TEXT NOT NULL DEFAULT '{}',
                provenance_json     TEXT NOT NULL DEFAULT '{}',
                checkpoint_id       TEXT,
                created_at          REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conv_sessions(conversation_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conv_checkpoints (
                checkpoint_id       TEXT PRIMARY KEY,
                scenario_id         TEXT NOT NULL,
                seed                INTEGER NOT NULL,
                completed_steps     INTEGER NOT NULL,
                total_steps         INTEGER NOT NULL,
                simulated_days      REAL NOT NULL,
                state_json          TEXT NOT NULL DEFAULT '{}',
                created_at          REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS studio_schema_meta (
                meta_key            TEXT PRIMARY KEY,
                meta_value          TEXT NOT NULL,
                updated_at          REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS territorial_scenarios (
                scenario_id             TEXT PRIMARY KEY,
                state                   TEXT NOT NULL,
                state_history_json      TEXT NOT NULL DEFAULT '[]',
                location_query          TEXT NOT NULL DEFAULT '',
                district_id             TEXT,
                department_code         TEXT,
                lat                     REAL,
                lon                     REAL,
                catchment_json          TEXT NOT NULL DEFAULT '{}',
                seed                    INTEGER NOT NULL DEFAULT 42,
                parameters_json         TEXT NOT NULL DEFAULT '{}',
                provenance_json         TEXT NOT NULL DEFAULT '{}',
                is_historic_benchmark   INTEGER NOT NULL DEFAULT 0,
                record_json             TEXT NOT NULL DEFAULT '{}',
                created_at              REAL NOT NULL,
                updated_at              REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS territorial_evidence_packages (
                package_id              TEXT PRIMARY KEY,
                scenario_id             TEXT NOT NULL,
                seed                    INTEGER NOT NULL DEFAULT 42,
                tier_a_json             TEXT NOT NULL DEFAULT '[]',
                tier_b_json             TEXT NOT NULL DEFAULT '[]',
                tier_c_json             TEXT NOT NULL DEFAULT '[]',
                tier_d_json             TEXT NOT NULL DEFAULT '[]',
                tier_e_json             TEXT NOT NULL DEFAULT '[]',
                tier_f_json             TEXT NOT NULL DEFAULT '[]',
                tier_g_json             TEXT NOT NULL DEFAULT '[]',
                summary_json            TEXT NOT NULL DEFAULT '{}',
                created_at              REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS territorial_coverage_cache (
                territory_id            TEXT PRIMARY KEY,
                level                   TEXT NOT NULL,
                payload_json            TEXT NOT NULL DEFAULT '{}',
                updated_at              REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS persistent_population_assignments (
                uid                     TEXT PRIMARY KEY,
                home_district_id        TEXT NOT NULL,
                current_district_id     TEXT NOT NULL,
                household_id            TEXT NOT NULL,
                lat                     REAL NOT NULL,
                lon                     REAL NOT NULL,
                residential_building_id TEXT,
                state_json              TEXT NOT NULL DEFAULT '{}',
                updated_at              REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS census_datasets_registry (
                dataset_id              TEXT NOT NULL,
                version                 TEXT NOT NULL,
                adapter_name            TEXT NOT NULL,
                published_at            TEXT NOT NULL,
                content_sha256          TEXT NOT NULL,
                metadata_json           TEXT NOT NULL DEFAULT '{}',
                updated_at              REAL NOT NULL,
                PRIMARY KEY (dataset_id, version)
            );

            CREATE TABLE IF NOT EXISTS territorial_discovery_cache (
                cache_key               TEXT PRIMARY KEY,
                source_name             TEXT NOT NULL,
                payload_json            TEXT NOT NULL,
                updated_at              REAL NOT NULL,
                ttl_sec                 REAL NOT NULL DEFAULT 86400.0
            );

            CREATE TABLE IF NOT EXISTS synthetic_population_batches (
                batch_id                TEXT PRIMARY KEY,
                district_id             TEXT NOT NULL,
                seed                    INTEGER NOT NULL,
                represented_population  INTEGER NOT NULL,
                represented_households  INTEGER NOT NULL,
                calibration_status      TEXT NOT NULL,
                srmse                   REAL NOT NULL,
                certificate_json        TEXT NOT NULL DEFAULT '{}',
                batch_summary_json      TEXT NOT NULL DEFAULT '{}',
                created_at              REAL NOT NULL
            );
            """
        )
        c.execute(
            "INSERT OR REPLACE INTO studio_schema_meta (meta_key, meta_value, updated_at) VALUES (?, ?, ?)",
            ("phase_117_schema_version", "2", time.time()),
        )
        c.execute(
            "INSERT OR REPLACE INTO studio_schema_meta (meta_key, meta_value, updated_at) VALUES (?, ?, ?)",
            ("phase_118_schema_version", "3", time.time()),
        )
        c.commit()

    def save_session(self, session: ConversationSessionState) -> None:
        now = time.time()
        if session.created_at <= 0:
            session.created_at = now
        session.updated_at = now

        coords_json = json.dumps(list(session.active_coordinates) if session.active_coordinates else None)
        interv_json = (
            session.active_intervention.model_dump_json()
            if session.active_intervention is not None
            else "null"
        )
        temp_json = (
            session.active_temporal_horizon.model_dump_json()
            if session.active_temporal_horizon is not None
            else "null"
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO conv_sessions (
                    conversation_id, active_scenario_id, active_district_id,
                    active_location_query, active_coordinates_json,
                    active_intervention_json, active_temporal_json,
                    scenario_ids_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    active_scenario_id=excluded.active_scenario_id,
                    active_district_id=excluded.active_district_id,
                    active_location_query=excluded.active_location_query,
                    active_coordinates_json=excluded.active_coordinates_json,
                    active_intervention_json=excluded.active_intervention_json,
                    active_temporal_json=excluded.active_temporal_json,
                    scenario_ids_json=excluded.scenario_ids_json,
                    updated_at=excluded.updated_at
                """,
                (
                    session.conversation_id,
                    session.active_scenario_id,
                    session.active_district_id,
                    session.active_location_query,
                    coords_json,
                    interv_json,
                    temp_json,
                    json.dumps(session.scenario_ids),
                    session.created_at,
                    session.updated_at,
                ),
            )

    def append_turn(self, conversation_id: str, turn: ConversationTurn) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO conv_turns (
                    conversation_id, turn_index, role, message, timestamp, stage, scenario_id, intent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    turn.turn_index,
                    turn.role,
                    turn.message,
                    turn.timestamp,
                    turn.stage.value,
                    turn.scenario_id,
                    turn.intent,
                ),
            )

    def load_session(self, conversation_id: str) -> Optional[ConversationSessionState]:
        row = self.conn.execute(
            "SELECT * FROM conv_sessions WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None

        coords_raw = json.loads(row["active_coordinates_json"])
        coords = (float(coords_raw[0]), float(coords_raw[1])) if isinstance(coords_raw, list) and len(coords_raw) == 2 else None
        interv_raw = json.loads(row["active_intervention_json"])
        interv = InterventionSpec.model_validate(interv_raw) if isinstance(interv_raw, dict) else None
        temp_raw = json.loads(row["active_temporal_json"])
        temp = TemporalHorizonSpec.model_validate(temp_raw) if isinstance(temp_raw, dict) else None

        turn_rows = self.conn.execute(
            "SELECT * FROM conv_turns WHERE conversation_id = ? ORDER BY turn_index ASC, turn_id ASC",
            (conversation_id,),
        ).fetchall()
        turns = [
            ConversationTurn(
                turn_index=int(tr["turn_index"]),
                role=tr["role"],
                message=tr["message"],
                timestamp=float(tr["timestamp"]),
                stage=AnalysisStage(tr["stage"]),
                scenario_id=tr["scenario_id"],
                intent=tr["intent"],
            )
            for tr in turn_rows
        ]
        return ConversationSessionState(
            conversation_id=row["conversation_id"],
            active_scenario_id=row["active_scenario_id"],
            active_district_id=row["active_district_id"],
            active_location_query=row["active_location_query"],
            active_coordinates=coords,
            active_intervention=interv,
            active_temporal_horizon=temp,
            scenario_ids=json.loads(row["scenario_ids_json"] or "[]"),
            turns=turns,
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def save_scenario_definition(
        self,
        scenario_id: str,
        conversation_id: str,
        district_id: str,
        geo_context_summary: Dict[str, Any],
        temporal: TemporalHorizonSpec,
        intervention: Optional[InterventionSpec],
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO conv_scenarios (
                    scenario_id, conversation_id, district_id,
                    geo_context_json, temporal_json, intervention_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    district_id=excluded.district_id,
                    geo_context_json=excluded.geo_context_json,
                    temporal_json=excluded.temporal_json,
                    intervention_json=excluded.intervention_json
                """,
                (
                    scenario_id,
                    conversation_id,
                    district_id,
                    json.dumps(geo_context_summary, ensure_ascii=False),
                    temporal.model_dump_json(),
                    intervention.model_dump_json() if intervention else "null",
                    time.time(),
                ),
            )

    def save_execution_record(
        self,
        execution_id: str,
        conversation_id: str,
        scenario_id: str,
        seed: int,
        evidence: EvidenceBundle,
        recommendation: DecisionRecommendation,
        provenance_record: Dict[str, Any],
        checkpoint_id: Optional[str] = None,
    ) -> None:
        # Store compact indicator summary & entity references instead of duplicating large tick logs
        compact_evidence_ref = {
            "scenario_id": evidence.scenario_id,
            "seed": evidence.seed,
            "horizon_days": evidence.horizon_days,
            "simulated_ticks": evidence.simulated_ticks,
            "district_id": evidence.district_id,
            "active_engines": evidence.active_engines,
            "ledger_audit": evidence.ledger_audit,
            "indicator_values": {
                ind.indicator_id: ind.value for ind in evidence.indicators if ind.available
            },
            "missing_indicators": evidence.missing_indicators,
        }
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO conv_executions (
                    execution_id, conversation_id, scenario_id, seed,
                    active_engines_json, evidence_ref_json, analysis_json,
                    provenance_json, checkpoint_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    conversation_id,
                    scenario_id,
                    seed,
                    json.dumps(evidence.active_engines),
                    json.dumps(compact_evidence_ref, ensure_ascii=False),
                    recommendation.model_dump_json(),
                    json.dumps(provenance_record, ensure_ascii=False),
                    checkpoint_id,
                    time.time(),
                ),
            )

    def save_checkpoint(
        self,
        checkpoint_id: str,
        scenario_id: str,
        seed: int,
        completed_steps: int,
        total_steps: int,
        simulated_days: float,
        state_summary: Dict[str, Any],
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO conv_checkpoints (
                    checkpoint_id, scenario_id, seed, completed_steps,
                    total_steps, simulated_days, state_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkpoint_id) DO UPDATE SET
                    completed_steps=excluded.completed_steps,
                    simulated_days=excluded.simulated_days,
                    state_json=excluded.state_json
                """,
                (
                    checkpoint_id,
                    scenario_id,
                    seed,
                    completed_steps,
                    total_steps,
                    simulated_days,
                    json.dumps(state_summary, ensure_ascii=False),
                    time.time(),
                ),
            )

    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM conv_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "checkpoint_id": row["checkpoint_id"],
            "scenario_id": row["scenario_id"],
            "seed": int(row["seed"]),
            "completed_steps": int(row["completed_steps"]),
            "total_steps": int(row["total_steps"]),
            "simulated_days": float(row["simulated_days"]),
            "state_summary": json.loads(row["state_json"] or "{}"),
        }

    def list_executions_for_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM conv_executions WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [
            {
                "execution_id": r["execution_id"],
                "scenario_id": r["scenario_id"],
                "seed": int(r["seed"]),
                "active_engines": json.loads(r["active_engines_json"]),
                "evidence_ref": json.loads(r["evidence_ref_json"]),
                "analysis": json.loads(r["analysis_json"]),
                "provenance": json.loads(r["provenance_json"]),
                "checkpoint_id": r["checkpoint_id"],
                "created_at": float(r["created_at"]),
            }
            for r in rows
        ]

    def get_execution_by_id(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single persisted execution record by execution_id."""
        r = self.conn.execute(
            "SELECT * FROM conv_executions WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
        if r is None:
            return None
        return {
            "execution_id": r["execution_id"],
            "conversation_id": r["conversation_id"],
            "scenario_id": r["scenario_id"],
            "seed": int(r["seed"]),
            "active_engines": json.loads(r["active_engines_json"]),
            "evidence_ref": json.loads(r["evidence_ref_json"]),
            "analysis": json.loads(r["analysis_json"]),
            "provenance": json.loads(r["provenance_json"]),
            "checkpoint_id": r["checkpoint_id"],
            "created_at": float(r["created_at"]),
        }

    def get_scenario_by_id(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single persisted scenario definition by scenario_id."""
        r = self.conn.execute(
            "SELECT * FROM conv_scenarios WHERE scenario_id = ?",
            (scenario_id,),
        ).fetchone()
        if r is None:
            return None
        return {
            "scenario_id": r["scenario_id"],
            "conversation_id": r["conversation_id"],
            "district_id": r["district_id"],
            "geo_context_summary": json.loads(r["geo_context_json"] or "{}"),
            "temporal": json.loads(r["temporal_json"] or "{}"),
            "intervention": json.loads(r["intervention_json"] or "null"),
            "created_at": float(r["created_at"]),
        }

    def list_sessions(self, limit: int = 30) -> List[Dict[str, Any]]:
        """List recent conversations with summary titles and execution counts."""
        rows = self.conn.execute(
            "SELECT * FROM conv_sessions ORDER BY updated_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        sessions_out: List[Dict[str, Any]] = []
        for r in rows:
            cid = r["conversation_id"]
            first_turn = self.conn.execute(
                "SELECT message FROM conv_turns WHERE conversation_id = ? AND role = 'user' ORDER BY turn_index ASC LIMIT 1",
                (cid,),
            ).fetchone()
            turn_cnt = self.conn.execute(
                "SELECT COUNT(*) FROM conv_turns WHERE conversation_id = ?",
                (cid,),
            ).fetchone()[0]
            exec_cnt = self.conn.execute(
                "SELECT COUNT(*) FROM conv_executions WHERE conversation_id = ?",
                (cid,),
            ).fetchone()[0]
            title_raw = first_turn["message"] if first_turn else (r["active_location_query"] or cid)
            title = (title_raw[:68] + "…") if len(title_raw) > 68 else title_raw
            sessions_out.append(
                {
                    "conversation_id": cid,
                    "title": title,
                    "active_scenario_id": r["active_scenario_id"],
                    "active_district_id": r["active_district_id"],
                    "active_location_query": r["active_location_query"],
                    "scenario_ids": json.loads(r["scenario_ids_json"] or "[]"),
                    "turn_count": int(turn_cnt),
                    "execution_count": int(exec_cnt),
                    "created_at": float(r["created_at"]),
                    "updated_at": float(r["updated_at"]),
                }
            )
        return sessions_out

    # ------------------------------------------------------------------
    # Phase 1.17 Territorial Scenario, Evidence A–G & Population Persistence
    # ------------------------------------------------------------------

    def save_territorial_scenario(self, record: Any) -> None:
        """Persist OnDemandScenarioRecord and its A–G evidence package if present."""
        now = time.time()
        loc = record.resolved_location or {}
        catch_json = record.catchment.model_dump_json() if record.catchment is not None else "{}"
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO territorial_scenarios (
                    scenario_id, state, state_history_json, location_query, district_id,
                    department_code, lat, lon, catchment_json, seed, parameters_json,
                    provenance_json, is_historic_benchmark, record_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    state=excluded.state,
                    state_history_json=excluded.state_history_json,
                    district_id=excluded.district_id,
                    department_code=excluded.department_code,
                    lat=excluded.lat,
                    lon=excluded.lon,
                    catchment_json=excluded.catchment_json,
                    provenance_json=excluded.provenance_json,
                    record_json=excluded.record_json,
                    updated_at=excluded.updated_at
                """,
                (
                    record.scenario_id,
                    record.state.value,
                    json.dumps([h.model_dump(mode="json") for h in record.state_history], ensure_ascii=False),
                    record.query,
                    loc.get("district_id"),
                    loc.get("department_code"),
                    loc.get("lat"),
                    loc.get("lon"),
                    catch_json,
                    record.seed,
                    json.dumps(record.parameters, ensure_ascii=False),
                    json.dumps(record.provenance, ensure_ascii=False),
                    1 if record.is_historic_center_benchmark else 0,
                    record.model_dump_json(),
                    record.created_at or now,
                    now,
                ),
            )
            if record.evidence_package is not None:
                pkg = record.evidence_package
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO territorial_evidence_packages (
                        package_id, scenario_id, seed, tier_a_json, tier_b_json, tier_c_json,
                        tier_d_json, tier_e_json, tier_f_json, tier_g_json, summary_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pkg.package_id,
                        record.scenario_id,
                        pkg.seed,
                        json.dumps([i.model_dump(mode="json") for i in pkg.A_real_observed_data], ensure_ascii=False),
                        json.dumps([i.model_dump(mode="json") for i in pkg.B_official_statistical_estimates], ensure_ascii=False),
                        json.dumps([i.model_dump(mode="json") for i in pkg.C_geographic_derivations], ensure_ascii=False),
                        json.dumps([i.model_dump(mode="json") for i in pkg.D_synthetic_population_characteristics], ensure_ascii=False),
                        json.dumps([i.model_dump(mode="json") for i in pkg.E_simulated_outcomes], ensure_ascii=False),
                        json.dumps(pkg.F_ai_interpretations_and_hypotheses, ensure_ascii=False),
                        json.dumps(pkg.G_recommendations, ensure_ascii=False),
                        json.dumps(
                            {
                                "geographic_scope": pkg.geographic_scope,
                                "population_scope": pkg.population_scope,
                                "time_interval": pkg.time_interval,
                                "ai_provider_used": pkg.ai_provider_used,
                                "ai_model_used": pkg.ai_model_used,
                                "limitations": pkg.limitations,
                            },
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
            self.conn.commit()

    def load_territorial_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT record_json FROM territorial_scenarios WHERE scenario_id = ?",
            (scenario_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["record_json"])

    def save_population_assignments(self, assignments: List[Dict[str, Any]]) -> None:
        if not assignments:
            return
        now = time.time()
        with self._lock:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO persistent_population_assignments (
                    uid, home_district_id, current_district_id, household_id, lat, lon,
                    residential_building_id, state_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        a["uid"],
                        a["home_district_id"],
                        a["current_district_id"],
                        a["household_id"],
                        float(a["lat"]),
                        float(a["lon"]),
                        a.get("residential_building_id"),
                        json.dumps(a, ensure_ascii=False),
                        now,
                    )
                    for a in assignments
                ],
            )
            self.conn.commit()

    def count_population_assignments(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM persistent_population_assignments").fetchone()
        return int(row[0]) if row else 0

    def save_census_dataset_meta(self, meta: Any) -> None:
        now = time.time()
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO census_datasets_registry (
                    dataset_id, version, adapter_name, published_at, content_sha256, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta.dataset_id,
                    meta.version,
                    meta.adapter_name,
                    meta.published_at,
                    meta.content_sha256,
                    meta.model_dump_json(),
                    now,
                ),
            )
            self.conn.commit()

    def save_synthetic_population_batch(self, prep_result: Any) -> None:
        now = time.time()
        batch = prep_result.population_batch
        cert = prep_result.certificate
        cal = prep_result.calibration
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO synthetic_population_batches (
                    batch_id, district_id, seed, represented_population, represented_households,
                    calibration_status, srmse, certificate_json, batch_summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.batch_id,
                    batch.district_id,
                    int(batch.seed),
                    int(batch.represented_population_total),
                    int(batch.represented_households_total),
                    cert.calibration_status,
                    float(cal.srmse),
                    cert.model_dump_json(),
                    json.dumps(
                        {
                            "area_label": batch.area_label,
                            "generation_scale": batch.generation_scale,
                            "simulated_sample_households": batch.simulated_sample_households,
                            "simulated_sample_persons": batch.simulated_sample_persons,
                            "is_weighted_cohort": batch.is_weighted_cohort,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )
            self.conn.commit()

    def count_synthetic_population_batches(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM synthetic_population_batches").fetchone()
        return int(row[0]) if row else 0
