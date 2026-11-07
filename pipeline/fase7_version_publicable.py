"""
Taller 02 - FASE 7: Versión publicable con marca neutra ("Observatorio Global de Salud")

Uso:  python fase7_version_publicable.py "<plantilla_dashboard.html>" "<datos_dashboard.json>" "<carpeta libs>" "<salida.html>" ["<salida_publicar.html>"]

Parte de la misma plantilla y los mismos datos del dashboard de la Fase 6, pero:
  - reemplaza la identidad del Banco Mundial (encabezado y avisos) por una marca neutra;
  - incluye Plotly y el mapa DENTRO del archivo (funciona sin internet y aunque la red bloquee CDNs);
  - <salida.html>: archivo completo para abrir localmente;
  - <salida_publicar.html> (opcional): mismo contenido sin <html>/<head>/<body>, porque la
    plataforma de publicación agrega ese esqueleto.
Los créditos de fuente (World Development Indicators del Banco Mundial) se mantienen.
"""
import sys, os, json, re
plantilla, datos, libs, salida = sys.argv[1:5]
salida_pub = sys.argv[5] if len(sys.argv) > 5 else None
seguro = lambda t: t.replace("</", "<\\/")
leer = lambda p: open(p, encoding="utf-8").read()
html = leer(plantilla)

bloque_libs = (f"<script>\n{seguro(leer(os.path.join(libs, 'plotly.min.js'))).replace(chr(0xFFFD), chr(92) + 'ufffd')}\n</script>\n"
               f"<script>window.PlotlyGeoAssets = {{topojson: {{world_110m: {seguro(leer(os.path.join(libs, 'world_110m.json')))}}}}};</script>")
reemplazos = [
    ("<title>Brechas Globales de Salud</title>", "<title>Observatorio Global de Salud</title>"),
    ("<span>No es un sitio oficial del Banco Mundial</span>", "<span>Fuentes públicas · Corte 2025</span>"),
    ("<!-- Iconografía genérica (globo). Reemplazar por el logotipo oficial si el docente lo exige. -->", ""),
    ("<b>Banco Mundial · Datos</b>", "<b>Observatorio Global de Salud</b>"),
    ('<p class="aviso">Prototipo académico. No es un sitio ni una publicación oficial del Banco Mundial.</p>',
     '<p class="aviso">Proyecto académico independiente construido con datos públicos.</p>'),
    (".filtros{position:sticky;top:0;", ".filtros{position:sticky;top:env(safe-area-inset-top,0px);"),
    ("<!--__PLOTLY__-->", bloque_libs),
    ("/*__DATOS__*/", seguro(json.dumps(json.load(open(datos, encoding="utf-8")), ensure_ascii=False))),
]
for a, b in reemplazos:
    assert a in html, f"No se encontró en la plantilla: {a[:60]}"
    html = html.replace(a, b)
assert "Banco Mundial · Datos" not in html and "oficial del Banco Mundial" not in html

open(salida, "w", encoding="utf-8").write(html)                     # versión local completa
print(f"OK local    -> {salida} ({len(html)/1024/1024:.1f} MB)")
if salida_pub:
    pub = html
    for patron in [r"<!DOCTYPE html>\s*", r'<html lang="es">\s*', r"<head>\s*", r"</head>\s*", r"<body>\s*",
                   r"</body>\s*", r"</html>\s*", r'<meta charset="utf-8">\s*', r'<meta name="viewport"[^>]*>\s*']:
        pub = re.sub(patron, "", pub, count=1)
    open(salida_pub, "w", encoding="utf-8").write(pub)
    print(f"OK publicar -> {salida_pub} ({len(pub)/1024/1024:.1f} MB)")
