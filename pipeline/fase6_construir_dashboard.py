"""
Taller 02 - Dashboard Banco Mundial
FASE 6: Construye el dashboard HTML a partir del modelo en estrella.

Uso:  python fase6_construir_dashboard.py "<plantilla_dashboard.html>" "<datos_dashboard.json>" "<Dashboard_BancoMundial.html>"

- Inserta datos_dashboard.json (fases 4 y 5, desde SQLite) dentro de la plantilla.
- Inserta la librería Plotly (libs/plotly.min.js) y el mapa mundial (libs/world_110m.json)
  DENTRO del archivo, para que el dashboard funcione sin internet y en vistas previas
  que bloquean scripts externos. Resultado: un único HTML autónomo.
Pipeline completo: fase1 -> fase3 -> fase4 -> fase5 -> fase6.
"""
import sys, os, json
plantilla, datos, salida = (sys.argv[1:4] + ["plantilla_dashboard.html", "datos_dashboard.json",
                                             "Dashboard_BancoMundial.html"][len(sys.argv) - 1:])[:3]
LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs")

def seguro(texto):                       # evita cerrar la etiqueta <script> antes de tiempo
    return texto.replace("</", "<\\/")

with open(datos, encoding="utf-8") as f:
    d = json.load(f)
assert {"meta", "paises", "analisis"} <= set(d), "Faltan secciones: ejecute las fases 4 y 5 primero"

with open(os.path.join(LIBS, "plotly.min.js"), encoding="utf-8") as f:
    plotly_js = f.read()
with open(os.path.join(LIBS, "world_110m.json"), encoding="utf-8") as f:
    mapa = f.read()

plotly_js = plotly_js.replace(chr(0xFFFD), chr(92) + "ufffd")   # carácter especial de Plotly, escrito como escape JS
bloque = (f"<script>\n{seguro(plotly_js)}\n</script>\n"
          # Plotly busca primero aquí el mapa antes de intentar descargarlo de internet
          f"<script>window.PlotlyGeoAssets = {{topojson: {{world_110m: {seguro(mapa)}}}}};</script>")

html = open(plantilla, encoding="utf-8").read()
assert "<!--__PLOTLY__-->" in html and "/*__DATOS__*/" in html, "La plantilla no tiene los marcadores esperados"
html = html.replace("<!--__PLOTLY__-->", bloque).replace("/*__DATOS__*/", seguro(json.dumps(d, ensure_ascii=False)))
with open(salida, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK -> {salida} ({len(d['paises'])} países, {len(html)/1024/1024:.1f} MB, funciona sin internet)")
