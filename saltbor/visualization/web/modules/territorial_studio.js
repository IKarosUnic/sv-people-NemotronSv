/**
 * SALTBOR Phase 1.16B — TerritorialSimulationStudio (Vanilla ES6 Module)
 * Chat-First Conversational Territorial Intelligence Workspace & Optional National Map.
 */

const WELCOME_TEXT =
    "Hola. Soy SALTBOR, tu asistente de inteligencia territorial. " +
    "Puedes preguntarme sobre cualquier lugar de El Salvador, analizar necesidades, " +
    "proponer negocios, evaluar proyectos o simular cambios sociales y económicos.";

const STARTER_PROMPTS = [
    "Quiero abrir un negocio en Santa Tecla.",
    "¿Hace falta una escuela en esta comunidad?",
    "Analiza la actividad comercial de San Miguel.",
    "¿Dónde sería conveniente construir una farmacia?",
    "¿Qué pasa si se bloquea esta carretera?",
    "Compara dos ubicaciones para una pupusería.",
    "Analiza la demanda de transporte en esta zona.",
];

const VERDICT_META = {
    PROMISING: { label: "PROMETEDOR", cls: "real" },
    CONDITIONALLY_PROMISING: { label: "CONDICIONALMENTE PROMETEDOR", cls: "warn" },
    INSUFFICIENT_EVIDENCE: { label: "EVIDENCIA INSUFICIENTE", cls: "warn" },
    HIGH_RISK: { label: "ALTO RIESGO", cls: "risk" },
    NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS: { label: "NO RECOMENDADO BAJO SUPUESTOS ACTUALES", cls: "risk" },
};

const PROVIDER_STATUS_LABELS = {
    CONNECTED: "Gemini conectado",
    NOT_CONFIGURED: "Gemini no configurado",
    QUOTA_EXCEEDED: "Cuota de Gemini excedida",
    RATE_LIMITED: "Límite de tasa alcanzado",
    UNAVAILABLE: "Proveedor no disponible",
    LOCAL_PROVIDER_ACTIVE: "Proveedor local Ollama activo",
    OFFLINE_MODE: "Modo Offline activo",
};

function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

export class TerritorialSimulationStudio {
    constructor() {
        this.conversationId = null;
        this.activeScenarioId = null;
        this.activeContext = null;
        this.activeCoordinates = null;
        this.mapMode = "hidden"; // hidden | side | expanded | full
        this.isPickingMapPoint = false;
        this.activeJobId = null;
        this.pollTimer = null;
        this.lastResult = null;
        this.activeReportLevel = "BASIC";
        this.turns = [];
        this.isDrawingPolygon = false;
        this.drawnVertices = [];
        this.activePolygonGeoJSON = null;
        this.lastDiscovery = null;
        this.maxExpansionMinutes = 30;

        this.bindElements();
        if (this.shell && window.innerWidth <= 1024) {
            this.shell.classList.add("history-collapsed");
        }
        this.renderWelcome();
        this.bindEvents();
        this.refreshConversationsList();
        this.refreshProviderStatus();
    }

    bindElements() {
        this.shell = document.getElementById("studio-shell");
        this.thread = document.getElementById("studio-thread");
        this.scrollBox = document.getElementById("studio-messages-scroll");
        this.historyList = document.getElementById("studio-history-list");
        this.input = document.getElementById("studio-chat-input");
        this.btnSend = document.getElementById("studio-btn-send");
        this.btnNewChat = document.getElementById("studio-btn-new-chat");
        this.btnToggleHistory = document.getElementById("studio-btn-toggle-history");
        this.locationSearch = document.getElementById("studio-location-search");
        this.autocompleteMenu = document.getElementById("studio-location-autocomplete");
        this.btnAttachMapPoint = document.getElementById("studio-btn-pick-point");
        this.btnClearPoint = document.getElementById("studio-btn-clear-point");
        this.btnToggleAdvanced = document.getElementById("studio-btn-toggle-advanced");
        this.advancedRow = document.getElementById("studio-advanced-row");
        this.daysOverrideInput = document.getElementById("studio-days-override");
        this.contextPill = document.getElementById("studio-active-context-pill");
        this.providerPill = document.getElementById("studio-provider-pill");
        this.progressBanner = document.getElementById("studio-progress-banner");
        this.progressText = document.getElementById("studio-progress-text");
        this.btnCancelJob = document.getElementById("studio-btn-cancel-job");
        this.btnExportReport = document.getElementById("studio-btn-export-report");

        // Map drawer controls
        this.mapHost = document.getElementById("studio-map-canvas-host");
        this.mapCoordsLabel = document.getElementById("studio-map-coords-label");
        this.btnMapModeHidden = document.getElementById("studio-map-mode-hidden");
        this.btnMapModeSide = document.getElementById("studio-map-mode-side");
        this.btnMapModeExpanded = document.getElementById("studio-map-mode-expanded");
        this.btnMapModeFull = document.getElementById("studio-map-mode-full");
        this.btnHeaderToggleMap = document.getElementById("studio-btn-toggle-map");

        // Phase 1.18 Territorial Explorer controls
        this.btnDrawPolygon = document.getElementById("studio-btn-draw-polygon");
        this.btnFinishPolygon = document.getElementById("studio-btn-finish-polygon");
        this.btnClearPolygon = document.getElementById("studio-btn-clear-polygon");
        this.travelTimeSelect = document.getElementById("studio-travel-time-select");
        this.travelTimeCustom = document.getElementById("studio-travel-time-custom");
        this.sectorSelect = document.getElementById("studio-sector-select");
        this.btnDiscoverTerritory = document.getElementById("studio-btn-discover-territory");
        this.btnExpandArea = document.getElementById("studio-btn-expand-area");
        this.explorerInspector = document.getElementById("studio-explorer-inspector");

        // Settings modal
        this.settingsModal = document.getElementById("studio-settings-modal");
        this.btnOpenSettings = document.getElementById("btn-open-studio-settings");
        this.btnCloseSettings = document.getElementById("studio-settings-close");
        this.settingsModeSelect = document.getElementById("studio-setting-provider-mode");
        this.settingsKeyInput = document.getElementById("studio-setting-gemini-key");
        this.settingsKeyMasked = document.getElementById("studio-setting-key-masked");
        this.settingsFlashModel = document.getElementById("studio-setting-flash-model");
        this.settingsFlashLiteModel = document.getElementById("studio-setting-flash-lite-model");
        this.settingsOllamaModel = document.getElementById("studio-setting-ollama-model");
        this.settingsStrictPrivacy = document.getElementById("studio-setting-strict-privacy");
        this.settingsStatusText = document.getElementById("studio-setting-status-text");
        this.btnSaveSettings = document.getElementById("studio-settings-save");
        this.btnClearKey = document.getElementById("studio-settings-clear-key");
    }

    bindEvents() {
        if (!this.shell) return;

        this.btnSend?.addEventListener("click", () => this.handleSend());
        this.input?.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                this.handleSend();
            }
        });

        this.btnNewChat?.addEventListener("click", () => this.startNewConversation());
        this.btnToggleHistory?.addEventListener("click", () => {
            this.shell.classList.toggle("history-collapsed");
        });

        this.btnToggleAdvanced?.addEventListener("click", () => {
            this.advancedRow?.classList.toggle("open");
        });

        this.btnCancelJob?.addEventListener("click", () => this.cancelActiveJob());
        this.btnExportReport?.addEventListener("click", () => this.exportMarkdownReport());

        // Location search autocomplete (works even with map hidden)
        let searchTimer = null;
        this.locationSearch?.addEventListener("input", () => {
            clearTimeout(searchTimer);
            const q = this.locationSearch.value.trim();
            if (!q) {
                this.autocompleteMenu?.classList.remove("open");
                return;
            }
            searchTimer = setTimeout(() => this.performLocationSearch(q), 180);
        });
        document.addEventListener("click", (e) => {
            if (this.autocompleteMenu && !this.autocompleteMenu.contains(e.target) && e.target !== this.locationSearch) {
                this.autocompleteMenu.classList.remove("open");
            }
        });

        this.btnAttachMapPoint?.addEventListener("click", () => {
            if (this.mapMode === "hidden") this.setMapMode("side");
            this.isPickingMapPoint = !this.isPickingMapPoint;
            this.btnAttachMapPoint.classList.toggle("btn-primary", this.isPickingMapPoint);
            this.btnAttachMapPoint.classList.toggle("btn-secondary", !this.isPickingMapPoint);
            if (this.mapCoordsLabel && this.isPickingMapPoint) {
                this.mapCoordsLabel.textContent = "Haz clic en cualquier lugar del mapa de El Salvador para fijar el punto.";
            }
        });

        this.btnClearPoint?.addEventListener("click", () => {
            this.activeCoordinates = null;
            this.btnClearPoint.style.display = "none";
            this.updateContextPill();
        });

        // Map mode controls
        this.btnHeaderToggleMap?.addEventListener("click", () => {
            this.setMapMode(this.mapMode === "hidden" ? "side" : "hidden");
        });
        this.btnMapModeHidden?.addEventListener("click", () => this.setMapMode("hidden"));
        this.btnMapModeSide?.addEventListener("click", () => this.setMapMode("side"));
        this.btnMapModeExpanded?.addEventListener("click", () => this.setMapMode("expanded"));
        this.btnMapModeFull?.addEventListener("click", () => this.setMapMode("full"));

        // Phase 1.18 Interactive Territorial Explorer events
        this.btnDrawPolygon?.addEventListener("click", () => this.togglePolygonDraw(true));
        this.btnFinishPolygon?.addEventListener("click", () => this.finishPolygonDraw());
        this.btnClearPolygon?.addEventListener("click", () => this.clearDrawnPolygon());
        this.travelTimeSelect?.addEventListener("change", () => {
            if (this.travelTimeCustom) {
                this.travelTimeCustom.style.display = this.travelTimeSelect.value === "custom" ? "inline-block" : "none";
            }
        });
        this.btnDiscoverTerritory?.addEventListener("click", () => this.runTerritorialDiscovery());
        this.btnExpandArea?.addEventListener("click", () => {
            this.maxExpansionMinutes = Math.min(90, (this.maxExpansionMinutes || 30) + 10);
            this.runTerritorialDiscovery();
        });
        document.querySelectorAll("[data-studio-layer]").forEach((chk) => {
            chk.addEventListener("change", () => this.applyDiscoveryLayerVisibility());
        });

        document.getElementById("btn-return-to-studio")?.addEventListener("click", () => {
            this.restoreWorldMapContainer();
            if (typeof window.switchView === "function") window.switchView("studio");
            this.setMapMode("side");
        });

        window.addEventListener("saltbor:restore-world-map", () => {
            this.restoreWorldMapContainer();
        });

        // Settings modal
        this.providerPill?.addEventListener("click", () => this.openSettingsModal());
        this.btnOpenSettings?.addEventListener("click", () => this.openSettingsModal());
        this.btnCloseSettings?.addEventListener("click", () => this.closeSettingsModal());
        this.settingsModal?.addEventListener("click", (e) => {
            if (e.target === this.settingsModal) this.closeSettingsModal();
        });
        this.btnSaveSettings?.addEventListener("click", () => this.saveProviderSettings());
        this.btnClearKey?.addEventListener("click", () => this.clearGeminiKey());

        // Mobile sidebar button
        const mobileNavBtn = document.getElementById("btn-mobile-nav");
        mobileNavBtn?.addEventListener("click", () => {
            document.getElementById("sidebar")?.classList.toggle("mobile-open");
        });
        document.querySelectorAll("#sidebar .nav-item").forEach((it) => {
            it.addEventListener("click", () => {
                document.getElementById("sidebar")?.classList.remove("mobile-open");
            });
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth <= 1024) {
                this.shell?.classList.add("history-collapsed");
            }
            const map = window.saltborState?.gisMap;
            if (map && this.mapMode !== "hidden") map.resize();
        });
    }

    renderWelcome() {
        if (!this.thread) return;
        this.thread.innerHTML = "";
        const card = document.createElement("div");
        card.className = "studio-welcome";
        card.id = "studio-welcome-card";
        card.innerHTML = `
            <span class="studio-welcome-badge">🇸🇻 Cobertura Nacional · 14 Departamentos · 262 Distritos</span>
            <h1>Estudio Conversacional de Inteligencia Territorial</h1>
            <p class="studio-welcome-lead">${escapeHtml(WELCOME_TEXT)}</p>
            <div class="studio-starter-grid">
                ${STARTER_PROMPTS.map(
                    (p) => `<button type="button" class="studio-chip" data-starter="${escapeHtml(p)}">${escapeHtml(p)}</button>`
                ).join("")}
            </div>
        `;
        card.querySelectorAll("[data-starter]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const text = btn.getAttribute("data-starter");
                if (this.input && text) {
                    this.input.value = text;
                    this.handleSend();
                }
            });
        });
        this.thread.appendChild(card);
    }

    startNewConversation() {
        this.stopPolling();
        this.conversationId = null;
        this.activeScenarioId = null;
        this.activeContext = null;
        this.activeCoordinates = null;
        this.lastResult = null;
        this.activeReportLevel = "BASIC";
        this.turns = [];
        this.isDrawingPolygon = false;
        this.drawnVertices = [];
        this.activePolygonGeoJSON = null;
        this.lastDiscovery = null;
        this.maxExpansionMinutes = 30;
        if (this.btnClearPoint) this.btnClearPoint.style.display = "none";
        if (this.btnExportReport) this.btnExportReport.style.display = "none";
        this.updateContextPill();
        this.renderWelcome();
        this.refreshConversationsList();
    }

    updateContextPill() {
        if (!this.contextPill) return;
        const parts = [];
        if (this.activeContext?.district_name) {
            parts.push(`📍 ${this.activeContext.district_name}, ${this.activeContext.department_name}`);
        }
        if (this.activeCoordinates) {
            parts.push(`(${this.activeCoordinates.lat.toFixed(4)}, ${this.activeCoordinates.lon.toFixed(4)})`);
        }
        this.contextPill.textContent = parts.length ? parts.join(" · ") : "📍 Sin ubicación fijada (puedes escribirla en el chat)";
    }

    scrollToBottom() {
        if (this.scrollBox) {
            this.scrollBox.scrollTop = this.scrollBox.scrollHeight;
        }
    }

    appendUserMessage(text) {
        document.getElementById("studio-welcome-card")?.remove();
        const wrap = document.createElement("div");
        wrap.className = "studio-msg user";
        wrap.innerHTML = `<div class="studio-msg-bubble">${escapeHtml(text)}</div>`;
        this.thread.appendChild(wrap);
        this.turns.push({ role: "user", message: text });
        this.scrollToBottom();
    }

    appendErrorMessage(msg) {
        const wrap = document.createElement("div");
        wrap.className = "studio-msg assistant";
        wrap.innerHTML = `
            <div class="studio-msg-role">SALTBOR · Error controlado</div>
            <div class="studio-msg-bubble">
                <div class="studio-card" style="border-color: var(--accent-rose);">
                    <div class="studio-card-title">⚠️ No se pudo completar la operación</div>
                    <p style="font-size:12.5px; color: var(--text-secondary);">${escapeHtml(msg)}</p>
                </div>
            </div>
        `;
        this.thread.appendChild(wrap);
        this.scrollToBottom();
    }

    async handleSend(overrideMessage = null) {
        const message = (overrideMessage !== null ? overrideMessage : this.input?.value || "").trim();
        if (!message) return;

        if (overrideMessage === null && this.input) {
            this.input.value = "";
        }
        this.appendUserMessage(message);

        const daysVal = this.daysOverrideInput?.value ? parseInt(this.daysOverrideInput.value, 10) : null;
        const payload = {
            message,
            conversation_id: this.conversationId,
            lat: this.activeCoordinates ? this.activeCoordinates.lat : null,
            lon: this.activeCoordinates ? this.activeCoordinates.lon : null,
            map_visible: this.mapMode !== "hidden",
            auto_execute: false,
            temporal_days_override: Number.isFinite(daysVal) && daysVal > 0 ? daysVal : null,
        };

        this.showProgress("ANALYZING_REQUEST", "Comprendiendo solicitud y resolviendo contexto territorial...", false);
        try {
            const res = await fetch("/api/studio/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.hideProgress();

            this.conversationId = data.conversation_id;
            this.activeScenarioId = data.scenario_id;
            if (data.territorial_context?.resolved) {
                this.activeContext = data.territorial_context;
                this.activeIntelligence = data.territorial_intelligence || null;
                this.updateContextPill();
                if (this.mapMode !== "hidden") {
                    this.syncMapToContext(this.activeContext, this.activeIntelligence);
                }
            }
            this.renderStageAAssessment(data);
            this.refreshConversationsList();
        } catch (err) {
            this.hideProgress();
            this.appendErrorMessage(err.message || "Fallo de comunicación con el servidor.");
        }
    }

    renderStageAAssessment(data) {
        const ctx = data.territorial_context || {};
        const interv = data.proposed_intervention;
        const temp = data.temporal_horizon || {};
        const pop = data.population_context || {};
        const comp = data.computational_estimate || {};

        const wrap = document.createElement("div");
        wrap.className = "studio-msg assistant";

        const locBadge = ctx.resolved
            ? `<span class="studio-badge real">UBICACIÓN RESUELTA</span>`
            : `<span class="studio-badge warn">${ctx.is_ambiguous ? "ACLARACIÓN REQUERIDA" : "UBICACIÓN PENDIENTE"}</span>`;

        const candidateChips = (ctx.candidates || []).length
            ? `<div class="studio-actions-row" style="margin-top:8px;">
                ${ctx.candidates
                    .map(
                        (c) =>
                            `<button type="button" class="studio-chip" data-clarify="${escapeHtml(c.matched_label + ", " + c.department_name)}">📍 ${escapeHtml(c.matched_label)} (${escapeHtml(c.department_name)})</button>`
                    )
                    .join("")}
               </div>`
            : "";

        const actionButtons = data.ready_to_execute
            ? `<div class="studio-actions-row">
                <button type="button" class="btn btn-primary btn-sm studio-btn-touch" data-run-stage-b="${escapeHtml(data.scenario_id)}" data-compare="false">
                    ▶ Ejecutar Simulación (${escapeHtml(temp.horizon_days || 30)} días)
                </button>
                <button type="button" class="btn btn-secondary btn-sm studio-btn-touch" data-run-stage-b="${escapeHtml(data.scenario_id)}" data-compare="true">
                    ⚖️ Simular y Comparar Alternativas
                </button>
                <button type="button" class="btn btn-secondary btn-sm studio-btn-touch" data-open-map-ctx="true">
                    🗺️ Ver Contexto en Mapa
                </button>
               </div>`
            : "";

        const ti = data.territorial_intelligence || {};
        const tiBldg = ti.buildings || {};
        const tiComm = ti.commerce || {};
        const tiCatch = ti.catchment || {};
        const tiEmp = ti.employment || {};
        const tiHtml = ti.catchment
            ? `<div style="margin-top:8px; padding:8px 10px; border-radius:8px; background:var(--bg-elevated); border:1px solid var(--border-subtle); font-size:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <strong>🏗️ Entorno Edificado, Comercio y Área de Influencia</strong>
                    <span class="studio-badge info">Cobertura ${escapeHtml(ti.coverage_tier || "PARTIAL")}</span>
                </div>
                <div style="color:var(--text-secondary); line-height:1.5;">
                    Edificios OSM: <strong>${escapeHtml(tiBldg.total_observed ?? 0)}</strong> ·
                    Negocios confirmados: <strong>${escapeHtml(tiComm.confirmed_establishments ?? 0)}</strong>
                    (edificios comerciales sin verificar: ${escapeHtml(tiComm.unverified_commercial_buildings ?? 0)}) ·
                    Área influencia: <strong>${escapeHtml(tiCatch.effective_area_km2 ?? 0)} km²</strong> (${escapeHtml(tiCatch.method || "adaptive")}) ·
                    Vacantes verificadas: <strong>${escapeHtml(tiEmp.verified_job_vacancies_count ?? 0)}</strong> / Empleadores conocidos: <strong>${escapeHtml(tiEmp.known_employers_count ?? 0)}</strong>
                </div>
               </div>`
            : "";

        const missingItems = (data.missing_data || []).map((m) => `<li>${escapeHtml(m)}</li>`).join("");

        wrap.innerHTML = `
            <div class="studio-msg-role">SALTBOR · Evaluación Preliminar (Etapa A — Sin simular aún)</div>
            <div class="studio-msg-bubble">
                <p>${escapeHtml(data.assistant_reply)}</p>
                <div class="studio-card">
                    <div class="studio-card-header">
                        <span class="studio-card-title">📋 Contexto Territorial y Propuesta</span>
                        ${locBadge}
                    </div>
                    <div class="studio-kpi-grid">
                        <div class="studio-kpi">
                            <span class="studio-kpi-label">Ubicación</span>
                            <span class="studio-kpi-value">${escapeHtml(ctx.resolved ? `${ctx.district_name}, ${ctx.department_name}` : ctx.query || "Por definir")}</span>
                        </div>
                        <div class="studio-kpi">
                            <span class="studio-kpi-label">Intervención</span>
                            <span class="studio-kpi-value">${escapeHtml(interv ? `${interv.name} ($${Number(interv.unit_price_usd || 0).toFixed(2)}, ${interv.workforce_count} pers.)` : "Análisis territorial")}</span>
                        </div>
                        <div class="studio-kpi">
                            <span class="studio-kpi-label">Horizonte Recomendado</span>
                            <span class="studio-kpi-value">${escapeHtml(`${temp.horizon_days || 30} días (${temp.resolution_mode || "HYBRID"})`)}</span>
                        </div>
                        <div class="studio-kpi">
                            <span class="studio-kpi-label">Calidad por Pregunta</span>
                            <span class="studio-kpi-value">${ctx.resolved ? `${Math.round(((ctx.question_data_quality?.confidence_score ?? ctx.data_quality_score) || 0) * 100)}% · Pobl. ~${Number(ctx.approx_population || 0).toLocaleString()}` : "N/D"}</span>
                        </div>
                    </div>
                    ${ctx.question_data_quality ? `<div style="font-size:11.5px; color:var(--text-secondary); margin-top:4px;">${escapeHtml(ctx.question_data_quality.summary || "")}</div>` : ""}
                    ${tiHtml}
                    ${pop.estimation_method ? `<div style="font-size:11.5px; color:var(--text-muted);">Motores a activar: ${escapeHtml((data.required_engines || []).join(", "))} · Agentes propuestos: ${escapeHtml(comp.recommended_active_agents || 40)}</div>` : ""}
                    ${missingItems ? `<details class="studio-details"><summary>⚠️ Datos faltantes o cobertura parcial (${data.missing_data.length})</summary><ul class="studio-list">${missingItems}</ul></details>` : ""}
                    ${candidateChips}
                    ${actionButtons}
                </div>
            </div>
        `;

        wrap.querySelectorAll("[data-clarify]").forEach((btn) => {
            btn.addEventListener("click", () => this.handleSend(btn.getAttribute("data-clarify")));
        });
        wrap.querySelectorAll("[data-run-stage-b]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const sid = btn.getAttribute("data-run-stage-b");
                const cmp = btn.getAttribute("data-compare") === "true";
                this.executeStageB(sid, cmp);
            });
        });
        wrap.querySelector("[data-open-map-ctx]")?.addEventListener("click", () => {
            if (ctx.resolved) this.activeContext = ctx;
            this.setMapMode("side");
            if (this.activeContext) this.syncMapToContext(this.activeContext);
        });

        this.thread.appendChild(wrap);
        this.scrollToBottom();
    }

    async executeStageB(scenarioId, compareAlternatives = false) {
        if (!this.conversationId) return;
        this.showProgress("VALIDATING_SCENARIO", "Iniciando simulación con población sintética...", true);
        try {
            const res = await fetch("/api/studio/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    conversation_id: this.conversationId,
                    scenario_id: scenarioId,
                    seed: 42,
                    compare_alternatives: compareAlternatives,
                    max_active_agents: 40,
                    map_visible: this.mapMode !== "hidden",
                    run_in_background: true,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const started = await res.json();
            this.activeJobId = started.job_id;
            this.pollJobStatus(started.job_id);
        } catch (err) {
            this.hideProgress();
            this.appendErrorMessage(`Error iniciando simulación: ${err.message}`);
        }
    }

    pollJobStatus(jobId) {
        this.stopPolling();
        const pollOnce = async () => {
            try {
                const res = await fetch(`/api/studio/jobs/${encodeURIComponent(jobId)}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const job = await res.json();

                this.showProgress(job.stage_code || "RUNNING", job.stage_label || "Procesando simulación...", job.status === "RUNNING");

                if (job.status === "COMPLETED" && job.result) {
                    this.stopPolling();
                    this.hideProgress();
                    this.activeJobId = null;
                    this.lastResult = job.result;
                    if (this.btnExportReport) this.btnExportReport.style.display = "inline-flex";
                    this.renderStageBResult(job.result);
                    this.refreshConversationsList();
                    if (this.mapMode !== "hidden" && job.result.territorial_context) {
                        this.activeIntelligence = job.result.territorial_intelligence || this.activeIntelligence;
                        this.syncMapToContext(job.result.territorial_context, this.activeIntelligence);
                    }
                } else if (job.status === "CANCELLED") {
                    this.stopPolling();
                    this.hideProgress();
                    this.activeJobId = null;
                    this.appendErrorMessage("Simulación cancelada. Los checkpoints previos permanecen guardados.");
                } else if (job.status === "FAILED") {
                    this.stopPolling();
                    this.hideProgress();
                    this.activeJobId = null;
                    this.appendErrorMessage(job.error || "La simulación falló en el motor backend.");
                }
            } catch (err) {
                this.stopPolling();
                this.hideProgress();
                this.appendErrorMessage(`Error consultando estado de simulación: ${err.message}`);
            }
        };

        pollOnce();
        this.pollTimer = setInterval(pollOnce, 350);
    }

    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    async cancelActiveJob() {
        if (!this.activeJobId) return;
        try {
            await fetch(`/api/studio/jobs/${encodeURIComponent(this.activeJobId)}/cancel`, { method: "POST" });
            if (this.progressText) this.progressText.textContent = "Cancelando simulación de forma segura...";
        } catch (err) {
            console.warn("Cancel request error:", err);
        }
    }

    showProgress(stageCode, label, cancellable = false) {
        if (!this.progressBanner) return;
        this.progressBanner.classList.add("active");
        this.progressBanner.dataset.stage = stageCode;
        if (this.progressText) this.progressText.textContent = label;
        if (this.btnCancelJob) this.btnCancelJob.style.display = cancellable ? "inline-flex" : "none";
    }

    hideProgress() {
        this.progressBanner?.classList.remove("active");
    }

    _renderBasicCardHtml(card, fallbackLabel = "") {
        if (!card) return "";
        const origBadge = escapeHtml(card.evidence_origin || "SYNTHETIC_SIMULATED");
        return `
            <div class="studio-basic-metric">
                <div class="studio-ind-top">
                    <span class="studio-kpi-label">${escapeHtml(card.label || fallbackLabel)}</span>
                    <span class="studio-origin-badge" data-origin="${origBadge}">${origBadge}</span>
                </div>
                <div class="studio-kpi-value" style="font-size:16px; margin:2px 0 4px;">${escapeHtml(card.formatted_value)}</div>
                <p style="font-size:12px; color:var(--text-secondary); margin:0; line-height:1.45;">${escapeHtml(card.basic_explanation || "")}</p>
                ${card.not_guaranteed_note ? `<div style="font-size:10.5px; color:var(--text-muted); margin-top:3px;">${escapeHtml(card.not_guaranteed_note)}</div>` : ""}
            </div>`;
    }

    _renderProgressivePanes(prog, rec, ev, ctx, tiBHtml, cmpHtml, indicatorsHtml, opinionsHtml, ledgerOk) {
        const defaultLvl = prog?.default_level || "BASIC";
        const b = prog?.basic || {};
        const inter = prog?.intermediate || {};
        const exp = prog?.expert || {};
        const vMeta = VERDICT_META[rec.verdict] || { label: rec.verdict || "ANALIZADO", cls: "info" };

        const basicHtml = `
            <div class="studio-card">
                <div class="studio-card-header">
                    <span class="studio-card-title">📌 Resumen Sencillo — ¿Qué evaluamos?</span>
                    <span class="studio-badge ${vMeta.cls}">${escapeHtml(b.overall_verdict_plain || vMeta.label)}</span>
                </div>
                <div class="studio-kpi-grid">
                    <div class="studio-kpi"><span class="studio-kpi-label">Qué se evaluó</span><span class="studio-kpi-value">${escapeHtml(b.what_was_evaluated || "Escenario territorial")}</span></div>
                    <div class="studio-kpi"><span class="studio-kpi-label">Dónde</span><span class="studio-kpi-value">${escapeHtml(b.where_was_evaluated || ev.geographic_scope || ctx.district_name)}</span></div>
                    <div class="studio-kpi"><span class="studio-kpi-label">Horizonte</span><span class="studio-kpi-value">${escapeHtml(b.temporal_horizon_summary || `${ev.horizon_days || 30} días`)}</span></div>
                </div>
                <p style="font-size:13.5px; font-weight:600; margin:8px 0 4px; color:var(--text-primary);">${escapeHtml(b.overall_result_headline || rec.executive_summary || "")}</p>
                <p style="font-size:12.5px; line-height:1.55; color:var(--text-secondary); margin:0 0 8px;">${escapeHtml(b.understandable_recommendation || "")}</p>
                <div class="studio-basic-grid">
                    ${this._renderBasicCardHtml(b.estimated_revenue, "Ingresos estimados")}
                    ${this._renderBasicCardHtml(b.estimated_expenses, "Gastos estimados")}
                    ${this._renderBasicCardHtml(b.operating_result, "Resultado operativo")}
                    ${this._renderBasicCardHtml(b.potential_demand, "Demanda potencial")}
                    ${this._renderBasicCardHtml(b.potential_customers, "Clientes potenciales")}
                    ${(b.contextual_highlights || []).map((c) => this._renderBasicCardHtml(c)).join("")}
                </div>
                <div class="studio-basic-grid" style="margin-top:8px;">
                    <div class="studio-basic-metric">
                        <strong>✅ Principales oportunidades</strong>
                        <ul class="studio-list" style="margin-top:4px;">${(b.main_opportunities || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
                    </div>
                    <div class="studio-basic-metric">
                        <strong>⚠️ Principales riesgos</strong>
                        <ul class="studio-list" style="margin-top:4px;">${(b.main_risks || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
                    </div>
                </div>
                <div class="studio-disclaimer" style="margin-top:8px;">${escapeHtml(b.non_guarantee_notice || "Estimación simulada bajo supuestos explícitos; no representa ganancias garantizadas.")}</div>
            </div>`;

        const scenariosHtml = (inter.alternative_scenarios || []).length
            ? `
            <div class="studio-card">
                <div class="studio-card-header">
                    <span class="studio-card-title">📊 Comparación de Escenarios (Parámetros Documentados)</span>
                    <span class="studio-badge info">${escapeHtml((inter.alternative_scenarios || []).length)} escenarios</span>
                </div>
                <table class="studio-comparison-table">
                    <thead><tr><th>Escenario</th><th>Parámetros</th><th>Métricas clave</th><th>Nota de derivación</th></tr></thead>
                    <tbody>
                        ${(inter.alternative_scenarios || []).map((s) => `
                            <tr>
                                <td><strong>${escapeHtml(s.scenario_label)}</strong></td>
                                <td><code>${escapeHtml(JSON.stringify(s.parameters_used || {}))}</code></td>
                                <td><code>${escapeHtml(JSON.stringify(s.metrics || {}))}</code></td>
                                <td style="font-size:11px; color:var(--text-muted);">${escapeHtml(s.derivation_note || "")}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>`
            : "";

        const intermediateHtml = `
            <div class="studio-card">
                <div class="studio-card-header">
                    <span class="studio-card-title">📈 Análisis Orientado a Decisiones</span>
                    <span class="studio-badge ${vMeta.cls}">${escapeHtml(vMeta.label)}</span>
                </div>
                <div class="studio-basic-grid">
                    <div class="studio-basic-metric"><strong>Demanda y Mercado</strong><p>${escapeHtml(inter.demand_and_market || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Competencia</strong><p>${escapeHtml(inter.competition || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Comportamiento de Consumidores</strong><p>${escapeHtml(inter.consumer_behavior || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Capacidad Económica</strong><p>${escapeHtml(inter.economic_capacity || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Movilidad Territorial</strong><p>${escapeHtml(inter.territorial_mobility || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Accesibilidad</strong><p>${escapeHtml(inter.accessibility || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Empleo</strong><p>${escapeHtml(inter.employment || "")}</p></div>
                    <div class="studio-basic-metric"><strong>Costos y Rentabilidad</strong><p>${escapeHtml(inter.costs_and_profitability || "")}</p></div>
                </div>
                <div class="studio-basic-grid" style="margin-top:8px;">
                    <div class="studio-basic-metric">
                        <strong>⚠️ Riesgos Comerciales y Brechas</strong>
                        <ul class="studio-list">${(inter.commercial_risks || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
                    </div>
                    <div class="studio-basic-metric">
                        <strong>🧭 Recomendaciones Accionables</strong>
                        <ul class="studio-list">${(inter.actionable_recommendations || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
                    </div>
                </div>
            </div>
            ${scenariosHtml}
            ${cmpHtml}`;

        const execMeta = exp.execution_metadata || {};
        const extrap = exp.extrapolations || {};
        const originCounts = exp.evidence_origin_counts || {};
        const originSummary = Object.entries(originCounts)
            .map(([k, v]) => `<span class="studio-origin-badge" data-origin="${escapeHtml(k)}">${escapeHtml(k)}: ${escapeHtml(v)}</span>`)
            .join(" ");

        const expertMetaHtml = `
            <div class="studio-card">
                <div class="studio-card-header">
                    <span class="studio-card-title">🔬 Auditoría Técnica, Reproducibilidad y Procedencia</span>
                    <span class="studio-badge info">Seed ${escapeHtml(execMeta.seed ?? ev.seed)}</span>
                </div>
                <div style="font-size:11.5px; color:var(--text-secondary); line-height:1.55;">
                    Ejecución: <code>${escapeHtml(execMeta.execution_id || "")}</code> · Escenario: <code>${escapeHtml(execMeta.scenario_id || ev.scenario_id || "")}</code> · Versión: <code>${escapeHtml(execMeta.engine_version || "SALTBOR-Phase-1.17")}</code><br/>
                    Motores: ${escapeHtml((execMeta.active_engines || ev.active_engines || []).join(", "))}<br/>
                    Contabilidad: ${ledgerOk ? "Conservación verificada" : "Alerta"} (<code>$${Number(ev.ledger_audit?.cash_conservation_diff_usd || 0).toFixed(2)} diff</code>, ${escapeHtml(ev.ledger_audit?.total_transactions ?? 0)} transacciones)<br/>
                    Cohorte directa vs Extrapolación: visitas directas=<code>${escapeHtml(extrap.raw_cohort_visitors ?? "N/A")}</code>, ventas libro=<code>$${escapeHtml(extrap.raw_cohort_revenue_usd ?? "N/A")}</code> → visitas proyectadas=<code>${escapeHtml(extrap.extrapolated_visitors ?? "N/A")}</code>
                </div>
                ${originSummary ? `<div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:6px;">${originSummary}</div>` : ""}
            </div>`;

        return { defaultLvl, basicHtml, intermediateHtml, expertMetaHtml };
    }

    renderStageBResult(res) {
        const ev = res.evidence || {};
        const rec = res.recommendation || {};
        const ctx = res.territorial_context || {};
        const prog = res.progressive_report || null;
        const vMeta = VERDICT_META[rec.verdict] || { label: rec.verdict || "ANALIZADO", cls: "info" };
        const ledgerOk = ev.ledger_audit?.conservation_passed !== false;

        const wrap = document.createElement("div");
        wrap.className = "studio-msg assistant";

        const indicatorsHtml = (ev.indicators || [])
            .filter((i) => i.available && i.value !== null && i.value !== undefined)
            .map((ind) => {
                const p = ind.provenance || {};
                const univOrig = escapeHtml(ind.evidence_origin || ind.data_origin || (ind.is_synthetic === false ? "PUBLIC_OFFICIAL" : "SYNTHETIC_SIMULATED"));
                const calibTag = escapeHtml(ind.empirical_calibration_status || "UNCALIBRATED_SYNTHETIC");
                return `
                <div class="studio-ind-row">
                    <div class="studio-ind-top">
                        <strong>${escapeHtml(ind.name)}</strong>
                        <span class="studio-origin-badge" data-origin="${univOrig}">${univOrig}</span>
                        <span class="studio-kpi-value" style="margin:0;">${escapeHtml(ind.value)} ${escapeHtml(ind.unit)}</span>
                    </div>
                    <details class="studio-details">
                        <summary>Explicación técnica, incertidumbre y procedencia (${calibTag})</summary>
                        <div class="studio-ind-prov">
                            ${ind.expert_explanation ? `<strong>Explicación EXPERT:</strong> ${escapeHtml(ind.expert_explanation)}<br/>` : ""}
                            ${ind.definition ? `<strong>Definición:</strong> ${escapeHtml(ind.definition)}<br/>` : ""}
                            <strong>Clasificación universal:</strong> <code>${univOrig}</code> · <strong>Calibración:</strong> <code>${calibTag}</code> · <strong>Motor:</strong> <code>${escapeHtml(p.source_engine)}</code><br/>
                            <strong>Método:</strong> ${escapeHtml(p.calculation_method)} · <strong>Intervalo:</strong> ${escapeHtml(p.time_interval)} · <strong>Alcance:</strong> ${escapeHtml(p.population_scope)} · <strong>Semilla:</strong> ${escapeHtml(p.seed)}<br/>
                            <strong>Incertidumbre:</strong> ${escapeHtml(ind.uncertainty || "Ver supuestos.")}<br/>
                            <strong>Limitaciones:</strong> ${escapeHtml(p.limitations)}
                        </div>
                    </details>
                </div>`;
            })
            .join("");

        const opinionsHtml = (ev.synthetic_opinions || [])
            .map(
                (op) => `
                <div class="studio-ind-row">
                    <div class="studio-ind-top">
                        <strong>Grupo sintético: ${escapeHtml(op.group_label)}</strong>
                        <span class="studio-badge synthetic">NO INDEPENDIENTE</span>
                    </div>
                    <p style="margin-top:4px; color:var(--text-secondary);">${escapeHtml(op.response_text)}</p>
                    <div class="studio-ind-prov">${escapeHtml(op.correlation_warning)}</div>
                </div>`
            )
            .join("");

        const cmpHtml = res.comparison
            ? `
            <div class="studio-card">
                <div class="studio-card-header">
                    <span class="studio-card-title">⚖️ Comparación de Escenarios (Múltiples Semillas)</span>
                    <span class="studio-badge info">Mejor relativo: ${escapeHtml(res.comparison.recommended_alternative)}</span>
                </div>
                <table class="studio-comparison-table">
                    <thead>
                        <tr><th>Escenario</th><th>Asistencia Esc.</th><th>Riesgo Deserción</th><th>Ingreso Neto</th><th>Liquidez Prom.</th></tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Línea Base</td>
                            <td>${((res.comparison.baseline.metrics_mean.school_attendance_rate || 0) * 100).toFixed(1)}%</td>
                            <td>${((res.comparison.baseline.metrics_mean.school_dropout_risk || 0) * 100).toFixed(1)}%</td>
                            <td>$${Number(res.comparison.baseline.metrics_mean.commercial_net_profit_usd || 0).toFixed(2)}</td>
                            <td>$${Number(res.comparison.baseline.metrics_mean.household_avg_cash_usd || 0).toFixed(2)}</td>
                        </tr>
                        ${(res.comparison.alternatives || [])
                            .map(
                                (alt) => `
                            <tr>
                                <td><strong>${escapeHtml(alt.label)}</strong></td>
                                <td>${((alt.metrics_mean.school_attendance_rate || 0) * 100).toFixed(1)}%</td>
                                <td>${((alt.metrics_mean.school_dropout_risk || 0) * 100).toFixed(1)}%</td>
                                <td>$${Number(alt.metrics_mean.commercial_net_profit_usd || 0).toFixed(2)}</td>
                                <td>$${Number(alt.metrics_mean.household_avg_cash_usd || 0).toFixed(2)}</td>
                            </tr>`
                            )
                            .join("")}
                    </tbody>
                </table>
                <div class="studio-disclaimer">${escapeHtml(res.comparison.methodology_note)}</div>
            </div>`
            : "";

        const tiB = res.territorial_intelligence || {};
        const tiBHtml = tiB.mobility
            ? `
            <div class="studio-card">
                <div class="studio-card-header">
                    <span class="studio-card-title">🧭 Inteligencia Territorial Nacional, Movilidad y Empleo (A–G)</span>
                    <span class="studio-badge info">Cobertura ${escapeHtml(tiB.coverage_tier || "PARTIAL")}</span>
                </div>
                <div class="studio-kpi-grid">
                    <div class="studio-kpi">
                        <span class="studio-kpi-label">Edificios OSM</span>
                        <span class="studio-kpi-value">${escapeHtml(tiB.buildings?.total_observed ?? 0)}</span>
                    </div>
                    <div class="studio-kpi">
                        <span class="studio-kpi-label">Comercios Reales</span>
                        <span class="studio-kpi-value">${escapeHtml(tiB.commerce?.confirmed_establishments ?? 0)} confirmados</span>
                    </div>
                    <div class="studio-kpi">
                        <span class="studio-kpi-label">Índice Peatonal Sintético</span>
                        <span class="studio-kpi-value">${escapeHtml(tiB.mobility?.estimated_pedestrian_activity_index ?? 0)}</span>
                    </div>
                    <div class="studio-kpi">
                        <span class="studio-kpi-label">Desajuste Empleo</span>
                        <span class="studio-kpi-value">${escapeHtml(tiB.employment?.jobs_workers_spatial_mismatch ?? 0)}</span>
                    </div>
                </div>
                <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">
                    ${escapeHtml(tiB.catchment?.methodology || "")} · ${escapeHtml(tiB.mobility?.measured_flows_note || "")}
                </div>
            </div>`
            : "";

        const activeInd = (ev.indicators || []).find((i) => i.indicator_id === "unique_active_cohort");
        const { defaultLvl, basicHtml, intermediateHtml, expertMetaHtml } = this._renderProgressivePanes(
            prog, rec, ev, ctx, tiBHtml, cmpHtml, indicatorsHtml, opinionsHtml, ledgerOk
        );
        wrap.innerHTML = `
            <div class="studio-msg-role">SALTBOR · Resultados Simulados (Etapa B) · Proveedor analítico: ${escapeHtml(rec.provider_used || "OFFLINE")}</div>
            <div class="studio-msg-bubble">
                <div class="studio-depth-switcher" role="tablist" aria-label="Nivel de profundidad del reporte">
                    <button type="button" class="studio-depth-btn ${defaultLvl === "BASIC" ? "active" : ""}" data-depth-tab="BASIC">Resumen sencillo</button>
                    <button type="button" class="studio-depth-btn ${defaultLvl === "INTERMEDIATE" ? "active" : ""}" data-depth-tab="INTERMEDIATE">Análisis de decisiones</button>
                    <button type="button" class="studio-depth-btn ${defaultLvl === "EXPERT" ? "active" : ""}" data-depth-tab="EXPERT">Análisis exhaustivo</button>
                </div>

                <div class="studio-depth-pane ${defaultLvl === "BASIC" ? "active" : ""}" data-depth="BASIC">
                    ${basicHtml}
                </div>

                <div class="studio-depth-pane ${defaultLvl === "INTERMEDIATE" ? "active" : ""}" data-depth="INTERMEDIATE">
                    ${intermediateHtml}
                </div>

                <div class="studio-depth-pane ${defaultLvl === "EXPERT" ? "active" : ""}" data-depth="EXPERT">
                    ${expertMetaHtml}
                    <!-- B. Simulation Summary -->
                    <div class="studio-card">
                        <div class="studio-card-header">
                            <span class="studio-card-title">📊 Resumen de Simulación</span>
                            <span class="studio-badge ${ledgerOk ? "real" : "risk"}">Contabilidad: $${Number(ev.ledger_audit?.cash_conservation_diff_usd || 0).toFixed(2)} diff</span>
                        </div>
                        <div class="studio-kpi-grid">
                            <div class="studio-kpi">
                                <span class="studio-kpi-label">Alcance Geográfico</span>
                                <span class="studio-kpi-value">${escapeHtml(ev.geographic_scope || ctx.district_name)}</span>
                            </div>
                            <div class="studio-kpi">
                                <span class="studio-kpi-label">Agentes Sintéticos Activos</span>
                                <span class="studio-kpi-value">${escapeHtml(activeInd ? activeInd.value : 0)} únicos</span>
                            </div>
                            <div class="studio-kpi">
                                <span class="studio-kpi-label">Horizonte Ejecutado</span>
                                <span class="studio-kpi-value">${escapeHtml(ev.horizon_days)} días (${escapeHtml(ev.simulated_ticks)} ticks eq.)</span>
                            </div>
                            <div class="studio-kpi">
                                <span class="studio-kpi-label">Motores Reales</span>
                                <span class="studio-kpi-value">${escapeHtml((ev.active_engines || []).length)} activos</span>
                            </div>
                        </div>
                    </div>

                    <!-- C. Evidence (Separated from LLM Interpretation) -->
                    <div class="studio-card">
                        <div class="studio-card-header">
                            <span class="studio-card-title">🧬 Evidencia y Procedencia Universal (${escapeHtml((ev.indicators || []).length)} indicadores)</span>
                            <span class="studio-badge synthetic">SYNTHETIC_SIMULATED</span>
                        </div>
                        <div class="studio-ind-list">${indicatorsHtml}</div>
                        ${opinionsHtml ? `<details class="studio-details"><summary>💬 Reacciones agrupadas de agentes sintéticos (${ev.synthetic_opinions.length})</summary><div class="studio-ind-list">${opinionsHtml}</div></details>` : ""}
                        ${(ev.missing_indicators || []).length ? `<details class="studio-details"><summary>⚠️ Indicadores no disponibles / datos faltantes (${ev.missing_indicators.length})</summary><ul class="studio-list">${ev.missing_indicators.map((m) => `<li>${escapeHtml(m)}</li>`).join("")}</ul></details>` : ""}
                    </div>

                    <!-- D & E. Gemini / Analyst Interpretation & Recommendations -->
                    <div class="studio-card">
                        <div class="studio-card-header">
                            <span class="studio-card-title">🧠 Análisis e Interpretación (${escapeHtml(rec.model_used || rec.provider_used)})</span>
                            <span class="studio-badge ${vMeta.cls}">${escapeHtml(vMeta.label)}</span>
                        </div>
                        <p style="font-size:13px; line-height:1.55;">${escapeHtml(rec.executive_summary)}</p>
                        <div style="font-size:11.5px; color:var(--text-muted);">${escapeHtml(rec.model_vs_external_distinction)}</div>
                        ${(rec.observed_patterns || []).length ? `<div><strong style="font-size:12px;">Patrones observados:</strong><ul class="studio-list">${rec.observed_patterns.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
                        ${(rec.unmet_demand || []).length ? `<div><strong style="font-size:12px;">Demanda insatisfecha y necesidades:</strong><ul class="studio-list">${rec.unmet_demand.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
                        <details class="studio-details">
                            <summary>🔍 Supuestos, incertidumbre, limitaciones e interpretaciones alternativas</summary>
                            <ul class="studio-list">
                                ${(rec.assumptions || []).map((x) => `<li><strong>Supuesto:</strong> ${escapeHtml(x)}</li>`).join("")}
                                ${(rec.uncertainty || []).map((x) => `<li><strong>Incertidumbre:</strong> ${escapeHtml(x)}</li>`).join("")}
                                ${(rec.limitations || []).map((x) => `<li><strong>Limitación:</strong> ${escapeHtml(x)}</li>`).join("")}
                                ${(rec.alternative_interpretations || []).map((x) => `<li><strong>Alternativa:</strong> ${escapeHtml(x)}</li>`).join("")}
                            </ul>
                        </details>
                        <div class="studio-disclaimer">${escapeHtml(rec.disclaimer)}</div>
                    </div>

                    ${tiBHtml}
                    ${cmpHtml}
                </div>
            </div>
        `;

        this._bindDepthTabHandlers(wrap);
        this.thread.appendChild(wrap);
        this.scrollToBottom();
    }

    _bindDepthTabHandlers(wrap) {
        wrap.querySelectorAll("[data-depth-tab]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const targetDepth = btn.getAttribute("data-depth-tab");
                this.activeReportLevel = targetDepth;
                wrap.querySelectorAll("[data-depth-tab]").forEach((b) => {
                    b.classList.toggle("active", b.getAttribute("data-depth-tab") === targetDepth);
                });
                wrap.querySelectorAll(".studio-depth-pane").forEach((pane) => {
                    pane.classList.toggle("active", pane.getAttribute("data-depth") === targetDepth);
                });
            });
        });
    }

    _renderPersistedProgressiveCard(execRec, sess) {
        const prog = execRec?.progressive_report;
        if (!prog || !this.thread) return;
        const execMeta = prog.expert?.execution_metadata || {};
        const ledgerAudit = prog.expert?.transactions_and_accounting || {
            conservation_passed: true,
            cash_conservation_diff_usd: execRec.ledger_conservation_diff ?? 0,
            total_transactions: execRec.total_transactions ?? 0,
        };
        const ev = {
            geographic_scope: prog.basic?.where_was_evaluated || sess?.active_location_query || "",
            horizon_days: execMeta.horizon_days || 30,
            seed: execMeta.seed ?? execRec.seed,
            scenario_id: execMeta.scenario_id || execRec.scenario_id || "",
            active_engines: execMeta.active_engines || [],
            ledger_audit: ledgerAudit,
        };
        const rec = {
            verdict: prog.basic?.overall_verdict_code || execRec.verdict || "CONDITIONALLY_PROMISING",
            executive_summary: prog.basic?.overall_result_headline || "",
            provider_used: execMeta.provider_used || "OFFLINE",
        };
        const ctx = { district_name: ev.geographic_scope };
        const ledgerOk = ledgerAudit.conservation_passed !== false;
        const { defaultLvl, basicHtml, intermediateHtml, expertMetaHtml } = this._renderProgressivePanes(
            prog, rec, ev, ctx, "", "", "", "", ledgerOk
        );
        const allCardsHtml = (prog.expert?.all_indicators || [])
            .map((c) => `
                <div class="studio-ind-row">
                    <div class="studio-ind-top">
                        <strong>${escapeHtml(c.label)}</strong>
                        <span class="studio-origin-badge" data-origin="${escapeHtml(c.evidence_origin)}">${escapeHtml(c.evidence_origin)}</span>
                        <span class="studio-kpi-value" style="margin:0;">${escapeHtml(c.formatted_value)}</span>
                    </div>
                    <details class="studio-details">
                        <summary>Explicación técnica (${escapeHtml(c.empirical_calibration_status)})</summary>
                        <div class="studio-ind-prov">
                            <strong>Explicación EXPERT:</strong> ${escapeHtml(c.expert_explanation)}<br/>
                            <strong>Procedencia:</strong> ${escapeHtml(c.where_it_comes_from)} · ${escapeHtml(c.how_it_was_obtained)}<br/>
                            <strong>Incertidumbre:</strong> ${escapeHtml(c.uncertainty)}<br/>
                            <strong>Limitaciones:</strong> ${escapeHtml(c.limitations)}
                        </div>
                    </details>
                </div>`
            )
            .join("");

        const wrap = document.createElement("div");
        wrap.className = "studio-msg assistant";
        wrap.innerHTML = `
            <div class="studio-msg-role">SALTBOR · Reporte Persistido (${escapeHtml(execRec.execution_id || "")})</div>
            <div class="studio-msg-bubble">
                <div class="studio-depth-switcher" role="tablist" aria-label="Nivel de profundidad del reporte persistido">
                    <button type="button" class="studio-depth-btn ${defaultLvl === "BASIC" ? "active" : ""}" data-depth-tab="BASIC">Resumen sencillo</button>
                    <button type="button" class="studio-depth-btn ${defaultLvl === "INTERMEDIATE" ? "active" : ""}" data-depth-tab="INTERMEDIATE">Análisis de decisiones</button>
                    <button type="button" class="studio-depth-btn ${defaultLvl === "EXPERT" ? "active" : ""}" data-depth-tab="EXPERT">Análisis exhaustivo</button>
                </div>
                <div class="studio-depth-pane ${defaultLvl === "BASIC" ? "active" : ""}" data-depth="BASIC">${basicHtml}</div>
                <div class="studio-depth-pane ${defaultLvl === "INTERMEDIATE" ? "active" : ""}" data-depth="INTERMEDIATE">${intermediateHtml}</div>
                <div class="studio-depth-pane ${defaultLvl === "EXPERT" ? "active" : ""}" data-depth="EXPERT">
                    ${expertMetaHtml}
                    <div class="studio-card">
                        <div class="studio-card-header"><span class="studio-card-title">🧬 Indicadores Auditados (${escapeHtml((prog.expert?.all_indicators || []).length)})</span></div>
                        <div class="studio-ind-list">${allCardsHtml}</div>
                    </div>
                </div>
            </div>`;
        this._bindDepthTabHandlers(wrap);
        this.thread.appendChild(wrap);
    }

    // =========================================================================
    // LOCATION SEARCH & OPTIONAL SINGLE-MAP REUSE
    // =========================================================================
    async performLocationSearch(query) {
        if (!this.autocompleteMenu) return;
        try {
            const res = await fetch(`/api/studio/territory/search?q=${encodeURIComponent(query)}&limit=8`);
            if (!res.ok) return;
            const data = await res.json();
            const items = data.results || [];
            if (!items.length) {
                this.autocompleteMenu.innerHTML = `<div style="padding:8px 10px; font-size:11.5px; color:var(--text-muted);">Sin coincidencias exactas en D.L. 762 / OSM</div>`;
                this.autocompleteMenu.classList.add("open");
                return;
            }
            this.autocompleteMenu.innerHTML = items
                .map(
                    (it, idx) => `
                    <button type="button" class="studio-autocomplete-item" data-loc-idx="${idx}">
                        <span><strong>${escapeHtml(it.label)}</strong></span>
                        <span style="color:var(--text-muted); font-size:11px;">${escapeHtml(it.level)}</span>
                    </button>`
                )
                .join("");
            this.autocompleteMenu.querySelectorAll("[data-loc-idx]").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const item = items[Number(btn.getAttribute("data-loc-idx"))];
                    this.selectSearchLocation(item);
                });
            });
            this.autocompleteMenu.classList.add("open");
        } catch (err) {
            console.warn("Location search error:", err);
        }
    }

    async selectSearchLocation(item) {
        this.autocompleteMenu?.classList.remove("open");
        if (this.locationSearch) this.locationSearch.value = item.label;
        this.activeCoordinates = { lat: item.lat, lon: item.lon };
        if (this.btnClearPoint) this.btnClearPoint.style.display = "inline-flex";
        try {
            const res = await fetch(`/api/studio/territory/resolve?query=${encodeURIComponent(item.district_name)}`);
            if (res.ok) {
                this.activeContext = await res.json();
                this.updateContextPill();
                if (this.mapMode !== "hidden") {
                    this.syncMapToContext(this.activeContext);
                }
            }
        } catch (err) {
            console.warn("Resolve location error:", err);
        }
    }

    setMapMode(mode) {
        this.mapMode = mode;
        if (!this.shell) return;

        this.shell.classList.remove("map-hidden", "map-side", "map-expanded");
        if (mode === "full") {
            this.restoreWorldMapContainer();
            if (typeof window.switchView === "function") window.switchView("world");
            document.getElementById("btn-return-to-studio")?.style.setProperty("display", "inline-flex");
            return;
        }

        this.shell.classList.add(`map-${mode}`);
        document.querySelectorAll(".studio-map-mode-btn").forEach((b) => b.classList.remove("btn-primary"));
        document.getElementById(`studio-map-mode-${mode}`)?.classList.add("btn-primary");

        if (mode === "hidden") {
            this.isPickingMapPoint = false;
            return;
        }

        // Keep chat & side map unobstructed cleanly on laptop/desktop viewports
        document.getElementById("inspector-panel")?.classList.add("collapsed");
        if (window.innerWidth < 1600) {
            this.shell.classList.add("history-collapsed");
        }

        // Lazily dock the single #maplibre-viewport inside Studio map host
        const viewportEl = document.getElementById("maplibre-viewport");
        if (viewportEl && this.mapHost && viewportEl.parentElement !== this.mapHost) {
            this.mapHost.appendChild(viewportEl);
        }
        if (typeof window.initOrResizeGIS25D === "function") {
            window.initOrResizeGIS25D();
        }
        setTimeout(() => {
            const map = window.saltborState?.gisMap;
            if (map) {
                map.resize();
                this.attachMapClickListener(map);
                if (this.activeContext) this.syncMapToContext(this.activeContext);
            }
        }, 160);
    }

    restoreWorldMapContainer() {
        const viewportEl = document.getElementById("maplibre-viewport");
        const worldLayout = document.querySelector("#view-world .gis-layout");
        if (viewportEl && worldLayout && viewportEl.parentElement !== worldLayout) {
            worldLayout.insertBefore(viewportEl, worldLayout.firstChild);
        }
    }

    attachMapClickListener(map) {
        if (map._studioClickBound) return;
        map._studioClickBound = true;
        map.on("click", async (e) => {
            if (this.mapMode === "hidden") return;
            const lat = Number(e.lngLat.lat.toFixed(6));
            const lon = Number(e.lngLat.lng.toFixed(6));

            if (this.isDrawingPolygon) {
                this.drawnVertices.push([lon, lat]);
                this.renderDrawnPolygonPreview(map);
                if (this.mapCoordsLabel) {
                    this.mapCoordsLabel.textContent = `Polígono: ${this.drawnVertices.length} vértice(s) trazados. Clic para agregar o 'Cerrar Polígono'.`;
                }
                return;
            }

            if (!this.isPickingMapPoint) return;
            this.activeCoordinates = { lat, lon };
            this.isPickingMapPoint = false;
            this.btnAttachMapPoint?.classList.remove("btn-primary");
            this.btnAttachMapPoint?.classList.add("btn-secondary");
            if (this.btnClearPoint) this.btnClearPoint.style.display = "inline-flex";

            try {
                const res = await fetch(`/api/studio/territory/resolve?lat=${lat}&lon=${lon}`);
                if (res.ok) {
                    this.activeContext = await res.json();
                    this.updateContextPill();
                    this.syncMapToContext(this.activeContext);
                }
            } catch (err) {
                console.warn("Map coordinate resolve error:", err);
            }
        });
    }

    togglePolygonDraw(enable) {
        if (this.mapMode === "hidden") this.setMapMode("side");
        this.isDrawingPolygon = Boolean(enable);
        this.isPickingMapPoint = false;
        if (this.isDrawingPolygon) {
            this.drawnVertices = [];
            this.activePolygonGeoJSON = null;
        }
        if (this.btnFinishPolygon) this.btnFinishPolygon.style.display = this.isDrawingPolygon ? "inline-flex" : "none";
        if (this.btnClearPolygon) this.btnClearPolygon.style.display = "inline-flex";
        if (this.mapCoordsLabel && this.isDrawingPolygon) {
            this.mapCoordsLabel.textContent = "Haz clic en el mapa para trazar vértices del polígono principal.";
        }
    }

    finishPolygonDraw() {
        if (this.drawnVertices.length < 3) {
            if (this.mapCoordsLabel) this.mapCoordsLabel.textContent = "Se requieren al menos 3 vértices para cerrar el polígono.";
            return;
        }
        const ring = [...this.drawnVertices, this.drawnVertices[0]];
        this.activePolygonGeoJSON = { type: "Polygon", coordinates: [ring] };
        this.isDrawingPolygon = false;
        if (this.btnFinishPolygon) this.btnFinishPolygon.style.display = "none";
        const map = window.saltborState?.gisMap;
        if (map) this.renderDrawnPolygonPreview(map);
        this.runTerritorialDiscovery();
    }

    clearDrawnPolygon() {
        this.isDrawingPolygon = false;
        this.drawnVertices = [];
        this.activePolygonGeoJSON = null;
        if (this.btnFinishPolygon) this.btnFinishPolygon.style.display = "none";
        if (this.btnClearPolygon) this.btnClearPolygon.style.display = "none";
        const map = window.saltborState?.gisMap;
        if (map && map.getSource("studio-drawn-poly")) {
            map.getSource("studio-drawn-poly").setData({ type: "FeatureCollection", features: [] });
        }
    }

    renderDrawnPolygonPreview(map) {
        const feats = [];
        if (this.drawnVertices.length >= 3) {
            const ring = [...this.drawnVertices, this.drawnVertices[0]];
            feats.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: {} });
        } else if (this.drawnVertices.length >= 2) {
            feats.push({ type: "Feature", geometry: { type: "LineString", coordinates: this.drawnVertices }, properties: {} });
        }
        const fc = { type: "FeatureCollection", features: feats };
        if (map.getSource("studio-drawn-poly")) {
            map.getSource("studio-drawn-poly").setData(fc);
        } else if (map.isStyleLoaded() || map.getStyle()) {
            map.addSource("studio-drawn-poly", { type: "geojson", data: fc });
            map.addLayer({
                id: "studio-drawn-poly-fill",
                type: "fill",
                source: "studio-drawn-poly",
                paint: { "fill-color": "#f59e0b", "fill-opacity": 0.18 },
            });
            map.addLayer({
                id: "studio-drawn-poly-line",
                type: "line",
                source: "studio-drawn-poly",
                paint: { "line-color": "#f59e0b", "line-width": 2.2 },
            });
        }
    }

    getSelectedTravelTimeMinutes() {
        const val = this.travelTimeSelect?.value || "15";
        if (val === "custom") {
            return Math.max(3, Math.min(90, Number(this.travelTimeCustom?.value || 25)));
        }
        return Number(val) || 15;
    }

    async runTerritorialDiscovery() {
        const payload = {
            location_query: !this.activePolygonGeoJSON && !this.activeCoordinates ? (this.activeContext?.district_name || this.locationSearch?.value || "Santa Tecla") : null,
            lat: !this.activePolygonGeoJSON && this.activeCoordinates ? this.activeCoordinates.lat : null,
            lon: !this.activePolygonGeoJSON && this.activeCoordinates ? this.activeCoordinates.lon : null,
            polygon_geojson: this.activePolygonGeoJSON,
            travel_time_minutes: this.getSelectedTravelTimeMinutes(),
            sector: this.sectorSelect?.value || "general",
            max_expansion_minutes: this.maxExpansionMinutes || 30,
        };
        try {
            if (this.mapCoordsLabel) this.mapCoordsLabel.textContent = "Ejecutando descubrimiento censal y territorial (3 escalas)...";
            const res = await fetch("/api/territorial/discover", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.lastDiscovery = data;
            this.renderDiscoveryLayersOnMap(data);
            this.renderExplorerInspector(data);
        } catch (err) {
            if (this.mapCoordsLabel) this.mapCoordsLabel.textContent = `Error en análisis territorial: ${err.message}`;
        }
    }

    renderDiscoveryLayersOnMap(data) {
        const map = window.saltborState?.gisMap;
        if (!map || !data?.areas_geojson) return;
        const disc = data.discovery;
        if (disc?.center_lat && disc?.center_lon) {
            map.flyTo({ center: [disc.center_lon, disc.center_lat], zoom: 13.6, duration: 750 });
        }

        const apply = () => {
            if (map.getSource("studio-118-areas")) {
                map.getSource("studio-118-areas").setData(data.areas_geojson);
            } else {
                map.addSource("studio-118-areas", { type: "geojson", data: data.areas_geojson });
                map.addLayer({
                    id: "studio-118-contextual",
                    type: "fill",
                    source: "studio-118-areas",
                    filter: ["==", "zone_tier", "CONTEXTUAL_AREA"],
                    paint: { "fill-color": "#6366f1", "fill-opacity": 0.08, "fill-outline-color": "#6366f1" },
                });
                map.addLayer({
                    id: "studio-118-influence",
                    type: "fill",
                    source: "studio-118-areas",
                    filter: ["==", "zone_tier", "INFLUENCE_AREA"],
                    paint: { "fill-color": "#0ea5e9", "fill-opacity": 0.14, "fill-outline-color": "#0ea5e9" },
                });
                map.addLayer({
                    id: "studio-118-primary",
                    type: "fill",
                    source: "studio-118-areas",
                    filter: ["==", "zone_tier", "PRIMARY_AREA"],
                    paint: { "fill-color": "#f59e0b", "fill-opacity": 0.24, "fill-outline-color": "#f59e0b" },
                });
            }

            if (map.getSource("studio-118-pop-clusters")) {
                map.getSource("studio-118-pop-clusters").setData(data.population_clusters_geojson);
            } else {
                map.addSource("studio-118-pop-clusters", { type: "geojson", data: data.population_clusters_geojson });
                map.addLayer({
                    id: "studio-118-pop",
                    type: "circle",
                    source: "studio-118-pop-clusters",
                    paint: {
                        "circle-radius": ["interpolate", ["linear"], ["get", "households"], 1, 5, 30, 14],
                        "circle-color": "#a855f7",
                        "circle-opacity": 0.72,
                        "circle-stroke-width": 1,
                        "circle-stroke-color": "#ffffff",
                    },
                });
            }

            if (map.getSource("studio-118-infra")) {
                map.getSource("studio-118-infra").setData(data.infrastructure_geojson);
            } else {
                map.addSource("studio-118-infra", { type: "geojson", data: data.infrastructure_geojson });
                map.addLayer({
                    id: "studio-118-infra-points",
                    type: "circle",
                    source: "studio-118-infra",
                    filter: ["!=", "domain", "ENVIRONMENT"],
                    paint: {
                        "circle-radius": 5,
                        "circle-color": [
                            "match", ["get", "domain"],
                            "EDUCATION", "#10b981",
                            "HEALTH", "#ef4444",
                            "ECONOMY", "#f59e0b",
                            "#38bdf8",
                        ],
                        "circle-stroke-width": 1,
                        "circle-stroke-color": "#0f172a",
                    },
                });
                map.addLayer({
                    id: "studio-118-barriers-points",
                    type: "circle",
                    source: "studio-118-infra",
                    filter: ["==", "domain", "ENVIRONMENT"],
                    paint: { "circle-radius": 4.5, "circle-color": "#06b6d4", "circle-opacity": 0.75 },
                });
                map.on("click", "studio-118-infra-points", (ev) => {
                    const props = ev.features?.[0]?.properties;
                    if (props && this.explorerInspector) {
                        this.explorerInspector.style.display = "block";
                        this.explorerInspector.innerHTML = `
                            <div><strong>${escapeHtml(props.name)}</strong> (${escapeHtml(props.domain)} · ${escapeHtml(props.subtype)})</div>
                            <div>Zona: <code>${escapeHtml(props.zone_tier)}</code> · Dist: ${props.distance_m} m · Caminando: ${props.estimated_walk_min || "?"} min</div>
                            <div><span class="studio-prov-badge studio-prov-observed">${escapeHtml(props.verification_status)}</span>
                            <span class="studio-prov-badge studio-prov-unavailable">Capacidad: ${escapeHtml(props.capacity_evidence_type)}</span>
                            Niveles: ${escapeHtml(props.levels_evidence_status)}</div>
                        `;
                    }
                });
            }
            this.applyDiscoveryLayerVisibility();
        };

        if (map.isStyleLoaded() || map.getStyle()) {
            try { apply(); } catch (_e) {}
        }
        map.once("styledata", () => { try { apply(); } catch (_e) {} });
    }

    applyDiscoveryLayerVisibility() {
        const map = window.saltborState?.gisMap;
        if (!map) return;
        const toggleMap = {
            primary: ["studio-118-primary"],
            influence: ["studio-118-influence"],
            contextual: ["studio-118-contextual"],
            population: ["studio-118-pop"],
            infrastructure: ["studio-118-infra-points"],
            barriers: ["studio-118-barriers-points"],
        };
        document.querySelectorAll("[data-studio-layer]").forEach((chk) => {
            const ids = toggleMap[chk.getAttribute("data-studio-layer")] || [];
            const vis = chk.checked ? "visible" : "none";
            for (const lid of ids) {
                if (map.getLayer(lid)) map.setLayoutProperty(lid, "visibility", vis);
            }
        });
    }

    renderExplorerInspector(data) {
        if (!this.explorerInspector || !data) return;
        const alloc = data.allocation || {};
        const cert = data.certificate || {};
        const infra = data.infrastructure_summary || {};
        const barriers = data.discovery?.expansion?.contextual_area?.barriers_detected || [];
        this.explorerInspector.style.display = "block";
        this.explorerInspector.innerHTML = `
            <div>
                <span class="studio-prov-badge studio-prov-official">CENSO: ${escapeHtml(cert.census_granularity_used)}</span>
                <span class="studio-prov-badge studio-prov-estimated">ASIGNACIÓN: ±${alloc.uncertainty_pct}%</span>
                <span class="studio-prov-badge studio-prov-synthetic">CALIBRACIÓN: ${escapeHtml(cert.calibration_status)} (SRMSE=${cert.srmse})</span>
            </div>
            <div style="margin-top:4px;">
                <strong>Área Principal:</strong> ${alloc.target_area_km2} km² · <strong>Población asignada:</strong> ${alloc.allocated_population_target} hab. (${alloc.allocated_households_target} hogares)
                · Edificios residenciales: ${alloc.buildings_residential_confirmed} (+${alloc.buildings_unknown_probabilistic} inciertos, ${alloc.buildings_excluded_non_residential} excluidos)
            </div>
            <div>
                <strong>Infraestructura:</strong> ${JSON.stringify(infra.counts_by_domain || {})} · <strong>Barreras:</strong> ${barriers.length ? escapeHtml(barriers.join("; ")) : "Sin barreras críticas detectadas"}
            </div>
        `;
        if (this.mapCoordsLabel) {
            this.mapCoordsLabel.textContent = `${data.discovery?.primary_district_name} · Contexto ${data.discovery?.expansion?.contextual_area?.travel_time_minutes} min (${data.elapsed_ms} ms)`;
        }
    }

    syncMapToContext(ctx, intel = null) {
        if (!ctx || !ctx.resolved) return;
        const activeIntel = intel || this.activeIntelligence || null;
        if (this.mapCoordsLabel) {
            this.mapCoordsLabel.textContent = `${ctx.district_name}, ${ctx.department_name} (${ctx.lat.toFixed(4)}, ${ctx.lon.toFixed(4)}) · Elev. ${ctx.elevation_m || 0}m`;
        }
        const map = window.saltborState?.gisMap;
        if (!map) return;

        map.flyTo({ center: [ctx.lon, ctx.lat], zoom: 13.8, pitch: 25, duration: 900 });

        const features = [
            {
                type: "Feature",
                geometry: { type: "Point", coordinates: [ctx.lon, ctx.lat] },
                properties: { kind: "target", label: ctx.district_name },
            },
        ];
        if (activeIntel?.catchment?.isochrone_polygon_geojson) {
            features.push({
                type: "Feature",
                geometry: activeIntel.catchment.isochrone_polygon_geojson,
                properties: { kind: "catchment", label: "Área de influencia" },
            });
        }
        const facs = ctx.nearby_facilities || {};
        for (const [cat, items] of Object.entries(facs)) {
            for (const f of items.slice(0, 5)) {
                features.push({
                    type: "Feature",
                    geometry: { type: "Point", coordinates: [f.lon, f.lat] },
                    properties: { kind: cat, label: f.name },
                });
            }
        }
        for (const est of (activeIntel?.commerce?.top_establishments || []).slice(0, 12)) {
            features.push({
                type: "Feature",
                geometry: { type: "Point", coordinates: [est.lon, est.lat] },
                properties: { kind: "commerce", label: est.name },
            });
        }
        const fc = { type: "FeatureCollection", features };
        const applyOverlay = () => {
            if (map.getSource("studio-context-overlay")) {
                map.getSource("studio-context-overlay").setData(fc);
            } else {
                map.addSource("studio-context-overlay", { type: "geojson", data: fc });
                map.addLayer({
                    id: "studio-overlay-catchment",
                    type: "fill",
                    source: "studio-context-overlay",
                    filter: ["==", "kind", "catchment"],
                    paint: { "fill-color": "#0ea5e9", "fill-opacity": 0.14, "fill-outline-color": "#0ea5e9" },
                });
                map.addLayer({
                    id: "studio-overlay-pois",
                    type: "circle",
                    source: "studio-context-overlay",
                    filter: ["all", ["!=", "kind", "target"], ["!=", "kind", "catchment"]],
                    paint: { "circle-radius": 5, "circle-color": "#10b981", "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" },
                });
                map.addLayer({
                    id: "studio-overlay-target",
                    type: "circle",
                    source: "studio-context-overlay",
                    filter: ["==", "kind", "target"],
                    paint: { "circle-radius": 9, "circle-color": "#0ea5e9", "circle-stroke-width": 2.5, "circle-stroke-color": "#ffffff" },
                });
            }
        };
        const applyOverlaySafe = () => {
            try {
                applyOverlay();
            } catch (_e) {
                // Style not ready yet; wait for styledata/load
            }
        };
        if (map.isStyleLoaded() || map.getStyle()) applyOverlaySafe();
        map.once("styledata", applyOverlaySafe);
        map.once("load", applyOverlaySafe);
    }

    // =========================================================================
    // CONVERSATION PERSISTENCE & REPORT EXPORT
    // =========================================================================
    async refreshConversationsList() {
        if (!this.historyList) return;
        try {
            const res = await fetch("/api/studio/conversations?limit=25");
            if (!res.ok) return;
            const data = await res.json();
            const items = data.conversations || [];
            if (!items.length) {
                this.historyList.innerHTML = `<div style="padding:12px; font-size:11.5px; color:var(--text-muted);">Aún no hay conversaciones guardadas.</div>`;
                return;
            }
            this.historyList.innerHTML = items
                .map(
                    (c) => `
                <button type="button" class="studio-history-item ${c.conversation_id === this.conversationId ? "active" : ""}" data-open-conv="${escapeHtml(c.conversation_id)}">
                    <span class="studio-history-item-title">${escapeHtml(c.title)}</span>
                    <span class="studio-history-item-meta">
                        <span>${escapeHtml(c.active_location_query || "El Salvador")}</span>
                        <span>${c.execution_count} sim.</span>
                    </span>
                </button>`
                )
                .join("");
            this.historyList.querySelectorAll("[data-open-conv]").forEach((btn) => {
                btn.addEventListener("click", () => this.loadConversation(btn.getAttribute("data-open-conv")));
            });
        } catch (err) {
            console.warn("Failed to list conversations:", err);
        }
    }

    async loadConversation(cid) {
        try {
            const res = await fetch(`/api/studio/conversations/${encodeURIComponent(cid)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const sess = data.session;
            const execs = data.executions || [];

            this.conversationId = sess.conversation_id;
            this.activeScenarioId = sess.active_scenario_id;
            this.activeCoordinates = sess.active_coordinates ? { lat: sess.active_coordinates[0], lon: sess.active_coordinates[1] } : null;
            this.activeContext = sess.active_location_query ? { district_name: sess.active_location_query, department_name: "" } : null;
            this.updateContextPill();

            if (this.thread) this.thread.innerHTML = "";
            for (const turn of sess.turns || []) {
                if (turn.role === "user") {
                    this.appendUserMessage(turn.message);
                } else {
                    const wrap = document.createElement("div");
                    wrap.className = "studio-msg assistant";
                    wrap.innerHTML = `
                        <div class="studio-msg-role">SALTBOR · Historial (${escapeHtml(turn.stage)})</div>
                        <div class="studio-msg-bubble"><p>${escapeHtml(turn.message)}</p></div>
                    `;
                    this.thread.appendChild(wrap);
                }
            }
            if (execs.length) {
                const latestExec = execs[execs.length - 1];
                if (latestExec?.progressive_report) {
                    this._renderPersistedProgressiveCard(latestExec, sess);
                }
                if (this.btnExportReport) {
                    this.btnExportReport.style.display = "inline-flex";
                }
                this.lastResult = { persisted_execution: latestExec, session: sess };
            }
            this.refreshConversationsList();
            this.scrollToBottom();
        } catch (err) {
            this.appendErrorMessage(`No se pudo cargar la conversación: ${err.message}`);
        }
    }

    exportMarkdownReport() {
        if (!this.lastResult) return;
        const payload = this.lastResult;
        const lines = ["# Informe SALTBOR — Estudio de Inteligencia Territorial", ""];
        const prog = payload.progressive_report || payload.persisted_execution?.progressive_report;
        if (prog?.basic) {
            lines.push("## Nivel BASIC — Resumen Sencillo", `- **Evaluado**: ${prog.basic.what_was_evaluated}`, `- **Ubicación**: ${prog.basic.where_was_evaluated}`, `- **Horizonte**: ${prog.basic.temporal_horizon_summary}`, `- **Resultado**: ${prog.basic.overall_result_headline}`, "");
            for (const c of [prog.basic.estimated_revenue, prog.basic.estimated_expenses, prog.basic.operating_result, prog.basic.potential_demand, prog.basic.potential_customers]) {
                if (c) lines.push(`- **${c.label}**: ${c.formatted_value} [${c.evidence_origin}] — ${c.basic_explanation}`);
            }
            lines.push("", "## Nivel INTERMEDIATE — Análisis de Decisiones", `- **Demanda y Mercado**: ${prog.intermediate.demand_and_market}`, `- **Competencia**: ${prog.intermediate.competition}`, `- **Costos y Rentabilidad**: ${prog.intermediate.costs_and_profitability}`, "");
            lines.push("## Nivel EXPERT — Indicadores y Procedencia Universal");
            for (const c of prog.expert?.all_indicators || []) {
                lines.push(`- **${c.label}**: ${c.formatted_value} (${c.evidence_origin} / ${c.empirical_calibration_status}) — ${c.expert_explanation}`);
            }
            lines.push("", `> ${prog.basic.non_guarantee_notice}`);
        } else if (payload.recommendation) {
            lines.push(`**Veredicto**: ${payload.recommendation.verdict}`);
            lines.push(`**Resumen**: ${payload.recommendation.executive_summary}`, "");
            lines.push("## Indicadores Simulados (`SYNTHETIC_SIMULATED`)");
            for (const ind of payload.evidence?.indicators || []) {
                if (ind.available) lines.push(`- **${ind.name}**: ${ind.value} ${ind.unit} (Fuente: ${ind.provenance?.source_engine})`);
            }
            lines.push("", `> ${payload.recommendation.disclaimer}`);
        } else {
            lines.push("```json", JSON.stringify(payload, null, 2), "```");
        }
        const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `saltbor_informe_${this.conversationId || "estudio"}.md`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // =========================================================================
    // SETTINGS & GEMINI / OLLAMA / OFFLINE CONFIGURATION
    // =========================================================================
    async refreshProviderStatus() {
        try {
            const res = await fetch("/api/studio/providers/status");
            if (!res.ok) return;
            const st = await res.json();
            if (this.providerPill) {
                this.providerPill.dataset.status = st.status_code;
                this.providerPill.textContent = `⚙️ ${PROVIDER_STATUS_LABELS[st.status_code] || st.status_code}`;
            }
            if (this.settingsStatusText) {
                this.settingsStatusText.textContent = `${PROVIDER_STATUS_LABELS[st.status_code] || st.status_code} · Clave actual: ${st.gemini_key_masked}`;
            }
            if (this.settingsKeyMasked) {
                this.settingsKeyMasked.textContent = st.gemini_byok_configured ? `Clave en memoria: ${st.gemini_key_masked}` : "Sin clave configurada (BYOK opcional)";
            }
            if (this.settingsModeSelect && st.provider_mode) this.settingsModeSelect.value = st.provider_mode;
            if (this.settingsFlashModel && st.rate_limit?.flash_model) this.settingsFlashModel.value = st.rate_limit.flash_model;
            if (this.settingsFlashLiteModel && st.rate_limit?.flash_lite_model) this.settingsFlashLiteModel.value = st.rate_limit.flash_lite_model;
            if (this.settingsOllamaModel && st.ollama_model) this.settingsOllamaModel.value = st.ollama_model;
            if (this.settingsStrictPrivacy && typeof st.strict_redaction === "boolean") {
                this.settingsStrictPrivacy.checked = st.strict_redaction;
            }
        } catch (err) {
            console.warn("Provider status refresh error:", err);
        }
    }

    openSettingsModal() {
        this.refreshProviderStatus();
        this.settingsModal?.classList.add("open");
    }

    closeSettingsModal() {
        this.settingsModal?.classList.remove("open");
    }

    async saveProviderSettings() {
        const body = {
            provider_mode: this.settingsModeSelect?.value || "offline",
            flash_model: this.settingsFlashModel?.value?.trim() || null,
            flash_lite_model: this.settingsFlashLiteModel?.value?.trim() || null,
            ollama_model: this.settingsOllamaModel?.value?.trim() || null,
            strict_redaction: this.settingsStrictPrivacy ? this.settingsStrictPrivacy.checked : true,
        };
        const rawKey = this.settingsKeyInput?.value?.trim();
        if (rawKey) {
            body.gemini_api_key = rawKey;
        }
        try {
            const res = await fetch("/api/studio/providers/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            if (this.settingsKeyInput) this.settingsKeyInput.value = "";
            await this.refreshProviderStatus();
            this.closeSettingsModal();
        } catch (err) {
            if (this.settingsStatusText) this.settingsStatusText.textContent = `Error guardando: ${err.message}`;
        }
    }

    async clearGeminiKey() {
        try {
            await fetch("/api/studio/providers/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ gemini_api_key: "clear", provider_mode: "offline" }),
            });
            if (this.settingsKeyInput) this.settingsKeyInput.value = "";
            await this.refreshProviderStatus();
        } catch (err) {
            console.warn("Clear key error:", err);
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.territorialStudio = new TerritorialSimulationStudio();
});
