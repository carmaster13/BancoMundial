"""
Taller 02 - Dashboard Banco Mundial
FASE 1: Gobernanza de nombres + Data Wrangling

Uso:  python fase1_wrangling.py "<carpeta con los archivos>" "<archivo de salida .xlsx>"

Genera un libro de Excel con las tablas del modelo en estrella:
  DimPais, DimPeriodo, FactIndicadoresPais, TablaEquivalencias, LogCalidad
Power BI se conecta a este libro, así que al re-ejecutar el script con datos
nuevos el reporte se actualiza con "Actualizar" (punto 4 del taller).
"""
import sys, os, re, unicodedata
from difflib import SequenceMatcher
import pandas as pd
import numpy as np

CARPETA = sys.argv[1] if len(sys.argv) > 1 else "."
SALIDA = sys.argv[2] if len(sys.argv) > 2 else "Modelo_Estrella_BancoMundial.xlsx"
ANIO_MIN = 2015          # Opción A: último dato disponible desde 2015
ANIO_CORTE = 2025        # Año del reporte (DimPeriodo, según el diagrama del taller)

log = []                 # bitácora de calidad: (paso, regla, detalle, registros)
def registrar(paso, regla, detalle, n=""):
    log.append({"Paso": paso, "Regla": regla, "Detalle": detalle, "Registros": n})

def ruta(nombre):
    return os.path.join(CARPETA, nombre)

def limpiar_texto(s):
    """Quita espacios sobrantes y normaliza unicode (evita que 'Côte' ≠ 'Côte')."""
    if pd.isna(s):
        return s
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s))).strip()

def clave_comparacion(s):
    """Versión 'simplificada' de un nombre para medir parecido entre fuentes."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", " ", s)
    ruido = {"the", "of", "and", "rep", "republic", "dem", "democratic", "fed", "sts",
             "islamic", "arab", "sar", "china", "pdr", "people", "s", "rb", "us", "u",
             "part", "french", "dutch", "st", "saint"}
    return " ".join(t for t in s.split() if t not in ruido)

def similitud(a, b):
    return round(SequenceMatcher(None, clave_comparacion(a), clave_comparacion(b)).ratio(), 2)

# ---------------------------------------------------------------------------
# 1. Carga y limpieza básica de las fuentes del curso
# ---------------------------------------------------------------------------
countries = pd.read_excel(ruta("Countries.xlsx")).rename(
    columns={"Country Code": "CodigoPais", "Country": "Country_Original", "Continent": "Continent"})
paises = pd.read_excel(ruta("Paises.xlsx")).rename(
    columns={"Codigo Pais": "CodigoPais", "Pais": "Pais", "Continente": "Continente"})
pob = pd.read_excel(ruta("Population.xlsx")).rename(columns={"Population": "Poblacion"})
ev = pd.read_excel(ruta("Life+expectancy.xlsx")).rename(columns={"Life Expectancy": "EsperanzaVida"})
mi = pd.read_excel(ruta("Infant+death+rate.xlsx")).rename(columns={"Infant mortality": "MortalidadInfantil"})

for df in (countries, paises, pob, ev, mi):
    for col in df.select_dtypes(exclude="number").columns:
        df[col] = df[col].map(limpiar_texto)
registrar("1. Carga", "Limpieza de texto", "Espacios sobrantes y normalización unicode en todas las columnas de texto")

for nombre, df in [("Countries", countries), ("Paises", paises), ("Population", pob),
                   ("Life expectancy", ev), ("Infant mortality", mi)]:
    registrar("1. Carga", "Perfil", f"{nombre}: {len(df)} filas, {df.isna().sum().sum()} nulos, "
              f"{df.duplicated().sum()} duplicados", len(df))

# ---------------------------------------------------------------------------
# 2. Validación de la llave CodigoPais entre Countries (EN) y Paises (ES)
# ---------------------------------------------------------------------------
dim = countries.merge(paises, on="CodigoPais", how="outer", indicator=True)
huerfanos = dim[dim["_merge"] != "both"]
registrar("2. Llave", "Códigos ISO3 Countries vs Paises",
          "Coinciden al 100 %" if huerfanos.empty else f"Códigos sin pareja: {huerfanos.CodigoPais.tolist()}",
          len(huerfanos))
dim = dim.drop(columns="_merge")

# Continentes: un solo catálogo bilingüe, validado contra ambas fuentes
mapa_continente = {"Africa": "África", "America": "América", "Asia": "Asia",
                   "Europe": "Europa", "Oceania": "Oceanía"}
incoh = dim[dim["Continent"].map(mapa_continente) != dim["Continente"]]
registrar("2. Llave", "Continente EN vs ES", f"{len(incoh)} países con continente distinto entre fuentes", len(incoh))

# ---------------------------------------------------------------------------
# 3. Fuentes externas del Banco Mundial (formato ancho 1960-2025)
# ---------------------------------------------------------------------------
externos = {
    "PIBPerCapita": "GDP per capita.xls",
    "GastoSaludPerCapita": "Current health expenditure per capita.xls",
    "MatriculaSecundaria": "School enrollment, secondary.xls",
    "AguaPotable": "People using safely managed drinking water services.xls",
}
meta = pd.read_excel(ruta(externos["PIBPerCapita"]), sheet_name="Metadata - Countries")
meta["Country Code"] = meta["Country Code"].map(limpiar_texto)
agregados = set(meta.loc[meta["Region"].isna(), "Country Code"])
registrar("3. Banco Mundial", "Excluir agregados regionales",
          "Filas sin región (World, Latin America & Caribbean, High income...) se eliminan para no duplicar población",
          len(agregados))

nombres_bm = None
hechos_bm = []
for indicador, archivo in externos.items():
    d = pd.read_excel(ruta(archivo), sheet_name="Data", header=3)
    d["Country Code"] = d["Country Code"].map(limpiar_texto)
    d["Country Name"] = d["Country Name"].map(limpiar_texto)
    if nombres_bm is None:
        nombres_bm = d[["Country Code", "Country Name"]].rename(
            columns={"Country Code": "CodigoPais", "Country Name": "Nombre_BancoMundial"})
    d = d[~d["Country Code"].isin(agregados)]
    anios = [c for c in d.columns if re.fullmatch(r"\d{4}(\.0)?", str(c)) and int(float(c)) >= ANIO_MIN]
    largo = d.melt(id_vars="Country Code", value_vars=anios, var_name="Anio", value_name="Valor").dropna()
    largo["Anio"] = largo["Anio"].astype(float).astype(int)
    ultimo = largo.sort_values("Anio").groupby("Country Code").tail(1)
    ultimo = ultimo[ultimo["Country Code"].isin(set(dim.CodigoPais))]   # solo los 216 países del curso
    ultimo = ultimo.rename(columns={"Country Code": "CodigoPais", "Valor": indicador, "Anio": f"Anio_{indicador}"})
    hechos_bm.append(ultimo.set_index("CodigoPais"))
    registrar("3. Banco Mundial", f"{indicador}: último dato desde {ANIO_MIN}",
              f"{len(ultimo)} países con dato; años usados {ultimo[f'Anio_{indicador}'].min()}-"
              f"{ultimo[f'Anio_{indicador}'].max()}", len(ultimo))
hechos_bm = pd.concat(hechos_bm, axis=1).reset_index()

# ---------------------------------------------------------------------------
# 4. GOBERNANZA DE NOMBRES
#    Regla de oro: la llave es SIEMPRE el código ISO3, nunca el nombre.
#    a) Se cruzan los nombres de las 3 fuentes por código.
#    b) Se mide la similitud entre nombres para detectar anomalías.
#    c) Las anomalías se revisan y se corrigen con un diccionario documentado.
# ---------------------------------------------------------------------------
eq = dim[["CodigoPais", "Country_Original", "Pais"]].merge(nombres_bm, on="CodigoPais", how="left")
eq["Similitud_EN_vs_BM"] = [similitud(a, b) if pd.notna(b) else np.nan
                            for a, b in zip(eq.Country_Original, eq.Nombre_BancoMundial)]

# Correcciones confirmadas tras revisar los casos de baja similitud.
# Evidencia: el código, el nombre en Paises.xlsx y el nombre del Banco Mundial
# coinciden entre sí; solo Countries.xlsx (y los archivos de indicadores que
# lo copian) tienen el nombre de otro territorio.
CORRECCIONES = {
    "MNE": ("Montenegro", "Countries.xlsx decía 'Montserrat' (código MSR). Población 622.781 = Montenegro"),
    "MAF": ("Saint Martin (French part)", "Countries.xlsx decía 'Saint Pierre and Miquelon' (código SPM)"),
}
eq["Country"] = eq["Country_Original"]
eq["Tipo"] = np.where(eq["Country_Original"] == eq["Nombre_BancoMundial"], "Idéntico",
                      "Variante de escritura")
eq.loc[eq["Nombre_BancoMundial"].isna(), "Tipo"] = "Sin registro en Banco Mundial"
eq["Observacion"] = ""
for cod, (nombre, motivo) in CORRECCIONES.items():
    m = eq.CodigoPais == cod
    eq.loc[m, ["Country", "Tipo", "Observacion"]] = [nombre, "Error corregido", motivo]

# Actualización de nombres oficiales (nombre antiguo -> nombre vigente), aprobada en la revisión
ACTUALIZACIONES = {
    "SWZ": ("Esuatini", "Eswatini", "Nombre vigente desde 2018 (antes Suazilandia / Swaziland)"),
}
eq["Pais_Original"] = eq["Pais"]
for cod, (es, en, motivo) in ACTUALIZACIONES.items():
    m = eq.CodigoPais == cod
    eq.loc[m, ["Pais", "Country", "Tipo", "Observacion"]] = [es, en, "Nombre actualizado", motivo]

umbral = 0.65   # por debajo de este parecido, el caso se revisa a mano
revisar = eq[eq.Similitud_EN_vs_BM < umbral].sort_values("Similitud_EN_vs_BM")
registrar("4. Gobernanza", "Variantes de escritura (mismo país, distinto nombre)",
          "Se unen por código; ejemplo: 'Congo, Dem. Rep.' = 'Democratic Republic of the Congo'",
          int((eq.Tipo == "Variante de escritura").sum()))
registrar("4. Gobernanza", f"Similitud < {umbral} revisada manualmente",
          "Revisados (código, nombre Countries / nombre BM, resultado): " + "; ".join(
              f"{r.CodigoPais} {r.Country_Original} / {r.Nombre_BancoMundial} -> "
              f"{'ERROR' if r.Tipo == 'Error corregido' else 'mismo país'}" for r in revisar.itertuples()),
          len(revisar))
registrar("4. Gobernanza", "Prueba de plausibilidad",
          "Montserrat tiene ~5.000 habitantes, pero la fila trae 622.781 (población de Montenegro): "
          "confirma que el dato es de MNE y solo el nombre estaba mal", "")
for cod, (nombre, motivo) in CORRECCIONES.items():
    registrar("4. Gobernanza", "Error de nombre corregido", f"{cod} -> {nombre}. {motivo}", 1)
for cod, (es, en, motivo) in ACTUALIZACIONES.items():
    registrar("4. Gobernanza", "Nombre actualizado", f"{cod} -> {es} / {en}. {motivo}", 1)

# Los archivos de indicadores del curso solo traen el nombre: se traducen a código
# usando el nombre ORIGINAL de Countries (antes de corregir), que es el que usan.
nombre_a_codigo = dict(zip(eq.Country_Original, eq.CodigoPais))
base = None
for nombre, df, col in [("Population", pob, "Poblacion"), ("Life expectancy", ev, "EsperanzaVida"),
                        ("Infant mortality", mi, "MortalidadInfantil")]:
    df = df.copy()
    df["CodigoPais"] = df["Country"].map(nombre_a_codigo)
    sin = df[df.CodigoPais.isna()]
    registrar("4. Gobernanza", f"{nombre}: nombre -> código",
              "100 % de los países encontraron su código" if sin.empty else f"Sin código: {sin.Country.tolist()}",
              len(sin))
    df = df.dropna(subset=["CodigoPais"])[["CodigoPais", col]]
    base = df if base is None else base.merge(df, on="CodigoPais", how="outer")

# ---------------------------------------------------------------------------
# 5. Tabla de hechos y validaciones de rango
# ---------------------------------------------------------------------------
fact = base.merge(hechos_bm, on="CodigoPais", how="left")
fact.insert(1, "Anio", ANIO_CORTE)
fact["Poblacion"] = fact["Poblacion"].astype("int64")

reglas = {  # rango plausible: valores fuera se marcan, no se borran
    "Poblacion": (1_000, 2_000_000_000), "EsperanzaVida": (40, 95), "MortalidadInfantil": (0, 200),
    "PIBPerCapita": (100, 300_000), "GastoSaludPerCapita": (1, 20_000),
    "MatriculaSecundaria": (0, 170), "AguaPotable": (0, 100),
}
for col, (lo, hi) in reglas.items():
    fuera = fact[(fact[col] < lo) | (fact[col] > hi)]
    registrar("5. Validación", f"Rango {col} [{lo:,}-{hi:,}]",
              "Todos dentro de rango" if fuera.empty else f"Fuera de rango: {fuera.CodigoPais.tolist()}", len(fuera))
    nulos = fact[col].isna().sum()
    if nulos:
        registrar("5. Validación", f"Nulos {col}",
                  "Se dejan en blanco (no se imputan): imputar inventaría cifras de un país; el dashboard mostrará cuántos países tienen dato", int(nulos))

# Atípicos (regla de Tukey sobre log para variables muy asimétricas): solo se marcan
for col in ["PIBPerCapita", "GastoSaludPerCapita", "MortalidadInfantil", "EsperanzaVida"]:
    x = np.log(fact[col]) if col in ("PIBPerCapita", "GastoSaludPerCapita") else fact[col]
    q1, q3 = x.quantile([.25, .75]); iqr = q3 - q1
    atip = fact[(x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)]
    registrar("5. Validación", f"Atípicos {col} (Tukey)",
              ("Ninguno" if atip.empty else ", ".join(atip.CodigoPais)) + " — se conservan: son casos reales",
              len(atip))

registrar("5. Validación", "Alerta de unidad",
          "MortalidadInfantil alcanza 191 (Angola) y 163 (Afganistán): confirmar con el docente si es "
          "por 1.000 nacidos vivos y el año de la fuente del curso (~2016)", "")
registrar("5. Validación", "Duplicados en llave", f"{fact.CodigoPais.duplicated().sum()} códigos repetidos en la tabla de hechos",
          int(fact.CodigoPais.duplicated().sum()))

# ---------------------------------------------------------------------------
# 6. Dimensiones finales
# ---------------------------------------------------------------------------
dim_pais = eq[["CodigoPais", "Pais", "Country", "Nombre_BancoMundial"]].merge(
    dim[["CodigoPais", "Continente", "Continent"]], on="CodigoPais").merge(
    meta[["Country Code", "Region", "IncomeGroup"]].rename(
        columns={"Country Code": "CodigoPais", "Region": "RegionBM", "IncomeGroup": "GrupoIngresoBM"}),
    on="CodigoPais", how="left")
dim_pais = dim_pais.sort_values(["Continente", "Pais"]).reset_index(drop=True)
dim_periodo = pd.DataFrame({"Anio": [ANIO_CORTE],
                            "Descripcion": [f"Corte {ANIO_CORTE}: último dato disponible desde {ANIO_MIN}"]})

orden = ["CodigoPais", "Anio", "Poblacion", "EsperanzaVida", "MortalidadInfantil",
         "PIBPerCapita", "GastoSaludPerCapita", "MatriculaSecundaria", "AguaPotable",
         "Anio_PIBPerCapita", "Anio_GastoSaludPerCapita", "Anio_MatriculaSecundaria", "Anio_AguaPotable"]
fact = fact[orden].sort_values("CodigoPais").reset_index(drop=True)

tabla_eq = eq[["CodigoPais", "Country_Original", "Pais_Original", "Nombre_BancoMundial", "Pais", "Country",
               "Similitud_EN_vs_BM", "Tipo", "Observacion"]].rename(
    columns={"Country_Original": "Nombre_Countries_xlsx", "Pais_Original": "Nombre_Paises_xlsx",
             "Pais": "Nombre_Oficial_ES",
             "Country": "Nombre_Oficial_EN"})

# Integridad referencial del modelo en estrella
sin_dim = set(fact.CodigoPais) - set(dim_pais.CodigoPais)
registrar("6. Modelo", "Integridad referencial Fact -> DimPais",
          "OK: todos los códigos de la tabla de hechos existen en DimPais" if not sin_dim else f"Huérfanos: {sin_dim}",
          len(sin_dim))

# ---------------------------------------------------------------------------
# 7. Exportar
# ---------------------------------------------------------------------------
with pd.ExcelWriter(SALIDA, engine="openpyxl") as w:
    dim_pais.to_excel(w, "DimPais", index=False)
    dim_periodo.to_excel(w, "DimPeriodo", index=False)
    fact.to_excel(w, "FactIndicadoresPais", index=False)
    tabla_eq.to_excel(w, "TablaEquivalencias", index=False)
    pd.DataFrame(log).to_excel(w, "LogCalidad", index=False)
    for ws in w.book.worksheets:                      # ancho de columnas y encabezado fijo
        ws.freeze_panes = "A2"
        for col in ws.columns:
            largo = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max(10, largo + 2), 70)

print(pd.DataFrame(log).to_string())
print(f"\nOK -> {SALIDA}")
