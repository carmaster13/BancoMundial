"""
Taller 02 - Dashboard Banco Mundial
FASE 4: Modelo en estrella relacional (SQLite) + capa de KPI en SQL

Uso:  python fase4_modelo_estrella.py "<Modelo_Estrella_BancoMundial.xlsx>" "<salida .db>" "<salida .json>"

1. Crea una base de datos SQLite con llaves primarias, foráneas y reglas CHECK.
2. Carga DimPais, DimPeriodo y FactIndicadoresPais desde el Excel de las fases 1 y 3.
3. Crea vistas SQL con los 12 KPI (equivalentes a las medidas DAX de Power BI).
4. Exporta datos_dashboard.json: el dashboard HTML (Fase 6) lee SOLO este archivo,
   así que al re-ejecutar el pipeline el dashboard se actualiza solo (punto 4).
"""
import sys, os, json, sqlite3
import pandas as pd

LIBRO = sys.argv[1] if len(sys.argv) > 1 else "Modelo_Estrella_BancoMundial.xlsx"
DB = sys.argv[2] if len(sys.argv) > 2 else "modelo_estrella_bm.db"
JSON_OUT = sys.argv[3] if len(sys.argv) > 3 else "datos_dashboard.json"

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE DimPais (
    CodigoPais          TEXT PRIMARY KEY CHECK (length(CodigoPais) = 3),
    Pais                TEXT NOT NULL,
    Country             TEXT NOT NULL,
    Nombre_BancoMundial TEXT,
    Continente          TEXT NOT NULL CHECK (Continente IN ('África','América','Asia','Europa','Oceanía')),
    Continent           TEXT NOT NULL,
    RegionBM            TEXT,
    GrupoIngresoBM      TEXT
);

CREATE TABLE DimPeriodo (
    Anio        INTEGER PRIMARY KEY,
    Descripcion TEXT
);

CREATE TABLE FactIndicadoresPais (
    CodigoPais               TEXT    NOT NULL REFERENCES DimPais(CodigoPais),
    Anio                     INTEGER NOT NULL REFERENCES DimPeriodo(Anio),
    Poblacion                INTEGER NOT NULL CHECK (Poblacion > 0),
    EsperanzaVida            REAL    CHECK (EsperanzaVida BETWEEN 0 AND 100),
    MortalidadInfantil       REAL    CHECK (MortalidadInfantil >= 0),       -- por 1.000 nacidos vivos
    PIBPerCapita             REAL    CHECK (PIBPerCapita > 0),              -- USD corrientes
    GastoSaludPerCapita      REAL    CHECK (GastoSaludPerCapita > 0),       -- USD corrientes
    MatriculaSecundaria      REAL    CHECK (MatriculaSecundaria >= 0),      -- % bruta (puede pasar de 100)
    AguaPotable              REAL    CHECK (AguaPotable BETWEEN 0 AND 100), -- % de la población
    Anio_PIBPerCapita        INTEGER,
    Anio_GastoSaludPerCapita INTEGER,
    Anio_MatriculaSecundaria INTEGER,
    Anio_AguaPotable         INTEGER,
    -- Variables de la Fase 3 (ingeniería de características)
    TamanoPais               TEXT CHECK (TamanoPais IN ('Pequeño','Mediano','Grande')),
    TamanoPaisOrden          INTEGER,
    GastoSaludPctPIB         REAL,
    NivelEsperanzaVida       TEXT,
    BrechaEV_vsMundo         REAL,
    IndicePrioridad          REAL CHECK (IndicePrioridad BETWEEN 0 AND 100),
    ComponentesIndice        INTEGER,
    PrioridadFinanciamiento  TEXT CHECK (PrioridadFinanciamiento IN ('Baja','Media','Alta')),
    PRIMARY KEY (CodigoPais, Anio)
);
CREATE INDEX ix_fact_anio ON FactIndicadoresPais(Anio);
"""

VISTAS = """
-- Tabla plana (hechos + dimensiones) que consume el dashboard
CREATE VIEW vw_FactCompleta AS
SELECT f.*, d.Pais, d.Country, d.Continente, d.Continent, d.RegionBM, d.GrupoIngresoBM
FROM FactIndicadoresPais f
JOIN DimPais d    ON d.CodigoPais = f.CodigoPais
JOIN DimPeriodo p ON p.Anio = f.Anio;

-- Medianas (SQLite no trae MEDIAN): número de fila central por variable
CREATE VIEW vw_Medianas AS
WITH r AS (
  SELECT Continente, PIBPerCapita AS v, 'PIBPerCapita' AS var,
         ROW_NUMBER() OVER (PARTITION BY Continente ORDER BY PIBPerCapita) AS rn,
         COUNT(*)     OVER (PARTITION BY Continente) AS n
  FROM vw_FactCompleta WHERE PIBPerCapita IS NOT NULL
  UNION ALL
  SELECT Continente, GastoSaludPerCapita, 'GastoSaludPerCapita',
         ROW_NUMBER() OVER (PARTITION BY Continente ORDER BY GastoSaludPerCapita),
         COUNT(*)     OVER (PARTITION BY Continente)
  FROM vw_FactCompleta WHERE GastoSaludPerCapita IS NOT NULL
  UNION ALL
  SELECT Continente, AguaPotable, 'AguaPotable',
         ROW_NUMBER() OVER (PARTITION BY Continente ORDER BY AguaPotable),
         COUNT(*)     OVER (PARTITION BY Continente)
  FROM vw_FactCompleta WHERE AguaPotable IS NOT NULL
  UNION ALL
  SELECT Continente, GastoSaludPctPIB, 'GastoSaludPctPIB',
         ROW_NUMBER() OVER (PARTITION BY Continente ORDER BY GastoSaludPctPIB),
         COUNT(*)     OVER (PARTITION BY Continente)
  FROM vw_FactCompleta WHERE GastoSaludPctPIB IS NOT NULL
)
SELECT Continente, var, AVG(v) AS Mediana
FROM r WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY Continente, var;

-- Los 12 KPI por continente (ponderados por población donde aplica)
CREATE VIEW vw_KPI_Continente AS
SELECT
  Continente,
  SUM(Poblacion)                                                         AS K01_PoblacionTotal,
  COUNT(DISTINCT CodigoPais)                                             AS K02_NumeroPaises,
  ROUND(SUM(EsperanzaVida * Poblacion) * 1.0 / SUM(Poblacion), 2)        AS K03_EsperanzaVidaPond,
  ROUND(SUM(MortalidadInfantil * Poblacion) * 1.0 / SUM(Poblacion), 2)   AS K04_MortalidadInfantilPond,
  ROUND(MAX(EsperanzaVida) - MIN(EsperanzaVida), 2)                      AS K05_BrechaLongevidad,
  ROUND(100.0 * SUM(CASE WHEN EsperanzaVida < 65 THEN Poblacion ELSE 0 END) / SUM(Poblacion), 2)
                                                                         AS K06_PctPobRiesgoLongevidad,
  ROUND(100.0 * SUM(CASE WHEN MortalidadInfantil > 50 THEN Poblacion ELSE 0 END) / SUM(Poblacion), 2)
                                                                         AS K07_PctPobRiesgoInfantil,
  (SELECT ROUND(Mediana, 0) FROM vw_Medianas m WHERE m.Continente = f.Continente AND var = 'PIBPerCapita')
                                                                         AS K08_PIBPerCapitaMediana,
  (SELECT ROUND(Mediana, 0) FROM vw_Medianas m WHERE m.Continente = f.Continente AND var = 'GastoSaludPerCapita')
                                                                         AS K09_GastoSaludMediana,
  ROUND(SUM(CASE WHEN MatriculaSecundaria IS NOT NULL THEN MatriculaSecundaria * Poblacion END) * 1.0
        / SUM(CASE WHEN MatriculaSecundaria IS NOT NULL THEN Poblacion END), 2)
                                                                         AS K10_MatriculaPond,
  (SELECT ROUND(Mediana, 1) FROM vw_Medianas m WHERE m.Continente = f.Continente AND var = 'AguaPotable')
                                                                         AS K11_AguaPotableMediana,
  COUNT(AguaPotable)                                                     AS K11_PaisesConDatoAgua,
  (SELECT ROUND(Mediana, 2) FROM vw_Medianas m WHERE m.Continente = f.Continente AND var = 'GastoSaludPctPIB')
                                                                         AS K12_GastoSaludPctPIBMediana
FROM vw_FactCompleta f
GROUP BY Continente;
"""

# ---------------------------------------------------------------------------
if os.path.exists(DB):
    os.remove(DB)                               # se reconstruye completo en cada corrida
con = sqlite3.connect(DB)
con.executescript(DDL)

hojas = pd.read_excel(LIBRO, sheet_name=None)
for tabla in ("DimPais", "DimPeriodo", "FactIndicadoresPais"):   # orden: primero dimensiones
    df = hojas[tabla]
    cols = [c[1] for c in con.execute(f"PRAGMA table_info({tabla})")]
    df = df[cols].astype(object).where(df[cols].notna(), None)
    con.executemany(f"INSERT INTO {tabla} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    df.values.tolist())
con.commit()
con.executescript(VISTAS)

# --- Controles de integridad del modelo ------------------------------------
fk = con.execute("PRAGMA foreign_key_check").fetchall()
conteos = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
           for t in ("DimPais", "DimPeriodo", "FactIndicadoresPais")}
huerfanos_dim = con.execute("""SELECT COUNT(*) FROM DimPais d
                               WHERE NOT EXISTS (SELECT 1 FROM FactIndicadoresPais f
                                                 WHERE f.CodigoPais = d.CodigoPais)""").fetchone()[0]
print("Filas:", conteos)
print("Violaciones de llave foránea:", len(fk))
print("Países de DimPais sin hechos:", huerfanos_dim)
print("Cardinalidad DimPais -> Fact: 1 a", con.execute(
    "SELECT MAX(c) FROM (SELECT COUNT(*) c FROM FactIndicadoresPais GROUP BY CodigoPais)").fetchone()[0])

kpi = pd.read_sql("SELECT * FROM vw_KPI_Continente", con)
print(kpi.T.to_string())

# --- Exportar datos para el dashboard (Fase 6) ------------------------------
plana = pd.read_sql("SELECT * FROM vw_FactCompleta ORDER BY Continente, Pais", con)
salida = {
    "meta": {
        "fuente": "Archivos del curso + World Development Indicators (Banco Mundial)",
        "anio_corte": int(hojas["DimPeriodo"]["Anio"].iloc[0]),
        "nota": "Último dato disponible desde 2015 por indicador; mortalidad infantil por 1.000 nacidos vivos",
    },
    "paises": json.loads(plana.to_json(orient="records", force_ascii=False)),
}
with open(JSON_OUT, "w", encoding="utf-8") as fh:
    json.dump(salida, fh, ensure_ascii=False)
print(f"\nOK -> {DB}  |  {JSON_OUT} ({len(plana)} países)")
con.close()
