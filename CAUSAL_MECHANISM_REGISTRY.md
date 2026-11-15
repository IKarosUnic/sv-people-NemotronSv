# REGISTRO DE MECANISMOS CAUSALES (CAUSAL MECHANISM REGISTRY)
## SALTBOR PHASE 1.15 — CATÁLOGO CIENTÍFICO Y CLASIFICACIÓN EPISTÉMICA

Cada mecanismo causal en SALTBOR define con precisión su causa, efecto, motor computacional responsable, formulación analítica y nivel epistémico:

| Causa | Efecto Intermedio | Efecto Final | Motor Responsable | Formulación / Mecanismo | Estatus Epistémico |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Interrupción Vial** | Fricción topográfica y desvío logístico | Incremento de flete ($c_{\text{delivery}}$) | `CrossDomainInteractionEngine` | $c_{\text{delivery}} = d \cdot c_{\text{base}} \cdot \mu_{\text{friction}}$ | `EXPLICIT_MECHANISM` |
| **Recargo de Flete** | Aumento de costo de adquisición minorista | Inflación minorista en granos básicos | `RegionalEconomicNetworkEngine` | $P_{\text{retail}} = P_{\text{wholesale}} + c_{\text{delivery}} + \text{margin}$ | `EXPLICIT_MECHANISM` |
| **Inflación de Alimentos** | Aumento del gasto básico de la canasta familiar | Drenaje de liquidez y descapitalización | `VerifiableEconomicLedger` | $\Delta \text{Caja}_{\text{hogar}} = - (Q \cdot P_{\text{retail}})$ | `EXPLICIT_MECHANISM` |
| **Déficit de Liquidez** | Agotamiento de ahorros domésticos | Solicitud de crédito informal (*Fiado*) | `HumanBehaviorHeterogeneityEngine` | Transición de estrategia de afrontamiento $L_0 \rightarrow L_2$ | `EMPIRICAL_EVIDENCE` |
| **Fricción Vial** | Incremento de tiempo de traslado escolar | Ausentismo y riesgo de deserción | `PublicServiceCapacityEngine` | Deserción condicionada a fricción y vulnerabilidad económica | `EMPIRICAL_EVIDENCE` |
| **Epidemia / Emergencia** | Sobrecarga de demanda en puesto de salud | Aumento de tiempo de espera en cola | `PublicServiceCapacityEngine` | Modelo de colas $M/M/c$ $(\lambda > c\mu \implies W_q \uparrow)$ | `EXPLICIT_MECHANISM` |
| **Espera Prolongada en Salud** | Demora en tratamiento ambulatorio | Pérdida de jornales por enfermedad | `CrossDomainInteractionEngine` | $\text{Wages}_{\text{lost}} = \text{LostDays} \times w_{\text{daily}}$ | `EXPLICIT_MECHANISM` |

---

### Reglas de Validación Causal en el Asistente de IA

1. Si una relación propuesta coincide con una entrada del registro, se aprueba como `VALIDATED_MECHANISM`.
2. Si una relación es propuesta sin un motor analítico conectado, el `AICausalOrchestrationAssistant` la clasifica obligatoriamente como `HYPOTHESIS_PENDING_VALIDATION`.
3. Si la causa y el efecto son idénticos o forman un ciclo instantáneo no demorado en el mismo tick, se rechaza como `REJECTED_CIRCULAR_OR_UNSUPPORTED`.
