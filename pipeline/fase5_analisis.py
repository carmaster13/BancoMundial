"""
Taller 02 - Dashboard Banco Mundial
FASE 5: Correlaciones, reglas de asociación y respuesta a las 6 preguntas

Uso:  python fase5_analisis.py "<modelo_estrella_bm.db>" "<datos_dashboard.json>" "<carpeta salida>"

Lee la tabla plana del modelo en estrella (vista vw_FactCompleta), calcula:
  1. Matriz de correlación de Spearman con p-valores.
  2. Correlaciones parciales controlando el PIB per cápita ("más allá del ingreso").
  3. Reglas de asociación (Apriori) sobre variables categorizadas.
  4. Los datos que responde cada una de las 6 preguntas.
Guarda Resultados_Fase5.xlsx, gráficos de apoyo y agrega la sección "analisis"
a datos_dashboard.json para el dashboard de la Fase 6.
"""
import sys, os, json, sqlite3
import numpy as np, pandas as pd
from scipy import stats
from mlxtend.frequent_patterns import apriori, association_rules
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB, JSON_PATH, OUT = (sys.argv[1:4] + ["modelo_estrella_bm.db", "datos_dashboard.json", "."][len(sys.argv) - 1:])[:3]
os.makedirs(OUT, exist_ok=True)
AZUL, AZUL_CLARO, GRIS = "#002244", "#009FDA", "#F2F2F2"

df = pd.read_sql("SELECT * FROM vw_FactCompleta", sqlite3.connect(DB))
VARS = {"EsperanzaVida": "Esperanza de vida", "MortalidadInfantil": "Mortalidad infantil",
        "Poblacion": "Población", "PIBPerCapita": "PIB per cápita",
        "GastoSaludPerCapita": "Gasto salud p/c", "GastoSaludPctPIB": "Gasto salud % PIB",
        "MatriculaSecundaria": "Matrícula secundaria", "AguaPotable": "Agua potable"}

# ---------------------------------------------------------------------------
# 1. Correlación de Spearman (robusta a asimetrías y atípicos) con p-valores
# ---------------------------------------------------------------------------
cols = list(VARS)
rho = pd.DataFrame(index=cols, columns=cols, dtype=float)
pval = rho.copy(); n_par = rho.copy()
for a in cols:
    for b in cols:
        if a == b:
            rho.loc[a, b], pval.loc[a, b], n_par.loc[a, b] = 1.0, 0.0, df[a].notna().sum()
            continue
        m = df[[a, b]].dropna()
        r, p = stats.spearmanr(m[a], m[b])
        rho.loc[a, b], pval.loc[a, b], n_par.loc[a, b] = r, p, len(m)

def fuerza(r):
    r = abs(r)
    return "Fuerte" if r >= .7 else "Moderada" if r >= .4 else "Débil" if r >= .2 else "Nula"

# ---------------------------------------------------------------------------
# 2. Correlación parcial de Spearman controlando el PIB per cápita
#    (correlación de los residuos de los rangos después de quitar el efecto del ingreso)
# ---------------------------------------------------------------------------
def parcial(x, y, z="PIBPerCapita"):
    m = df[[x, y, z]].dropna().rank()
    rx = m[x] - np.polyval(np.polyfit(m[z], m[x], 1), m[z])
    ry = m[y] - np.polyval(np.polyfit(m[z], m[y], 1), m[z])
    r, p = stats.pearsonr(rx, ry)
    return r, p, len(m)

pares = [("PIBPerCapita", "EsperanzaVida", "P4"),
         ("GastoSaludPerCapita", "MortalidadInfantil", "P5"),
         ("GastoSaludPctPIB", "MortalidadInfantil", "P5"),
         ("MatriculaSecundaria", "EsperanzaVida", "P6"),
         ("AguaPotable", "EsperanzaVida", "P6"),
         ("MatriculaSecundaria", "AguaPotable", "P6"),
         ("Poblacion", "EsperanzaVida", "P3")]
filas = []
for x, y, preg in pares:
    r0, p0, n0 = rho.loc[x, y], pval.loc[x, y], int(n_par.loc[x, y])
    if x == "PIBPerCapita":
        rp = pp = None
    else:
        rp, pp, _ = parcial(x, y)
    filas.append({"Pregunta": preg, "Variable X": VARS[x], "Variable Y": VARS[y], "n": n0,
                  "Spearman": round(r0, 2), "p-valor": float(f"{p0:.2e}"), "Fuerza": fuerza(r0),
                  "Parcial (controla PIB)": None if rp is None else round(rp, 2),
                  "p-valor parcial": None if pp is None else float(f"{pp:.2e}"),
                  "Significativa sin PIB (α=0,05)": None if pp is None else ("Sí" if pp < .05 else "No")})
corr_tabla = pd.DataFrame(filas)

# ---------------------------------------------------------------------------
# 3. Reglas de asociación (Apriori)
#    Cada país es una "transacción"; sus ítems son categorías de cada variable.
# ---------------------------------------------------------------------------
def cat(s, cortes, etiquetas):
    return pd.cut(s, cortes, labels=etiquetas, right=False).astype(object)

items = pd.DataFrame({
    "Continente": df["Continente"],
    "Tamaño": df["TamanoPais"],
    "EV": cat(df.EsperanzaVida, [0, 65, 75, 200], ["Baja", "Media", "Alta"]),
    "MortInf": cat(df.MortalidadInfantil, [0, 15, 50, 1e9], ["Baja", "Media", "Alta"]),
    "Ingreso": df["GrupoIngresoBM"].map({"Low income": "Bajo", "Lower middle income": "Medio-bajo",
                                         "Upper middle income": "Medio-alto", "High income": "Alto"}),
    "GastoSalud": cat(df.GastoSaludPerCapita, [0, 100, 1000, 1e9], ["Bajo", "Medio", "Alto"]),
    "Agua": cat(df.AguaPotable, [0, 50, 90, 101], ["Bajo", "Medio", "Alto"]),
    "Matrícula": cat(df.MatriculaSecundaria, [0, 70, 100, 1e9], ["Baja", "Media", "Alta"]),
})
canasta = pd.get_dummies(items.apply(lambda s: s.map(lambda v: None if pd.isna(v) else f"{s.name}={v}")
                                     ).stack().droplevel(1)).groupby(level=0).max().astype(bool)
frecuentes = apriori(canasta, min_support=0.08, use_colnames=True, max_len=3)
reglas = association_rules(frecuentes, metric="confidence", min_threshold=0.75)
reglas = reglas[(reglas["lift"] >= 1.5)]
reglas["Antecedente"] = reglas["antecedents"].map(lambda s: " + ".join(sorted(s)))
reglas["Consecuente"] = reglas["consequents"].map(lambda s: " + ".join(sorted(s)))
reglas = reglas[reglas["consequents"].map(len) == 1]
# Interesan las reglas que explican salud (consecuente = EV o MortInf)
salud = reglas[reglas["Consecuente"].str.match(r"^(EV|MortInf)=")]
# Quitar reglas redundantes: si A -> C ya tiene igual o más confianza, A + B -> C sobra
def redundante(r, todas):
    sub = todas[(todas.Consecuente == r.Consecuente) &
                (todas.antecedents.map(lambda a: a < r.antecedents))]
    return (sub.confidence >= r.confidence - 0.02).any()
salud = salud[~salud.apply(lambda r: redundante(r, salud), axis=1)]
reglas_out = (salud.assign(Soporte=lambda d: d.support.round(3), Confianza=lambda d: d.confidence.round(3),
                           Lift=lambda d: d.lift.round(2),
                           Paises=lambda d: (d.support * len(df)).round().astype(int))
              .sort_values(["Lift", "Confianza"], ascending=False)
              [["Antecedente", "Consecuente", "Paises", "Soporte", "Confianza", "Lift"]]
              .reset_index(drop=True))

# ---------------------------------------------------------------------------
# 4. Respuestas a las preguntas
# ---------------------------------------------------------------------------
pond = lambda g, c: np.average(g[c], weights=g.Poblacion)
p1 = (df.groupby("Continente").agg(Paises=("CodigoPais", "count"), Poblacion=("Poblacion", "sum"))
        .assign(PctPoblacion=lambda d: (d.Poblacion / d.Poblacion.sum() * 100).round(1),
                PctPaises=lambda d: (d.Paises / d.Paises.sum() * 100).round(1))
        .sort_values("Poblacion", ascending=False).reset_index())
ranking = df.sort_values("EsperanzaVida")
p2 = pd.concat([ranking.tail(5).iloc[::-1].assign(Grupo="Top 5"), ranking.head(5).assign(Grupo="Bottom 5")])[
    ["Grupo", "Pais", "Continente", "EsperanzaVida", "BrechaEV_vsMundo"]]
p3 = (df.groupby(["TamanoPaisOrden", "TamanoPais"])
        .apply(lambda g: pd.Series({"Paises": len(g), "PctPoblacion": g.Poblacion.sum() / df.Poblacion.sum() * 100,
                                    "EV_mediana": g.EsperanzaVida.median(), "EV_ponderada": pond(g, "EsperanzaVida"),
                                    "MI_mediana": g.MortalidadInfantil.median(),
                                    "MI_ponderada": pond(g, "MortalidadInfantil")}), include_groups=False)
        .round(1).reset_index().drop(columns="TamanoPaisOrden"))
kw_ev = stats.kruskal(*[g.EsperanzaVida for _, g in df.groupby("TamanoPais")])
kw_mi = stats.kruskal(*[g.MortalidadInfantil for _, g in df.groupby("TamanoPais")])

# Cuartiles para las preguntas 4-6 (lectura sencilla para la junta)
def por_cuartil(x, y):
    m = df[[x, y]].dropna()
    q = pd.qcut(m[x], 4, labels=["Q1 (más bajo)", "Q2", "Q3", "Q4 (más alto)"])
    return m.groupby(q, observed=True)[y].median().round(1)
q4 = por_cuartil("PIBPerCapita", "EsperanzaVida")
q5 = por_cuartil("GastoSaludPerCapita", "MortalidadInfantil")
q6a = por_cuartil("AguaPotable", "EsperanzaVida")
q6b = por_cuartil("MatriculaSecundaria", "EsperanzaVida")

# ---------------------------------------------------------------------------
# 5. Gráficos de apoyo para la revisión (el dashboard tendrá su versión interactiva)
# ---------------------------------------------------------------------------
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(figsize=(8.5, 7))
etq = [VARS[c] for c in cols]
im = ax.imshow(rho.values.astype(float), cmap="RdBu", vmin=-1, vmax=1)
ax.set_xticks(range(len(cols)), etq, rotation=40, ha="right"); ax.set_yticks(range(len(cols)), etq)
for i in range(len(cols)):
    for j in range(len(cols)):
        v = rho.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9, color="white" if abs(v) > .6 else "#222")
ax.set_title("La salud se mueve con el ingreso, el gasto, el agua y la educación;\nno con el tamaño de la población",
             loc="left", fontsize=12, color=AZUL, fontweight="bold")
fig.colorbar(im, ax=ax, shrink=.75, label="Correlación de Spearman")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F5_matriz_correlacion.png"), dpi=160); plt.close(fig)

colores = {"África": "#E8A33D", "América": "#009FDA", "Asia": "#7B5EA7", "Europa": "#002244", "Oceanía": "#3BA272"}
fig, axs = plt.subplots(1, 3, figsize=(16, 5))
for ax, (x, y, titulo, logx) in zip(axs, [
        ("PIBPerCapita", "EsperanzaVida", "P4 · PIB per cápita vs esperanza de vida", True),
        ("GastoSaludPerCapita", "MortalidadInfantil", "P5 · Gasto en salud vs mortalidad infantil", True),
        ("AguaPotable", "EsperanzaVida", "P6 · Agua potable vs esperanza de vida", False)]):
    m = df.dropna(subset=[x, y])
    for c, g in m.groupby("Continente"):
        ax.scatter(g[x], g[y], s=np.clip(np.sqrt(g.Poblacion) / 60, 8, 400), alpha=.7, color=colores[c],
                   label=c, edgecolor="white", linewidth=.5)
    if logx: ax.set_xscale("log")
    ax.set_xlabel(VARS[x] + (" (USD, escala log)" if logx else " (% población)")); ax.set_ylabel(VARS[y])
    ax.set_title(f"{titulo}\nSpearman = {rho.loc[x, y]:.2f}", loc="left", fontsize=11, color=AZUL)
axs[0].legend(frameon=False, fontsize=8, title="Tamaño = población", title_fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "F5_dispersion_P4_P5_P6.png"), dpi=160); plt.close(fig)

# ---------------------------------------------------------------------------
# 6. Guardar resultados
# ---------------------------------------------------------------------------
with pd.ExcelWriter(os.path.join(OUT, "Resultados_Fase5.xlsx")) as w:
    rho.round(3).rename(index=VARS, columns=VARS).to_excel(w, sheet_name="MatrizSpearman")
    pval.rename(index=VARS, columns=VARS).to_excel(w, sheet_name="PValores")
    corr_tabla.to_excel(w, sheet_name="CorrelacionesClave", index=False)
    reglas_out.to_excel(w, sheet_name="ReglasAsociacion", index=False)
    p1.to_excel(w, sheet_name="P1_Distribucion", index=False)
    p2.to_excel(w, sheet_name="P2_PolosOpuestos", index=False)
    p3.to_excel(w, sheet_name="P3_Tamano", index=False)
    pd.DataFrame({"P4 EV mediana por cuartil de PIB": q4, "P5 MI mediana por cuartil de gasto salud": q5.values,
                  "P6 EV mediana por cuartil de agua": q6a.values,
                  "P6 EV mediana por cuartil de matrícula": q6b.values}).to_excel(w, sheet_name="P4_P6_Cuartiles")

with open(JSON_PATH, encoding="utf-8") as fh:
    data = json.load(fh)
data["analisis"] = {
    "correlacion": {"variables": etq, "matriz": rho.round(3).values.tolist()},
    "correlaciones_clave": json.loads(corr_tabla.to_json(orient="records", force_ascii=False)),
    "reglas": json.loads(reglas_out.groupby("Consecuente").head(5).to_json(orient="records", force_ascii=False)),
    "kruskal_tamano": {"EV_p": kw_ev.pvalue, "MI_p": kw_mi.pvalue},
}
with open(JSON_PATH, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False)

pd.set_option("display.width", 250)
print("== Correlaciones clave\n", corr_tabla.to_string(index=False))
print("\n== Reglas de asociación (salud)\n", reglas_out.head(15).to_string())
print(f"\nTotal reglas de salud no redundantes: {len(reglas_out)}")
print("\n== P1\n", p1.to_string(index=False)); print("\n== P2\n", p2.to_string(index=False))
print("\n== P3\n", p3.to_string(index=False), f"\nKruskal-Wallis EV p={kw_ev.pvalue:.3f}  MI p={kw_mi.pvalue:.3f}")
print("\n== P4-P6 cuartiles\n", pd.DataFrame({"P4": q4.values, "P5": q5.values, "P6agua": q6a.values, "P6matric": q6b.values}, index=q4.index))
