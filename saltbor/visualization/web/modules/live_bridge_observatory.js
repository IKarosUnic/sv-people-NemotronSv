/**
 * SALTBOR Phase 1.16–1.18 Modular ES6 Observatory, 1-Click Citizen Quick Simulator
 * & Ultra-Precise Pinpoint Map Placement Module.
 * 100% Vanilla JavaScript ES6 Module — Zero external CDN or bundler dependencies.
 */

export async function fetchPipelineTelemetry() {
    const res = await fetch('/api/pipeline/telemetry');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function configureAdaptiveLODBudget(targetBudgetMs = 50.0, autoThreshold = 100, forceAdaptive = false) {
    const res = await fetch('/api/pipeline/lod_budget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            target_budget_ms: targetBudgetMs,
            auto_activate_population_threshold: autoThreshold,
            force_adaptive: forceAdaptive,
        }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function injectNaturalLanguageScenarioLive(prompt, territoryOverride = null, stepTicksImmediately = 4) {
    const res = await fetch('/api/ai/execution/inject_live', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            prompt,
            territory_override: territoryOverride,
            step_ticks_immediately: stepTicksImmediately,
        }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function runQuickCitizenSimulation(evento, territorio = null, dias = null, conAyuda = null) {
    const res = await fetch('/api/quick/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            evento,
            territorio,
            dias,
            con_ayuda: conAyuda,
            sincronizar_mapa_en_vivo: true,
        }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function inspectExactMapPoint(lat, lon, radiusM = 350.0) {
    const url = `/api/quick/inspect_point?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius_m=${encodeURIComponent(radiusM)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function placeAndSimulatePinpoint(payload) {
    const res = await fetch('/api/quick/pinpoint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function fetchNational262Audit() {
    const res = await fetch('/api/territory/national_audit');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

export async function fetchExternalBacktestSuite(seed = 42) {
    const res = await fetch(`/api/scientific/external_validation/backtest?seed=${encodeURIComponent(seed)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
}

function renderQuickResult(data) {
    const box = document.getElementById('quick-sim-result-box');
    const header = document.getElementById('quick-sim-header');
    const cardsContainer = document.getElementById('quick-sim-cards');
    const summaryEl = document.getElementById('quick-sim-summary');
    if (!box || !header || !cardsContainer || !summaryEl) return;

    box.style.display = 'block';
    const locLabel = data.territorio || (data.ubicacion_exacta ? `${data.ubicacion_exacta.nearest_street_osm} (${data.ubicacion_exacta.district_name})` : '');
    const daysLabel = data.dias_simulados || (data.parametros_especificos ? data.parametros_especificos.dias_simulados : 7);
    header.textContent = `${data.titulo} — ${locLabel} (${daysLabel} días) · ${data.semaforo}`;

    cardsContainer.innerHTML = '';
    for (const c of (data.tarjetas_impacto || [])) {
        const div = document.createElement('div');
        div.style.cssText = 'padding:8px; border-radius:6px; background:rgba(30,41,59,0.85); border:1px solid rgba(148,163,184,0.2);';
        div.innerHTML = `<div style="font-size:11px; opacity:0.8;">${c.icono} ${c.titulo}</div>
                         <div style="font-size:14px; font-weight:700; margin:3px 0;">${c.valor}</div>
                         <div style="font-size:11px; opacity:0.75;">${c.explicacion}</div>`;
        cardsContainer.appendChild(div);
    }
    if (data.reporte_comercial) {
        const rc = data.reporte_comercial;
        const div = document.createElement('div');
        div.style.cssText = 'grid-column: span 2; padding:8px; border-radius:6px; background:rgba(15,118,110,0.25); border:1px solid rgba(45,212,191,0.35);';
        div.innerHTML = `<div style="font-size:11px; opacity:0.85;">🏪 Negocio y Cadena de Abasto Local</div>
                         <div style="font-size:13px; font-weight:700; margin:3px 0;">Caja: $${rc.caja_negocio_local_usd} (${rc.estado_negocio}) · Clientela: ${rc.afluencia_clientes_pct}%</div>
                         <div style="font-size:11px; opacity:0.8;">Proveedor: ${rc.centro_abasto_mayorista} (${rc.distancia_mayorista_km} km · Flete base +${rc.recargo_flete_base_pct}%)</div>`;
        cardsContainer.appendChild(div);
    }
    summaryEl.textContent = data.resumen_sencillo || '';
}

function initQuickSimulatorUI() {
    const btnOpenQuick = document.getElementById('btn-open-quick-sim');
    const modal = document.getElementById('modal-interventions');
    if (btnOpenQuick && modal) {
        btnOpenQuick.addEventListener('click', () => {
            modal.style.display = 'flex';
            const quickTabBtn = modal.querySelector('.modal-tab-btn[data-tab="quick"]');
            if (quickTabBtn) quickTabBtn.click();
        });
    }

    document.querySelectorAll('.quick-preset-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const presetId = btn.getAttribute('data-preset');
            if (!presetId) return;
            btn.disabled = true;
            try {
                const res = await runQuickCitizenSimulation(presetId);
                renderQuickResult(res);
            } catch (err) {
                console.error('Quick preset failed:', err);
            } finally {
                btn.disabled = false;
            }
        });
    });

    const btnRunCustom = document.getElementById('btn-run-quick-sim');
    if (btnRunCustom) {
        btnRunCustom.addEventListener('click', async () => {
            const promptEl = document.getElementById('quick-sim-prompt');
            const terrEl = document.getElementById('quick-sim-territory');
            const daysEl = document.getElementById('quick-sim-days');
            const reliefEl = document.getElementById('quick-sim-relief');

            const evento = promptEl ? promptEl.value.trim() : 'temporal_deslave';
            const territorio = terrEl && terrEl.value.trim() ? terrEl.value.trim() : null;
            const dias = daysEl ? parseInt(daysEl.value, 10) : 5;
            const conAyuda = reliefEl ? Boolean(reliefEl.checked) : false;

            btnRunCustom.disabled = true;
            try {
                const res = await runQuickCitizenSimulation(evento, territorio, dias, conAyuda);
                renderQuickResult(res);
            } catch (err) {
                console.error('Custom quick simulation failed:', err);
            } finally {
                btnRunCustom.disabled = false;
            }
        });
    }

    // Ultra-Precise Map Point Picker & Pinpoint Placement
    const btnPickMap = document.getElementById('btn-pick-map-point');
    if (btnPickMap && modal) {
        btnPickMap.addEventListener('click', () => {
            modal.style.display = 'none';
            const mapArea = document.getElementById('gis-map-container') || document.getElementById('world-canvas') || document.body;
            const prevCursor = mapArea.style.cursor;
            mapArea.style.cursor = 'crosshair';

            const onMapClick = async (ev) => {
                mapArea.style.cursor = prevCursor;
                mapArea.removeEventListener('click', onMapClick, true);

                // Parse latest cursor coordinates from #gis-cursor-coords if available, or compute from click offset
                let lat = 13.69785;
                let lon = -89.19142;
                const coordsHud = document.getElementById('gis-cursor-coords');
                if (coordsHud && coordsHud.textContent) {
                    const m = coordsHud.textContent.match(/([0-9]+\.[0-9]+)°\s*N,\s*(-?[0-9]+\.[0-9]+)°\s*W/);
                    if (m) {
                        lat = parseFloat(m[1]);
                        lon = parseFloat(m[2]);
                    }
                } else {
                    const rect = mapArea.getBoundingClientRect();
                    const rx = Math.max(0, Math.min(1, (ev.clientX - rect.left) / Math.max(1, rect.width)));
                    const ry = Math.max(0, Math.min(1, (ev.clientY - rect.top) / Math.max(1, rect.height)));
                    lat = parseFloat((13.715 - ry * 0.035).toFixed(6));
                    lon = parseFloat((-89.215 + rx * 0.045).toFixed(6));
                }

                const latInput = document.getElementById('pinpoint-lat');
                const lonInput = document.getElementById('pinpoint-lon');
                if (latInput) latInput.value = lat;
                if (lonInput) lonInput.value = lon;

                modal.style.display = 'flex';
                const previewEl = document.getElementById('pinpoint-street-preview');
                try {
                    const info = await inspectExactMapPoint(lat, lon, 350.0);
                    if (previewEl) {
                        previewEl.textContent = `📍 Punto fijo seleccionado: (${info.lat}, ${info.lon}) — ${info.nearest_street_osm} · ${info.district_name} (${info.municipality_name})`;
                    }
                } catch (_e) {
                    if (previewEl) {
                        previewEl.textContent = `📍 Punto fijo seleccionado: (${lat}, ${lon})`;
                    }
                }
            };
            setTimeout(() => mapArea.addEventListener('click', onMapClick, true), 50);
        });
    }

    const btnRunPinpoint = document.getElementById('btn-run-pinpoint-sim');
    if (btnRunPinpoint) {
        btnRunPinpoint.addEventListener('click', async () => {
            const lat = parseFloat((document.getElementById('pinpoint-lat') || {}).value || '13.69785');
            const lon = parseFloat((document.getElementById('pinpoint-lon') || {}).value || '-89.19142');
            const categoria = (document.getElementById('pinpoint-category') || {}).value || 'pupuseria';
            const descripcion = (document.getElementById('pinpoint-desc') || {}).value || 'Pupusería local';
            const precio_usd = parseFloat((document.getElementById('pinpoint-price') || {}).value || '0.85');
            const capital_inicial_usd = parseFloat((document.getElementById('pinpoint-capital') || {}).value || '180');
            const radio_m = parseFloat((document.getElementById('pinpoint-radius') || {}).value || '350');
            const dias = parseInt((document.getElementById('quick-sim-days') || {}).value || '7', 10);

            btnRunPinpoint.disabled = true;
            try {
                const res = await placeAndSimulatePinpoint({
                    lat,
                    lon,
                    categoria,
                    descripcion,
                    precio_usd,
                    capital_inicial_usd,
                    radio_m,
                    dias,
                });
                renderQuickResult(res);
            } catch (err) {
                console.error('Pinpoint placement failed:', err);
            } finally {
                btnRunPinpoint.disabled = false;
            }
        });
    }
}

if (typeof window !== 'undefined') {
    window.SaltborObservatoryV16 = {
        fetchPipelineTelemetry,
        configureAdaptiveLODBudget,
        injectNaturalLanguageScenarioLive,
        runQuickCitizenSimulation,
        inspectExactMapPoint,
        placeAndSimulatePinpoint,
        fetchNational262Audit,
        fetchExternalBacktestSuite,
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initQuickSimulatorUI);
    } else {
        initQuickSimulatorUI();
    }
}
