# ESQUEMA UNIVERSAL DE ESCENARIOS (UNIVERSAL SCENARIO SCHEMA)
## SALTBOR PHASE 1.15 — ESPECIFICACIÓN DECLARATIVA ESTANDARIZADA

Cualquier contingencia o política territorial en SALTBOR se expresa mediante el esquema `TerritorialScenarioDefinition`:

```python
@dataclass
class TerritorialScenarioDefinition:
    scenario_id: str                      # Identificador único inmutable (ej: SCEN_NL_81703_road_landslide)
    name: str                             # Nombre descriptivo para visualización e informes
    description: str                      # Descripción completa o consulta original en lenguaje natural
    department_code: str                  # Código departamental oficial IGN (ej: "04" para Chalatenango)
    municipality_id: str                  # Identificador municipal oficial D.L. 762 (ej: "0402" Chalatenango Centro)
    community_id: str                     # Identificador de comunidad o cantón (ej: "canton_el_rosario")
    is_rural: bool = True                 # Clasificación territorial
    shocks: List[Dict[str, Any]]          # Lista declarativa de eventos exógenos o perturbaciones
    interventions: List[Dict[str, Any]]   # Lista declarativa de intervenciones o políticas públicas
    parameters: Dict[str, Any]            # Parámetros macroeconómicos o ambientales específicos
    duration_ticks: int = 96              # Duración total de la simulación en ticks (mínimo 8)
    random_seeds: List[int]               # Semillas deterministas para reproducción
    hypotheses: List[str]                 # Hipótesis científicas a contrastar
    uncertainties: List[str]              # Incertidumbres detectadas por cobertura de datos
    data_provenance: DataProvenanceTier   # Nivel de evidencia según clasificación oficial
```

---

### Catálogo de Shocks e Intervenciones Reutilizables

#### 1. Tipos de Shocks Soportados (`ShockType`)
- `ROAD_BLOCKAGE_LANDSLIDE`: Deslaves, derrumbes o cortes de paso vial.
- `FLOODING_AGRICULTURE`: Inundaciones y anegamiento de parcelas de cultivo.
- `DROUGHT_CROP_LOSS`: Sequías meteorológicas y canículas prolongadas.
- `FOOD_PRICE_SPIKE`: Choques inflacionarios en precios mayoristas de granos básicos.
- `BUSINESS_CLOSURE`: Cierre temporal de establecimientos comerciales locales.
- `JOB_LOSS_DISPLACEMENT`: Pérdida de empleo estacional o jornalero.
- `HEALTHCARE_CLINIC_OVERLOAD`: Epidemias locales o saturación de unidades de salud.
- `PUBLIC_SERVICE_CUT`: Reducción de suministro hídrico o interrupción de energía eléctrica.

#### 2. Tipos de Intervenciones Soportadas (`InterventionType`)
- `ROAD_REHABILITATION`: Limpieza de derrumbes y reparación de infraestructura vial.
- `EMERGENCY_SCHOOL_TRANSPORT`: Transporte alternativo subsidiado para estudiantes.
- `TARGETED_CASH_TRANSFER`: Bonos monetarios canalizados a hogares vulnerables.
- `TEMPORARY_PRICE_CEILING`: Acuerdos de estabilización de precios en granos básicos.
- `COMMERCIAL_WORKING_CAPITAL_LOAN`: Líneas de liquidez a tienditas para financiar fiado.
- `PUBLIC_WORKFARE_EMPLOYMENT`: Empleo temporal de emergencia en obras comunales.
- `CLINIC_MOBILE_REINFORCEMENT`: Envío de brigadas de salud y dotación de medicamentos.
