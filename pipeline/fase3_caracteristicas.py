"""
Taller 02 - Dashboard Banco Mundial
FASE 3: Ingeniería de características (punto 6: al menos 3 variables nuevas)

Uso:  python fase3_caracteristicas.py "<Modelo_Estrella_BancoMundial.xlsx>"

Lee el libro generado en la Fase 1, agrega 5 variables nuevas (más 2 de apoyo)
a FactIndicadoresPais y crea la hoja DiccionarioVariables. Se ejecuta después
de fase1_wrangling.py; Power BI solo necesita "Actualizar".
"""
import sys
import numpy as np
import pandas as pd
from openpyxl import load_workbook

LIBRO = sys.argv[1] if len(sys.argv) > 1 else "Modelo_Estrella_BancoMundial.xlsx"

hojas = pd.read_excel(LIBRO, sheet_name=None)
fact = hojas["FactIndicadoresPais"]
# por si el script se corre dos veces, se recalculan desde cero
fact = fact[[c for c in fact.columns if not c.startswith(("Tamano", "GastoSaludPct", "NivelEsperanza",
                                                         "BrechaEV", "IndicePrioridad", "Prioridad",
                                                         "ComponentesIndice"))]]

# 1) Tamaño demográfico (P3) -------------------------------------------------
#    Umbrales redondos y explicables: < 5 M, 5-50 M, >= 50 M habitantes
fact["TamanoPais"] = pd.cut(fact["Poblacion"], [0, 5e6, 50e6, np.inf], right=False,
                            labels=["Pequeño", "Mediano", "Grande"]).astype(str)
fact["TamanoPaisOrden"] = fact["TamanoPais"].map({"Pequeño": 1, "Mediano": 2, "Grande": 3})

# 2) Gasto en salud como % del PIB (KPI 12): esfuerzo del país, no su riqueza --
fact["GastoSaludPctPIB"] = (fact["GastoSaludPerCapita"] / fact["PIBPerCapita"] * 100).round(2)

# 3) Nivel de esperanza de vida (P2 y reglas de asociación) -------------------
#    65 años = umbral del KPI 6 (población en riesgo); 75 = umbral de país de alta longevidad
fact["NivelEsperanzaVida"] = pd.cut(fact["EsperanzaVida"], [0, 65, 75, np.inf], right=False,
                                    labels=["Baja (<65)", "Media (65-75)", "Alta (75+)"]).astype(str)

# 4) Brecha de esperanza de vida frente a la media mundial PONDERADA ----------
media_mundial = np.average(fact["EsperanzaVida"], weights=fact["Poblacion"])
fact["BrechaEV_vsMundo"] = (fact["EsperanzaVida"] - media_mundial).round(2)

# 5) Índice de prioridad de financiamiento (0-100; 100 = mayor necesidad) -----
#    Se usa el percentil de cada país (robusto a extremos como Mónaco o EE. UU.).
#    "Necesidad" = más mortalidad, menos esperanza de vida, menos gasto, menos agua, menos educación.
componentes = {  # variable: (peso, True si un valor ALTO significa MÁS necesidad)
    "MortalidadInfantil":  (0.30, True),
    "EsperanzaVida":       (0.25, False),
    "GastoSaludPerCapita": (0.15, False),
    "AguaPotable":         (0.15, False),
    "MatriculaSecundaria": (0.15, False),
}
puntajes = pd.DataFrame(index=fact.index)
pesos = pd.DataFrame(index=fact.index)
for col, (peso, alto_es_necesidad) in componentes.items():
    pct = fact[col].rank(pct=True) * 100
    puntajes[col] = pct if alto_es_necesidad else 100 - pct
    pesos[col] = np.where(fact[col].notna(), peso, 0.0)
# Si a un país le falta un componente, los pesos se reparten entre los que sí tiene
fact["IndicePrioridad"] = ((puntajes.fillna(0) * pesos).sum(axis=1) / pesos.sum(axis=1)).round(1)
fact["ComponentesIndice"] = (pesos > 0).sum(axis=1)
fact["PrioridadFinanciamiento"] = pd.cut(fact["IndicePrioridad"], [0, 40, 70, 100.01], right=False,
                                         labels=["Baja", "Media", "Alta"]).astype(str)

# --- Diccionario de variables ------------------------------------------------
dicc = pd.DataFrame([
    ["TamanoPais", "Nueva", "Pequeño < 5 M hab.; Mediano 5-50 M; Grande ≥ 50 M",
     "Segmentar países por tamaño demográfico (P3)"],
    ["TamanoPaisOrden", "Apoyo", "1 = Pequeño, 2 = Mediano, 3 = Grande",
     "Ordenar la segmentación en los gráficos (Ordenar por columna)"],
    ["GastoSaludPctPIB", "Nueva", "GastoSaludPerCapita / PIBPerCapita × 100",
     "Esfuerzo del país en salud, independiente de su riqueza (KPI 12, P5). Años de ambos datos pueden diferir 1-2 años"],
    ["NivelEsperanzaVida", "Nueva", "Baja < 65; Media 65-75; Alta ≥ 75 años",
     "Clasificar longevidad para el mapa, la P2 y las reglas de asociación"],
    ["BrechaEV_vsMundo", "Nueva", f"EsperanzaVida − {media_mundial:.2f} (media mundial ponderada por población)",
     "Años que un país está por encima (+) o por debajo (−) del promedio mundial"],
    ["IndicePrioridad", "Nueva", "Promedio ponderado de percentiles de necesidad: MortalidadInfantil 30 %, "
     "EsperanzaVida 25 %, GastoSalud 15 %, Agua 15 %, Matrícula 15 %. Si falta un dato, se re-pondera",
     "Ranking de dónde invertir primero (responde la pregunta clave). 0 = menor necesidad, 100 = mayor"],
    ["ComponentesIndice", "Apoyo", "Número de componentes (de 5) con dato para el índice",
     "Transparencia: un índice con 3/5 componentes es menos confiable"],
    ["PrioridadFinanciamiento", "Nueva", "Baja < 40; Media 40-70; Alta ≥ 70 puntos del índice",
     "Categoría para colorear el mapa y filtrar el dashboard"],
    ["MortalidadInfantil", "Original", "Muertes por cada 1.000 nacidos vivos (confirmado por el docente)",
     "Año de la fuente del curso no registrado"],
], columns=["Variable", "Tipo", "Definición / fórmula", "Uso en el dashboard"])

# --- Guardar (reemplaza solo las hojas tocadas, conserva el resto) -----------
with pd.ExcelWriter(LIBRO, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
    fact.to_excel(w, sheet_name="FactIndicadoresPais", index=False)
    dicc.to_excel(w, sheet_name="DiccionarioVariables", index=False)
wb = load_workbook(LIBRO)
for nombre in ("FactIndicadoresPais", "DiccionarioVariables"):
    ws = wb[nombre]; ws.freeze_panes = "A2"
    for col in ws.columns:
        largo = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, largo + 2), 70)
# Registrar la confirmación de unidad en la bitácora
log = wb["LogCalidad"]
if not any(r[1] == "Unidad confirmada" for r in log.iter_rows(values_only=True)):
  log.append(["5. Validación", "Unidad confirmada",
            "MortalidadInfantil = muertes por 1.000 nacidos vivos (confirmado por el docente); año de la fuente no registrado", ""])
wb.save(LIBRO)

print(f"Media mundial ponderada de esperanza de vida: {media_mundial:.2f}")
print(fact[["TamanoPais", "NivelEsperanzaVida", "PrioridadFinanciamiento"]].apply(lambda s: s.value_counts()).fillna(0).astype(int))
print(fact[["GastoSaludPctPIB", "BrechaEV_vsMundo", "IndicePrioridad"]].describe().round(2))
