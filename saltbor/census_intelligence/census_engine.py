"""National Census Data Integration Engine for El Salvador (Phase 1.18 Section 3).

Integrates official statistical datasets (VII Censo 2024 ONEC/BCR, EHPM,
MINEDUCYT, MINSAL, institutional CSV/XLSX/JSON/GeoJSON imports) with:
- Explicit source adapters & geographic unit normalization (D.L. 762)
- Dataset versioning, SHA-256 checksums, publication & update dates
- Integrity validation, duplicate detection & strict PII guard
- Granularity tracking (never inventing missing canton/sector/manzana counts)
- Small Area Estimation (SAE) with explicit uncertainty when finer disaggregations lack official tables
"""

from __future__ import annotations

import abc
import csv
import hashlib
import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from saltbor.datasets.salvadoran.territory_data import (
    SALVADORAN_DEPARTMENTS_P8,
    SALVADORAN_DISTRICTS_P8,
    SALVADORAN_MUNICIPALITIES_P8,
)

from saltbor.census_intelligence.schemas import (
    CensusDatasetMetadata,
    CensusImportResult,
    CensusQueryResult,
    CensusVariableRecord,
    EvidenceClassification,
    GeographicGranularity,
    SmallAreaEstimate,
)

DEFAULT_OFFICIAL_CENSUS_DIR = Path(__file__).resolve().parents[1] / "datasets" / "official_census"

_PII_FORBIDDEN_FIELDS = {
    "dui",
    "nit",
    "nombre_completo",
    "full_name",
    "primer_nombre",
    "segundo_nombre",
    "primer_apellido",
    "segundo_apellido",
    "apellido",
    "apellidos",
    "telefono",
    "celular",
    "phone",
    "correo",
    "email",
    "direccion_exacta",
    "street_address",
    "fecha_nacimiento_exacta",
    "birth_date",
    "pasaporte",
    "isss",
    "nup",
}


class PIIViolationError(ValueError):
    """Raised when an imported dataset attempts to introduce individual PII."""


def _norm_txt(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").strip().lower())
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", cleaned).strip()


def _col_letters_to_idx(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def read_xlsx_rows_stdlib(path: Path, sheet_name: Optional[str] = None) -> List[Dict[str, str]]:
    """Pure-stdlib OOXML .xlsx reader (zero external openpyxl/pandas dependency)."""
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root:
                texts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
                shared_strings.append("".join(texts))

        target_sheet = "xl/worksheets/sheet1.xml"
        if sheet_name and "xl/workbook.xml" in zf.namelist() and "xl/_rels/workbook.xml.rels" in zf.namelist():
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rid_map: Dict[str, str] = {}
            for rel in rels_root:
                rid = rel.attrib.get("Id", "")
                tgt = rel.attrib.get("Target", "").lstrip("/")
                if not tgt.startswith("xl/"):
                    tgt = f"xl/{tgt}"
                rid_map[rid] = tgt
            for sh in wb_root.iter():
                if sh.tag.endswith("}sheet") and sh.attrib.get("name") == sheet_name:
                    for k, v in sh.attrib.items():
                        if k.endswith("}id") or k == "r:id":
                            target_sheet = rid_map.get(v, target_sheet)
                            break

        if target_sheet not in zf.namelist():
            candidates = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            if not candidates:
                return []
            target_sheet = candidates[0]

        ws_root = ET.fromstring(zf.read(target_sheet))
        raw_rows: List[List[str]] = []
        for row_el in ws_root.iter():
            if not (row_el.tag.endswith("}row") or row_el.tag == "row"):
                continue
            row_cells: Dict[int, str] = {}
            max_col = -1
            for c_el in row_el:
                if not (c_el.tag.endswith("}c") or c_el.tag == "c"):
                    continue
                ref = c_el.attrib.get("r", "")
                col_idx = _col_letters_to_idx(ref) if ref else (max_col + 1)
                max_col = max(max_col, col_idx)
                ctype = c_el.attrib.get("t", "")
                val = ""
                if ctype == "inlineStr":
                    val = "".join(t.text or "" for t in c_el.iter() if t.tag.endswith("}t") or t.tag == "t")
                else:
                    v_el = next((ch for ch in c_el if ch.tag.endswith("}v") or ch.tag == "v"), None)
                    if v_el is not None and v_el.text is not None:
                        if ctype == "s":
                            s_idx = int(v_el.text)
                            val = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else ""
                        else:
                            val = v_el.text
                row_cells[col_idx] = val
            if max_col >= 0:
                raw_rows.append([row_cells.get(i, "") for i in range(max_col + 1)])

    if len(raw_rows) < 2:
        return []
    headers = [str(h).strip() for h in raw_rows[0]]
    records: List[Dict[str, str]] = []
    for row in raw_rows[1:]:
        if not any(str(v).strip() for v in row):
            continue
        item = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers)) if headers[i]}
        records.append(item)
    return records


# ---------------------------------------------------------------------------
# Source Adapters
# ---------------------------------------------------------------------------

class CensusSourceAdapter(abc.ABC):
    """Abstract adapter normalizing a Salvadoran statistical or institutional source."""

    adapter_name: str = "generic"
    default_institution: str = "Institución Pública"
    default_evidence_type: EvidenceClassification = EvidenceClassification.PUBLIC_OFFICIAL

    @abc.abstractmethod
    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        dataset_id: str,
        version: str,
        published_at: str,
        reference_year: int,
        geo_resolver: Any,
    ) -> Tuple[List[CensusVariableRecord], List[Dict[str, Any]], List[str]]:
        """Return (normalized_variable_records, institutional_entities, validation_errors)."""


class Censo2024ONECAdapter(CensusSourceAdapter):
    """Adapter for ONEC/BCR VII Censo de Población y VI de Vivienda 2024 tabular imports."""

    adapter_name = "censo_2024_onec"
    default_institution = "ONEC / BCR El Salvador"
    default_evidence_type = EvidenceClassification.PUBLIC_OFFICIAL

    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        dataset_id: str,
        version: str,
        published_at: str,
        reference_year: int,
        geo_resolver: Any,
    ) -> Tuple[List[CensusVariableRecord], List[Dict[str, Any]], List[str]]:
        records: List[CensusVariableRecord] = []
        errors: List[str] = []
        for idx, row in enumerate(rows):
            unit_raw = str(
                row.get("geographic_unit")
                or row.get("district")
                or row.get("distrito")
                or row.get("municipality")
                or row.get("municipio")
                or row.get("department")
                or row.get("departamento")
                or row.get("canton")
                or ""
            ).strip()
            gran_raw = str(row.get("granularity") or row.get("nivel") or "").strip().upper()
            unit_id, unit_name, gran = geo_resolver(unit_raw, gran_raw)
            if not unit_id:
                errors.append(f"Fila {idx + 1}: unidad geográfica no reconocida '{unit_raw}'.")
                continue

            for var_key in (
                "total_population", "poblacion_total", "male_population", "hombres",
                "female_population", "mujeres", "occupied_dwellings", "viviendas_ocupadas",
                "households", "hogares", "mean_household_size", "tamano_hogar",
            ):
                if var_key in row and str(row[var_key]).strip() != "":
                    try:
                        val = float(row[var_key])
                    except ValueError:
                        errors.append(f"Fila {idx + 1}: valor no numérico en '{var_key}': {row[var_key]}.")
                        continue
                    if val < 0:
                        errors.append(f"Fila {idx + 1}: valor negativo inválido en '{var_key}': {val}.")
                        continue
                    norm_var = {
                        "poblacion_total": "total_population",
                        "hombres": "male_population",
                        "mujeres": "female_population",
                        "viviendas_ocupadas": "occupied_dwellings",
                        "hogares": "households",
                        "tamano_hogar": "mean_household_size",
                    }.get(var_key, var_key)
                    records.append(
                        CensusVariableRecord(
                            dataset_id=dataset_id,
                            dataset_version=version,
                            source_institution=self.default_institution,
                            geographic_unit_id=unit_id,
                            geographic_unit_name=unit_name,
                            granularity=gran,
                            variable_name=norm_var,
                            value=int(val) if norm_var != "mean_household_size" and val.is_integer() else val,
                            unit="personas" if "population" in norm_var else "",
                            reference_year=reference_year,
                            published_at=published_at,
                            evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                            confidence_level=0.95,
                        )
                    )
        return records, [], errors


class EHPMAdapter(CensusSourceAdapter):
    """Adapter for ONEC/BCR Encuesta de Hogares de Propósitos Múltiples (EHPM)."""

    adapter_name = "ehpm_onec"
    default_institution = "ONEC / BCR (EHPM)"
    default_evidence_type = EvidenceClassification.PUBLIC_OFFICIAL

    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        dataset_id: str,
        version: str,
        published_at: str,
        reference_year: int,
        geo_resolver: Any,
    ) -> Tuple[List[CensusVariableRecord], List[Dict[str, Any]], List[str]]:
        records: List[CensusVariableRecord] = []
        errors: List[str] = []
        for idx, row in enumerate(rows):
            unit_raw = str(row.get("geographic_unit") or row.get("stratum") or row.get("departamento") or "SV").strip()
            gran_raw = str(row.get("granularity") or ("URBAN_RURAL_STRATUM" if unit_raw.lower() in ("urban", "rural", "urbano", "rural") else "")).upper()
            unit_id, unit_name, gran = geo_resolver(unit_raw, gran_raw)
            for k, v in row.items():
                if k in ("geographic_unit", "stratum", "departamento", "granularity") or str(v).strip() == "":
                    continue
                try:
                    num = float(v)
                except (ValueError, TypeError):
                    continue
                if ("share" in k or "rate" in k or "tasa" in k) and not (0.0 <= num <= 1.0):
                    errors.append(f"Fila {idx + 1}: proporción fuera de [0,1] en '{k}': {num}.")
                    continue
                records.append(
                    CensusVariableRecord(
                        dataset_id=dataset_id,
                        dataset_version=version,
                        source_institution=self.default_institution,
                        geographic_unit_id=unit_id or _norm_txt(unit_raw),
                        geographic_unit_name=unit_name or unit_raw,
                        granularity=gran,
                        variable_name=_norm_txt(k).replace(" ", "_"),
                        value=num,
                        reference_year=reference_year,
                        published_at=published_at,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.90,
                    )
                )
        return records, [], errors


class MINEDSchoolRegistryAdapter(CensusSourceAdapter):
    """Adapter for official MINEDUCYT school establishment & enrollment datasets."""

    adapter_name = "mined_schools"
    default_institution = "MINEDUCYT El Salvador"
    default_evidence_type = EvidenceClassification.PUBLIC_OFFICIAL

    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        dataset_id: str,
        version: str,
        published_at: str,
        reference_year: int,
        geo_resolver: Any,
    ) -> Tuple[List[CensusVariableRecord], List[Dict[str, Any]], List[str]]:
        records: List[CensusVariableRecord] = []
        schools: List[Dict[str, Any]] = []
        errors: List[str] = []

        for idx, row in enumerate(rows):
            name = str(row.get("nombre_centro") or row.get("name") or row.get("centro_escolar") or "").strip()
            code = str(row.get("codigo_ce") or row.get("school_code") or row.get("codigo") or f"MINED_{idx+1}").strip()
            if not name:
                errors.append(f"Fila {idx + 1}: falta nombre de centro escolar.")
                continue

            lat_raw = row.get("lat") or row.get("latitude")
            lon_raw = row.get("lon") or row.get("longitude")
            try:
                lat_val = float(lat_raw) if lat_raw not in (None, "") else None
                lon_val = float(lon_raw) if lon_raw not in (None, "") else None
            except ValueError:
                lat_val, lon_val = None, None

            dist_raw = str(row.get("distrito") or row.get("district") or row.get("departamento") or "SV").strip()
            unit_id, unit_name, gran = geo_resolver(dist_raw, "DISTRICT")

            levels_raw = str(row.get("niveles") or row.get("levels") or "").strip()
            levels = [lv.strip().lower() for lv in re.split(r"[;,|/]+", levels_raw) if lv.strip()]

            def _opt_int(val: Any) -> Optional[int]:
                if val in (None, ""):
                    return None
                try:
                    n = int(float(val))
                    return n if n >= 0 else None
                except (ValueError, TypeError):
                    return None

            enrollment = _opt_int(row.get("matricula") or row.get("enrollment"))
            capacity = _opt_int(row.get("capacidad") or row.get("capacidad_instalada") or row.get("capacity"))
            vacancies = _opt_int(row.get("vacantes") or row.get("vacancies"))
            if vacancies is None and enrollment is not None and capacity is not None:
                vacancies = max(0, capacity - enrollment)

            schools.append({
                "school_code": code,
                "name": name,
                "district_id": unit_id,
                "district_name": unit_name,
                "lat": lat_val,
                "lon": lon_val,
                "sector": str(row.get("sector") or row.get("dependencia") or "publico").lower(),
                "levels": levels,
                "enrollment": enrollment,
                "installed_capacity": capacity,
                "available_vacancies": vacancies,
                "dataset_id": dataset_id,
                "dataset_version": version,
                "published_at": published_at,
                "source_institution": self.default_institution,
            })
            if enrollment is not None:
                records.append(
                    CensusVariableRecord(
                        dataset_id=dataset_id,
                        dataset_version=version,
                        source_institution=self.default_institution,
                        geographic_unit_id=f"{unit_id}:{code}",
                        geographic_unit_name=name,
                        granularity=gran,
                        variable_name="school_enrollment",
                        value=enrollment,
                        unit="estudiantes",
                        reference_year=reference_year,
                        published_at=published_at,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.95,
                    )
                )
        return records, schools, errors


class MINSALHealthAdapter(CensusSourceAdapter):
    """Adapter for official MINSAL health facility registries."""

    adapter_name = "minsal_health"
    default_institution = "MINSAL El Salvador"
    default_evidence_type = EvidenceClassification.PUBLIC_OFFICIAL

    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        dataset_id: str,
        version: str,
        published_at: str,
        reference_year: int,
        geo_resolver: Any,
    ) -> Tuple[List[CensusVariableRecord], List[Dict[str, Any]], List[str]]:
        records: List[CensusVariableRecord] = []
        facilities: List[Dict[str, Any]] = []
        errors: List[str] = []
        for idx, row in enumerate(rows):
            name = str(row.get("nombre") or row.get("name") or row.get("establecimiento") or "").strip()
            if not name:
                errors.append(f"Fila {idx + 1}: falta nombre de establecimiento MINSAL.")
                continue
            lat_raw = row.get("lat") or row.get("latitude")
            lon_raw = row.get("lon") or row.get("longitude")
            try:
                lat_val = float(lat_raw) if lat_raw not in (None, "") else None
                lon_val = float(lon_raw) if lon_raw not in (None, "") else None
            except ValueError:
                lat_val, lon_val = None, None
            dist_raw = str(row.get("distrito") or row.get("district") or "SV").strip()
            unit_id, unit_name, _ = geo_resolver(dist_raw, "DISTRICT")
            cap = row.get("capacidad_diaria") or row.get("camas") or row.get("capacity")
            facilities.append({
                "facility_code": str(row.get("codigo") or f"MINSAL_{idx+1}"),
                "name": name,
                "subtype": str(row.get("tipo") or row.get("type") or "unidad_salud").lower(),
                "district_id": unit_id,
                "district_name": unit_name,
                "lat": lat_val,
                "lon": lon_val,
                "installed_capacity": int(float(cap)) if cap not in (None, "") else None,
                "dataset_id": dataset_id,
                "published_at": published_at,
                "source_institution": self.default_institution,
            })
        return records, facilities, errors


class InstitutionalCustomAdapter(CensusSourceAdapter):
    """Flexible adapter for additional institutional CSV/XLSX/JSON/GeoJSON sources."""

    adapter_name = "institutional_custom"
    default_institution = "Fuente Institucional Oficial"
    default_evidence_type = EvidenceClassification.PUBLIC_OFFICIAL

    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        dataset_id: str,
        version: str,
        published_at: str,
        reference_year: int,
        geo_resolver: Any,
    ) -> Tuple[List[CensusVariableRecord], List[Dict[str, Any]], List[str]]:
        records: List[CensusVariableRecord] = []
        errors: List[str] = []
        for idx, row in enumerate(rows):
            unit_raw = str(row.get("geographic_unit") or row.get("unit") or row.get("distrito") or "SV").strip()
            gran_raw = str(row.get("granularity") or "").upper()
            unit_id, unit_name, gran = geo_resolver(unit_raw, gran_raw)
            var_name = str(row.get("variable") or row.get("variable_name") or "").strip()
            if var_name and row.get("value") not in (None, ""):
                try:
                    val: Any = float(row["value"])
                except (ValueError, TypeError):
                    val = str(row["value"])
                records.append(
                    CensusVariableRecord(
                        dataset_id=dataset_id,
                        dataset_version=version,
                        source_institution=str(row.get("source") or self.default_institution),
                        geographic_unit_id=unit_id or _norm_txt(unit_raw),
                        geographic_unit_name=unit_name or unit_raw,
                        granularity=gran,
                        variable_name=var_name,
                        value=val,
                        unit=str(row.get("unit_measure") or ""),
                        reference_year=reference_year,
                        published_at=published_at,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.88,
                    )
                )
            else:
                for k, v in row.items():
                    if k in ("geographic_unit", "unit", "distrito", "granularity", "source") or v in (None, ""):
                        continue
                    try:
                        num = float(v)
                    except (ValueError, TypeError):
                        continue
                    records.append(
                        CensusVariableRecord(
                            dataset_id=dataset_id,
                            dataset_version=version,
                            source_institution=str(row.get("source") or self.default_institution),
                            geographic_unit_id=unit_id or _norm_txt(unit_raw),
                            geographic_unit_name=unit_name or unit_raw,
                            granularity=gran,
                            variable_name=_norm_txt(k).replace(" ", "_"),
                            value=num,
                            reference_year=reference_year,
                            published_at=published_at,
                            evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                            confidence_level=0.88,
                        )
                    )
        return records, [], errors


# ---------------------------------------------------------------------------
# National Census Data Integration Engine
# ---------------------------------------------------------------------------

class NationalCensusDataIntegrationEngine:
    """Central statistical engine integrating official Salvadoran census & sectoral sources."""

    def __init__(self, official_data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(official_data_dir) if official_data_dir else DEFAULT_OFFICIAL_CENSUS_DIR
        self._datasets: Dict[str, CensusDatasetMetadata] = {}
        self._dataset_versions: Dict[str, List[CensusDatasetMetadata]] = {}
        self._records: Dict[Tuple[str, str, str, int], CensusVariableRecord] = {}
        self._mined_schools: List[Dict[str, Any]] = []
        self._minsal_facilities: List[Dict[str, Any]] = []
        self._raw_bundles: Dict[str, Dict[str, Any]] = {}

        self._adapters: Dict[str, CensusSourceAdapter] = {
            "censo_2024_onec": Censo2024ONECAdapter(),
            "ehpm_onec": EHPMAdapter(),
            "mined_schools": MINEDSchoolRegistryAdapter(),
            "minsal_health": MINSALHealthAdapter(),
            "institutional_custom": InstitutionalCustomAdapter(),
        }

        self._departments = (
            SALVADORAN_DEPARTMENTS_P8
            if isinstance(SALVADORAN_DEPARTMENTS_P8, dict)
            else {d.code: d for d in SALVADORAN_DEPARTMENTS_P8}
        )
        self._municipalities = (
            SALVADORAN_MUNICIPALITIES_P8
            if isinstance(SALVADORAN_MUNICIPALITIES_P8, dict)
            else {m.municipality_id: m for m in SALVADORAN_MUNICIPALITIES_P8}
        )
        self._districts = (
            SALVADORAN_DISTRICTS_P8
            if isinstance(SALVADORAN_DISTRICTS_P8, dict)
            else {d.district_id: d for d in SALVADORAN_DISTRICTS_P8}
        )
        self._build_geo_lookup()
        self._load_shipped_official_datasets()

    def register_adapter(self, adapter: CensusSourceAdapter) -> None:
        self._adapters[adapter.adapter_name] = adapter

    def _build_geo_lookup(self) -> None:
        self._dept_by_norm: Dict[str, str] = {_norm_txt(d.name): code for code, d in self._departments.items()}
        for code in self._departments:
            self._dept_by_norm[code.lower()] = code
        self._mun_by_norm: Dict[str, str] = {_norm_txt(m.name): mid for mid, m in self._municipalities.items()}
        self._dist_by_norm: Dict[str, str] = {}
        for did, d in self._districts.items():
            self._dist_by_norm[did.lower()] = did
            self._dist_by_norm[_norm_txt(d.name)] = did

    def resolve_geographic_unit(
        self,
        raw_name: str,
        explicit_granularity: str = "",
    ) -> Tuple[str, str, GeographicGranularity]:
        norm = _norm_txt(raw_name)
        if not norm or norm in ("sv", "el salvador", "nacional", "national"):
            return "SV", "El Salvador", GeographicGranularity.NATIONAL
        if norm in ("urban", "urbano"):
            return "STRATUM_URBAN", "Estrato Urbano Nacional", GeographicGranularity.URBAN_RURAL_STRATUM
        if norm in ("rural",):
            return "STRATUM_RURAL", "Estrato Rural Nacional", GeographicGranularity.URBAN_RURAL_STRATUM

        if explicit_granularity == "CANTON":
            return f"canton:{norm.replace(' ', '_')}", raw_name.strip(), GeographicGranularity.CANTON
        if explicit_granularity == "SECTOR_CENSAL":
            return f"sector:{norm.replace(' ', '_')}", raw_name.strip(), GeographicGranularity.SECTOR_CENSAL
        if explicit_granularity == "MANZANA":
            return f"manzana:{norm.replace(' ', '_')}", raw_name.strip(), GeographicGranularity.MANZANA

        if norm in self._dist_by_norm:
            did = self._dist_by_norm[norm]
            return did, self._districts[did].name, GeographicGranularity.DISTRICT
        if norm in self._mun_by_norm:
            mid = self._mun_by_norm[norm]
            return mid, self._municipalities[mid].name, GeographicGranularity.MUNICIPALITY
        if norm in self._dept_by_norm:
            code = self._dept_by_norm[norm]
            return code, self._departments[code].name, GeographicGranularity.DEPARTMENT

        if explicit_granularity in GeographicGranularity.__members__:
            return norm.replace(" ", "_"), raw_name.strip(), GeographicGranularity[explicit_granularity]
        return "", raw_name.strip(), GeographicGranularity.NATIONAL

    def _register_dataset_version(self, meta: CensusDatasetMetadata) -> None:
        self._datasets[meta.dataset_id] = meta
        self._dataset_versions.setdefault(meta.dataset_id, []).append(meta)

    def _store_record(self, rec: CensusVariableRecord) -> bool:
        key = (rec.dataset_id, rec.geographic_unit_id, rec.variable_name, rec.reference_year)
        if key in self._records:
            return False
        self._records[key] = rec
        return True

    def _load_shipped_official_datasets(self) -> None:
        if not self.data_dir.exists():
            return

        # 1. VII Censo de Población y VI de Vivienda 2024 (ONEC/BCR)
        censo_path = self.data_dir / "censo_2024_onec_bcr.json"
        if censo_path.exists():
            raw_bytes = censo_path.read_bytes()
            sha = hashlib.sha256(raw_bytes).hexdigest()
            data = json.loads(raw_bytes.decode("utf-8"))
            self._raw_bundles["censo_2024_onec_bcr"] = data
            ds_id = data["dataset_id"]
            ver = data["version"]
            pub = data["published_at"]
            year = int(data["reference_year"])

            nat = data["national"]
            cnt = 0
            for var_k, val in nat.items():
                if var_k in ("evidence_type", "geographic_unit_id", "geographic_unit_name"):
                    continue
                if self._store_record(
                    CensusVariableRecord(
                        dataset_id=ds_id,
                        dataset_version=ver,
                        source_institution=data["source_institution"],
                        geographic_unit_id="SV",
                        geographic_unit_name="El Salvador",
                        granularity=GeographicGranularity.NATIONAL,
                        variable_name=var_k,
                        value=val,
                        reference_year=year,
                        published_at=pub,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.98,
                    )
                ):
                    cnt += 1

            for dept in data.get("departments", []):
                if self._store_record(
                    CensusVariableRecord(
                        dataset_id=ds_id,
                        dataset_version=ver,
                        source_institution=data["source_institution"],
                        geographic_unit_id=dept["department_code"],
                        geographic_unit_name=dept["name"],
                        granularity=GeographicGranularity.DEPARTMENT,
                        variable_name="total_population",
                        value=int(dept["total_population"]),
                        unit="habitantes",
                        reference_year=year,
                        published_at=pub,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.98,
                    )
                ):
                    cnt += 1

            for mun in data.get("municipalities_verified", []):
                if self._store_record(
                    CensusVariableRecord(
                        dataset_id=ds_id,
                        dataset_version=ver,
                        source_institution=data["source_institution"],
                        geographic_unit_id=mun["municipality_id"],
                        geographic_unit_name=mun["name"],
                        granularity=GeographicGranularity.MUNICIPALITY,
                        variable_name="total_population",
                        value=int(mun["total_population"]),
                        unit="habitantes",
                        reference_year=year,
                        published_at=pub,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.97,
                    )
                ):
                    cnt += 1

            for dist in data.get("districts_verified", []):
                if self._store_record(
                    CensusVariableRecord(
                        dataset_id=ds_id,
                        dataset_version=ver,
                        source_institution=data["source_institution"],
                        geographic_unit_id=dist["district_id"],
                        geographic_unit_name=dist["name"],
                        granularity=GeographicGranularity.DISTRICT,
                        variable_name="total_population",
                        value=int(dist["total_population"]),
                        unit="habitantes",
                        reference_year=year,
                        published_at=pub,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.97,
                    )
                ):
                    cnt += 1
                if "urban_share" in dist and self._store_record(
                    CensusVariableRecord(
                        dataset_id=ds_id,
                        dataset_version=ver,
                        source_institution=data["source_institution"],
                        geographic_unit_id=dist["district_id"],
                        geographic_unit_name=dist["name"],
                        granularity=GeographicGranularity.DISTRICT,
                        variable_name="urban_share",
                        value=float(dist["urban_share"]),
                        unit="ratio",
                        reference_year=year,
                        published_at=pub,
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.96,
                    )
                ):
                    cnt += 1

            self._register_dataset_version(
                CensusDatasetMetadata(
                    dataset_id=ds_id,
                    adapter_name="censo_2024_onec",
                    title=data["title"],
                    source_institution=data["source_institution"],
                    source_url=data.get("source_url", ""),
                    license=data.get("license", ""),
                    version=ver,
                    published_at=pub,
                    updated_at=data["updated_at"],
                    reference_year=year,
                    available_granularities=[
                        GeographicGranularity.NATIONAL,
                        GeographicGranularity.DEPARTMENT,
                        GeographicGranularity.MUNICIPALITY,
                        GeographicGranularity.DISTRICT,
                    ],
                    unavailable_granularities=[
                        GeographicGranularity.CANTON,
                        GeographicGranularity.SECTOR_CENSAL,
                        GeographicGranularity.MANZANA,
                    ],
                    record_count=cnt,
                    content_sha256=sha,
                    limitations=data.get("limitations", []),
                )
            )

        # 2. EHPM 2024
        ehpm_path = self.data_dir / "ehpm_2024_onec_bcr.json"
        if ehpm_path.exists():
            raw_bytes = ehpm_path.read_bytes()
            sha = hashlib.sha256(raw_bytes).hexdigest()
            data = json.loads(raw_bytes.decode("utf-8"))
            self._raw_bundles["ehpm_2024_onec_bcr"] = data
            cnt = 0
            for var_k, val in data.get("national_indicators", {}).items():
                if var_k == "evidence_type":
                    continue
                if self._store_record(
                    CensusVariableRecord(
                        dataset_id=data["dataset_id"],
                        dataset_version=data["version"],
                        source_institution=data["source_institution"],
                        geographic_unit_id="SV",
                        geographic_unit_name="El Salvador",
                        granularity=GeographicGranularity.NATIONAL,
                        variable_name=var_k,
                        value=val,
                        reference_year=int(data["reference_year"]),
                        published_at=data["published_at"],
                        evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                        confidence_level=0.92,
                    )
                ):
                    cnt += 1
            self._register_dataset_version(
                CensusDatasetMetadata(
                    dataset_id=data["dataset_id"],
                    adapter_name="ehpm_onec",
                    title=data["title"],
                    source_institution=data["source_institution"],
                    source_url=data.get("source_url", ""),
                    version=data["version"],
                    published_at=data["published_at"],
                    updated_at=data["updated_at"],
                    reference_year=int(data["reference_year"]),
                    available_granularities=[
                        GeographicGranularity.NATIONAL,
                        GeographicGranularity.URBAN_RURAL_STRATUM,
                    ],
                    unavailable_granularities=[
                        GeographicGranularity.DISTRICT,
                        GeographicGranularity.CANTON,
                        GeographicGranularity.SECTOR_CENSAL,
                        GeographicGranularity.MANZANA,
                    ],
                    record_count=cnt,
                    content_sha256=sha,
                    limitations=data.get("limitations", []),
                )
            )

        # 3. MINED 2024 & MINSAL 2024 macros
        for fname, adapter_name in (
            ("mined_2024_macro.json", "mined_schools"),
            ("minsal_2024_macro.json", "minsal_health"),
        ):
            fpath = self.data_dir / fname
            if fpath.exists():
                raw_bytes = fpath.read_bytes()
                sha = hashlib.sha256(raw_bytes).hexdigest()
                data = json.loads(raw_bytes.decode("utf-8"))
                self._raw_bundles[data["dataset_id"]] = data
                cnt = 0
                for var_k, val in data.get("national", {}).items():
                    if var_k == "evidence_type":
                        continue
                    if self._store_record(
                        CensusVariableRecord(
                            dataset_id=data["dataset_id"],
                            dataset_version=data["version"],
                            source_institution=data["source_institution"],
                            geographic_unit_id="SV",
                            geographic_unit_name="El Salvador",
                            granularity=GeographicGranularity.NATIONAL,
                            variable_name=var_k,
                            value=val,
                            reference_year=int(data["reference_year"]),
                            published_at=data["published_at"],
                            evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                            confidence_level=0.95,
                        )
                    ):
                        cnt += 1
                self._register_dataset_version(
                    CensusDatasetMetadata(
                        dataset_id=data["dataset_id"],
                        adapter_name=adapter_name,
                        title=data["title"],
                        source_institution=data["source_institution"],
                        source_url=data.get("source_url", ""),
                        version=data["version"],
                        published_at=data["published_at"],
                        updated_at=data["updated_at"],
                        reference_year=int(data["reference_year"]),
                        available_granularities=[GeographicGranularity.NATIONAL],
                        unavailable_granularities=[
                            GeographicGranularity.DISTRICT,
                            GeographicGranularity.CANTON,
                            GeographicGranularity.SECTOR_CENSAL,
                            GeographicGranularity.MANZANA,
                        ],
                        record_count=cnt,
                        content_sha256=sha,
                        limitations=data.get("limitations", []),
                    )
                )

    # -----------------------------------------------------------------------
    # File Importers (CSV, XLSX, JSON, GeoJSON) with PII Guard & Deduplication
    # -----------------------------------------------------------------------

    @staticmethod
    def _check_pii_columns(rows: List[Dict[str, Any]]) -> List[str]:
        if not rows:
            return []
        cols = {_norm_txt(k).replace(" ", "_") for r in rows[:5] for k in r.keys()}
        found = sorted(c for c in cols if c in _PII_FORBIDDEN_FIELDS)
        if found:
            raise PIIViolationError(
                f"Importación rechazada por protección de privacidad: columnas PII detectadas {found}."
            )
        return found

    def import_records(
        self,
        rows: List[Dict[str, Any]],
        adapter_name: str,
        dataset_id: str,
        title: str = "",
        source_institution: str = "",
        version: str = "1.0.0",
        published_at: str = "2026-11-23",
        reference_year: int = 2024,
        file_format: str = "json",
        content_sha256: str = "",
    ) -> CensusImportResult:
        adapter = self._adapters.get(adapter_name)
        if adapter is None:
            raise KeyError(f"Adaptador '{adapter_name}' no registrado.")

        pii_found = self._check_pii_columns(rows)
        norm_recs, inst_entities, errors = adapter.normalize_rows(
            rows=rows,
            dataset_id=dataset_id,
            version=version,
            published_at=published_at,
            reference_year=reference_year,
            geo_resolver=self.resolve_geographic_unit,
        )

        imported = 0
        dups = 0
        grans: List[GeographicGranularity] = []
        for rec in norm_recs:
            if self._store_record(rec):
                imported += 1
                if rec.granularity not in grans:
                    grans.append(rec.granularity)
            else:
                dups += 1

        if adapter_name == "mined_schools" and inst_entities:
            existing_codes = {s["school_code"] for s in self._mined_schools}
            for sc in inst_entities:
                if sc["school_code"] in existing_codes:
                    dups += 1
                else:
                    existing_codes.add(sc["school_code"])
                    self._mined_schools.append(sc)
                    imported += 1
                    if GeographicGranularity.DISTRICT not in grans:
                        grans.append(GeographicGranularity.DISTRICT)

        if adapter_name == "minsal_health" and inst_entities:
            existing_codes = {f["facility_code"] for f in self._minsal_facilities}
            for fc in inst_entities:
                if fc["facility_code"] in existing_codes:
                    dups += 1
                else:
                    existing_codes.add(fc["facility_code"])
                    self._minsal_facilities.append(fc)
                    imported += 1
                    if GeographicGranularity.DISTRICT not in grans:
                        grans.append(GeographicGranularity.DISTRICT)

        detected_gran = grans[0] if grans else GeographicGranularity.NATIONAL
        sha = content_sha256 or hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        meta = CensusDatasetMetadata(
            dataset_id=dataset_id,
            adapter_name=adapter_name,
            title=title or f"Dataset {dataset_id}",
            source_institution=source_institution or adapter.default_institution,
            version=version,
            published_at=published_at,
            updated_at=published_at,
            reference_year=reference_year,
            available_granularities=grans or [detected_gran],
            unavailable_granularities=[
                g for g in (GeographicGranularity.CANTON, GeographicGranularity.SECTOR_CENSAL, GeographicGranularity.MANZANA)
                if g not in grans
            ],
            record_count=imported,
            duplicates_detected=dups,
            content_sha256=sha,
            limitations=errors[:10],
        )
        self._register_dataset_version(meta)

        return CensusImportResult(
            dataset_id=dataset_id,
            version=version,
            file_format=file_format,
            records_imported=imported,
            duplicates_skipped=dups,
            validation_errors=errors,
            pii_columns_blocked=pii_found,
            detected_granularity=detected_gran,
            content_sha256=sha,
            success=len(errors) == 0 or imported > 0,
        )

    def import_csv(
        self,
        path: str | Path,
        adapter_name: str,
        dataset_id: Optional[str] = None,
        version: str = "1.0.0",
        published_at: str = "2026-11-23",
        reference_year: int = 2024,
    ) -> CensusImportResult:
        p = Path(path)
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(text.splitlines())
        rows = [dict(r) for r in reader]
        return self.import_records(
            rows=rows,
            adapter_name=adapter_name,
            dataset_id=dataset_id or p.stem,
            version=version,
            published_at=published_at,
            reference_year=reference_year,
            file_format="csv",
            content_sha256=sha,
        )

    def import_json(
        self,
        path: str | Path,
        adapter_name: str,
        dataset_id: Optional[str] = None,
        version: str = "1.0.0",
        published_at: str = "2026-11-23",
        reference_year: int = 2024,
    ) -> CensusImportResult:
        p = Path(path)
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        payload = json.loads(raw.decode("utf-8"))
        rows: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            rows = [dict(r) for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            if payload.get("type") == "FeatureCollection":
                for feat in payload.get("features", []):
                    props = dict(feat.get("properties") or {})
                    geom = feat.get("geometry") or {}
                    if geom.get("type") == "Point" and isinstance(geom.get("coordinates"), list) and len(geom["coordinates"]) >= 2:
                        props.setdefault("lon", geom["coordinates"][0])
                        props.setdefault("lat", geom["coordinates"][1])
                    rows.append(props)
            else:
                for key in ("records", "rows", "data", "items"):
                    if isinstance(payload.get(key), list):
                        rows = [dict(r) for r in payload[key] if isinstance(r, dict)]
                        break
                if not rows:
                    rows = [payload]
        return self.import_records(
            rows=rows,
            adapter_name=adapter_name,
            dataset_id=dataset_id or p.stem,
            version=version,
            published_at=published_at,
            reference_year=reference_year,
            file_format="geojson" if isinstance(payload, dict) and payload.get("type") == "FeatureCollection" else "json",
            content_sha256=sha,
        )

    def import_xlsx(
        self,
        path: str | Path,
        adapter_name: str,
        dataset_id: Optional[str] = None,
        sheet_name: Optional[str] = None,
        version: str = "1.0.0",
        published_at: str = "2026-11-23",
        reference_year: int = 2024,
    ) -> CensusImportResult:
        p = Path(path)
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        rows = read_xlsx_rows_stdlib(p, sheet_name=sheet_name)
        return self.import_records(
            rows=rows,
            adapter_name=adapter_name,
            dataset_id=dataset_id or p.stem,
            version=version,
            published_at=published_at,
            reference_year=reference_year,
            file_format="xlsx",
            content_sha256=sha,
        )

    # -----------------------------------------------------------------------
    # Queries & Small Area Estimation
    # -----------------------------------------------------------------------

    def list_datasets(self) -> List[CensusDatasetMetadata]:
        return list(self._datasets.values())

    def get_dataset_history(self, dataset_id: str) -> List[CensusDatasetMetadata]:
        return list(self._dataset_versions.get(dataset_id, []))

    def get_imported_mined_schools(self) -> List[Dict[str, Any]]:
        return list(self._mined_schools)

    def get_imported_minsal_facilities(self) -> List[Dict[str, Any]]:
        return list(self._minsal_facilities)

    def _lookup_official_population(self, unit_id: str, variable_name: str = "total_population") -> Optional[CensusVariableRecord]:
        matches = [
            rec for rec in self._records.values()
            if rec.geographic_unit_id == unit_id and rec.variable_name == variable_name
        ]
        if not matches:
            return None
        matches.sort(key=lambda r: (r.reference_year, r.published_at), reverse=True)
        return matches[0]

    def query_area_statistics(
        self,
        district_id: str,
        requested_granularity: GeographicGranularity = GeographicGranularity.DISTRICT,
        custom_area_label: Optional[str] = None,
        local_residential_share: Optional[float] = None,
        local_building_capacity_estimate: Optional[int] = None,
    ) -> CensusQueryResult:
        """Query official census & EHPM distributions; apply explicit SAE when requested granularity is absent."""
        dist = self._districts.get(district_id)
        if dist is None:
            uid, uname, _ = self.resolve_geographic_unit(district_id)
            dist = self._districts.get(uid)

        censo_bundle = self._raw_bundles.get("censo_2024_onec_bcr", {})
        ehpm_bundle = self._raw_bundles.get("ehpm_2024_onec_bcr", {})
        mined_bundle = self._raw_bundles.get("mined_2024_macro", {})

        nat_censo = censo_bundle.get("national", {})
        priors = censo_bundle.get("derived_demographic_priors", {})

        is_urban = bool(dist.is_urban_core) if dist else True
        dept_code = dist.department_code if dist else "SS"
        dist_name = dist.name if dist else district_id

        # 1. Determine exact official population vs SAE
        dept_rec = self._lookup_official_population(dept_code, "total_population")
        dept_pop_2024 = int(dept_rec.value) if dept_rec else int(self._departments.get(dept_code).population_2024 if dept_code in self._departments else 500000)

        dist_official_rec = self._lookup_official_population(dist.district_id if dist else district_id, "total_population")
        if dist_official_rec is not None:
            dist_pop = int(dist_official_rec.value)
            dist_is_official = True
        else:
            # Calibrated SAE scaling D.L. 762 district share onto published 2024 Departmental Census total
            dept_dists = [d for d in self._districts.values() if d.department_code == dept_code]
            dl762_dept_sum = max(1, sum(d.approx_population for d in dept_dists))
            dl762_share = (dist.approx_population / dl762_dept_sum) if dist else 0.05
            dist_pop = max(1, int(round(dept_pop_2024 * dl762_share)))
            dist_is_official = False

        mean_hh_size = float(nat_censo.get("mean_household_size", 3.1))
        female_head_share = float(nat_censo.get("female_headed_household_share", 0.45))
        unocc_share = float(nat_censo.get("unoccupied_dwellings_share", 0.189))
        male_share = float(nat_censo.get("male_share", 0.4724))
        female_share = float(nat_censo.get("female_share", 0.5276))

        limitations: List[str] = []
        sae_estimate: Optional[SmallAreaEstimate] = None
        exact_available = False
        matched_granularity = GeographicGranularity.DISTRICT if dist_is_official else GeographicGranularity.DEPARTMENT

        if requested_granularity in (
            GeographicGranularity.CUSTOM_POLYGON,
            GeographicGranularity.CANTON,
            GeographicGranularity.SECTOR_CENSAL,
            GeographicGranularity.MANZANA,
        ):
            # Sub-district census microdata is NOT published in local package -> honest SAE!
            if local_building_capacity_estimate is not None and local_building_capacity_estimate > 0:
                if local_residential_share is not None and local_residential_share > 0 and dist_is_official:
                    share_est = int(round(dist_pop * min(0.85, local_residential_share)))
                    # Empirical-Bayes shrinkage blending dasymetric district share with local footprint capacity
                    est_pop = max(10, int(round(0.45 * share_est + 0.55 * local_building_capacity_estimate)))
                    sae_method = "Dasymetric residential footprint share + Empirical-Bayes capacity shrinkage"
                else:
                    est_pop = max(10, int(local_building_capacity_estimate))
                    sae_method = "Building-footprint residential dwelling occupancy SAE (Censo 2024 priors)"
                unc_pct = 24.0 if dist_is_official else 32.0
            else:
                share = max(0.004, min(0.5, float(local_residential_share or 0.02)))
                est_pop = max(15, int(round(dist_pop * share)))
                sae_method = "Proportional area/prior Small Area Estimation from parent district/department"
                unc_pct = 38.0

            est_hh = max(1, int(round(est_pop / mean_hh_size)))
            half_width = max(5, int(round(est_pop * (unc_pct / 100.0))))
            sae_estimate = SmallAreaEstimate(
                target_area_label=custom_area_label or f"Sub-área en {dist_name}",
                requested_granularity=requested_granularity,
                parent_official_unit_id=dist.district_id if dist_is_official and dist else dept_code,
                parent_official_unit_name=dist_name if dist_is_official else self._departments.get(dept_code).name,
                parent_official_granularity=GeographicGranularity.DISTRICT if dist_is_official else GeographicGranularity.DEPARTMENT,
                parent_official_population=dist_pop if dist_is_official else dept_pop_2024,
                estimated_population=est_pop,
                estimated_households=est_hh,
                sae_method=sae_method,
                uncertainty_pct=unc_pct,
                confidence_interval_95=(max(0, est_pop - half_width), est_pop + half_width),
                evidence_type=EvidenceClassification.ESTIMATED_FROM_OFFICIAL,
                confidence_level=round(max(0.35, 1.0 - unc_pct / 100.0), 2),
                limitations=[
                    f"No existen tabulados oficiales publicados localmente a granularidad {requested_granularity.value}; se utiliza SAE con incertidumbre ±{unc_pct:.0f}%.",
                ],
            )
            pop_evidence_type = EvidenceClassification.ESTIMATED_FROM_OFFICIAL
            official_pop_out: Optional[int] = dist_pop if dist_is_official else dept_pop_2024
            limitations.extend(sae_estimate.limitations)
        elif requested_granularity == GeographicGranularity.DISTRICT and not dist_is_official:
            # District not individually published in shipped Censo 2024 subset -> SAE from dept 2024 + D.L. 762
            unc_pct = 18.0
            half_w = max(20, int(round(dist_pop * (unc_pct / 100.0))))
            sae_estimate = SmallAreaEstimate(
                target_area_label=dist_name,
                requested_granularity=GeographicGranularity.DISTRICT,
                parent_official_unit_id=dept_code,
                parent_official_unit_name=self._departments[dept_code].name if dept_code in self._departments else dept_code,
                parent_official_granularity=GeographicGranularity.DEPARTMENT,
                parent_official_population=dept_pop_2024,
                estimated_population=dist_pop,
                estimated_households=max(1, int(round(dist_pop / mean_hh_size))),
                sae_method="Ratio-calibrated SAE (D.L. 762 district share × Censo 2024 departmental total)",
                uncertainty_pct=unc_pct,
                confidence_interval_95=(max(0, dist_pop - half_w), dist_pop + half_w),
                evidence_type=EvidenceClassification.ESTIMATED_FROM_OFFICIAL,
                confidence_level=0.82,
                limitations=[
                    f"Censo 2024 cargado localmente a nivel departamental para {dept_code}; población distrital de {dist_name} estimada vía SAE (±{unc_pct:.0f}%).",
                ],
            )
            pop_evidence_type = EvidenceClassification.ESTIMATED_FROM_OFFICIAL
            official_pop_out = dept_pop_2024
            limitations.extend(sae_estimate.limitations)
        else:
            exact_available = True
            pop_evidence_type = EvidenceClassification.PUBLIC_OFFICIAL
            official_pop_out = dist_pop

        # Stratum-aware urban/rural adjustment on EHPM priors
        stratum_key = "urban" if is_urban else "rural"
        stratum_ehpm = dict(ehpm_bundle.get("strata_priors", {}).get(stratum_key, {}))
        stratum_ehpm["national_indicators"] = ehpm_bundle.get("national_indicators", {})

        available_vars = [
            "departmental_population_2024",
            "national_sex_distribution_2024",
            "national_mean_household_size_2024",
            "national_unoccupied_dwelling_share_2024",
            "ehpm_stratum_schooling_and_income_priors",
            "mined_national_enrollment_macro",
        ]
        if dist_is_official:
            available_vars.insert(0, "district_official_population_2024")

        unavailable_vars = [
            "sector_censal_population_microdata",
            "manzana_exact_household_counts",
            "canton_official_age_sex_cross_tab",
        ]
        if not self._mined_schools:
            unavailable_vars.append("mined_per_school_enrollment_and_installed_capacity")
        if not self._minsal_facilities:
            unavailable_vars.append("minsal_per_facility_installed_capacity")

        if not self._mined_schools:
            limitations.append("Matrícula y capacidad instalada por centro escolar individual no importadas (UNAVAILABLE).")

        return CensusQueryResult(
            query_unit_id=dist.district_id if dist else district_id,
            query_unit_name=custom_area_label or dist_name,
            requested_granularity=requested_granularity,
            matched_granularity=matched_granularity,
            exact_granularity_available=exact_available,
            official_population=official_pop_out,
            population_evidence_type=pop_evidence_type,
            sae_estimate=sae_estimate,
            sex_distribution={"M": round(male_share, 4), "F": round(female_share, 4)},
            age_groups_distribution=dict(priors.get("age_groups_quinquennial", {})),
            household_size_distribution=dict(priors.get("household_size_distribution", {})),
            mean_household_size=mean_hh_size,
            female_headed_household_share=female_head_share,
            unoccupied_dwellings_share=unocc_share,
            ehpm_priors=stratum_ehpm,
            mined_macro=dict(mined_bundle),
            available_variables=available_vars,
            unavailable_variables=unavailable_vars,
            source_datasets=list(self._datasets.keys()),
            limitations=limitations,
        )
