import json
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient
from saltbor.visualization.api import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

print("Decisive Acceptance Test: Running end-to-end integration via FastAPI TestClient...")

# 1. Inspect providers status
p_res = client.get('/api/ai/providers/status')
assert p_res.status_code == 200
print('[1/8] AI Providers Status: OFFLINE_DETERMINISTIC available =', p_res.json()['providers']['OFFLINE_DETERMINISTIC']['available'])

# 2. Select a DIFFERENT Salvadoran canton from San Jose Las Flores (e.g. Canton El Rosario)
canton_query = 'Cantón El Rosario'
c_res = client.get(f'/api/ai/territories/coverage?territory={canton_query}')
assert c_res.status_code == 200
cov = c_res.json()
print(f'[2/8] Territory Selected: {cov["name"]} (Quality Score: {cov["data_quality_score"]}, Census: {cov["has_population_census"]})')

# 3. Enter a previously unused natural-language scenario
prompt = 'Simula un bloqueo por deslave de 14 días en el camino rural principal de este cantón. Evalúa cómo impacta la canasta básica de alimentos, la asistencia a clases de los jóvenes y la presión sobre las deudas de fiado.'
print(f'[3/8] Natural Language Input: "{prompt[:60]}..."')

# 4. Let the AI interpret the request and synthesize a structured scenario without Python code
build_res = client.post('/api/ai/scenarios/build_natural_language', json={'prompt': prompt, 'territory_override': canton_query})
assert build_res.status_code == 200
b_data = build_res.json()
scen_id = b_data['scenario_id']
print(f'[4/8] Synthesized Structured Scenario: ID={scen_id}, Ticks={b_data["duration_ticks"]}, Shocks={len(b_data["shocks"])}')

# 5. Validate causal mechanism
v_res = client.post('/api/ai/causal/validate', json={'cause': 'road_interruption', 'effect': 'freight_cost_surge'})
assert v_res.status_code == 200
print(f'[5/8] Causal Mechanism Validation: Status={v_res.json()["status"]}, Engine={v_res.json()["engine"]}')

# 6. Execute scenario via AISimulationExecutionController
exec_res = client.post('/api/ai/execution/run', json={'scenario_id': scen_id, 'seed': 42})
assert exec_res.status_code == 200
e_data = exec_res.json()
assert e_data['status'] == 'completed'
assert e_data['consistency_passed'] is True
print(f'[6/8] Simulation Executed: Status={e_data["status"]}, Duration={e_data["duration_ticks"]} ticks, Time={e_data["execution_time_seconds"]:.4f}s')

# 7. Analyze results with SimulationResultsAnalyst
a_res = client.post('/api/ai/results/analyze', json={'scenario_id': scen_id, 'seed': 42})
assert a_res.status_code == 200
a_data = a_res.json()
print(f'[7/8] Scientific Results Interpretation: {a_data["executive_summary"][:85]}...')
print(f'      Ledger Double-Entry Audit: {a_data["double_entry_ledger_audit"]}')

# 8. Counterfactual comparison with baseline
comp_res = client.get('/api/ai/scenarios/compare_counterfactual')
assert comp_res.status_code == 200
comp_data = comp_res.json()
print(f'[8/8] Counterfactual Comparison: Double-Entry Verified = {comp_data["double_entry_ledger_verified"]}')
print('DECISIVE ACCEPTANCE TEST: 100% SUCCESSFUL ON ALTERNATIVE CANTON WITHOUT PYTHON CODE!')
