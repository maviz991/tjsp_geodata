import geopandas as gpd
import colorsys
import os

OUTPUT_DIR = "output"


def gen_colors(n):
    colors = []
    for i in range(n):
        h = i / n
        r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.85)
        colors.append('#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255)))
    return colors


def write_solid_polygon_css(filename, color, opacity, legend_title, title):
    # Only one rule matches every feature here, so the GeoServer CSS "multiple
    # matching rules all get drawn" behavior that breaks a categorical + "* {}"
    # combo doesn't apply — a single universal rule is safe.
    css = f"""/* {title} — cor única (sem categorização por comando) */

/* @title {legend_title} */
* {{
  fill: {color};
  fill-opacity: {opacity};
  stroke: #232323;
  stroke-width: 0.4;
}}
"""
    with open(os.path.join(OUTPUT_DIR, filename), 'w', encoding='utf-8') as f:
        f.write(css)
    print(f"  wrote {filename}")


def write_solid_point_css(filename, color, mark_size, label_field, legend_title, title):
    rule_body = f"""  mark: symbol(circle);
  mark-size: {mark_size};"""
    if label_field:
        rule_body += f"""
  label: [{label_field}];
  font-fill: #232323;
  font-size: 9;
  halo-color: #ffffff;
  halo-radius: 1.5;
  label-anchor: 0 0.5;
  label-offset: {mark_size / 2 + 3} 0;"""
    rule_body += f"""
  :mark {{
    fill: {color};
    fill-opacity: 0.9;
    stroke: #232323;
    stroke-width: 0.6;
  }}"""
    css = f"""/* {title} — cor única (sem categorização por comando), tamanho {mark_size}px */

/* @title {legend_title} */
* {{
{rule_body}
}}
"""
    with open(os.path.join(OUTPUT_DIR, filename), 'w', encoding='utf-8') as f:
        f.write(css)
    print(f"  wrote {filename}")


def write_categorical_polygon_css(filename, field, categories, colors, legend_titles, title):
    # No catch-all "* {}" rule: GeoServer's CSS module stacks every matching rule as
    # a separate symbolizer instead of the last match winning like normal CSS — a
    # feature that already matches its [field = '...'] rule would ALSO match "*",
    # painting a second (gray) symbol on top of the colored one. Since every feature
    # here always has one of these category values, a catch-all is unnecessary.
    # "/* @title ... */" immediately before a rule is GeoServer CSS's own syntax for
    # a rule title — without it, GetLegendGraphic draws the swatch with no caption.
    lines = [f"/* {title} — preencher por {field} (categórico, {len(categories)} categorias) */"]
    for cat, color in zip(categories, colors):
        cat_escaped = cat.replace("'", "\\'")
        legend_title = legend_titles.get(cat, cat)
        lines.append(f"""/* @title {legend_title} */
[{field} = '{cat_escaped}'] {{
  fill: {color};
  fill-opacity: 0.85;
  stroke: #232323;
  stroke-width: 0.4;
}}""")
    with open(os.path.join(OUTPUT_DIR, filename), 'w', encoding='utf-8') as f:
        f.write("\n\n".join(lines) + "\n")
    print(f"  wrote {filename} ({len(categories)} rules)")


def write_categorical_point_css(filename, field, categories, colors, mark_size, label_field, legend_titles, title):
    """Point layer colored by the same id_comando categories/palette as the polygon
    layers, so a point visually ties back to the comando's fill color underneath it
    when layers are viewed together — more useful on a shared map than a flat
    interior/metropolitano split, which is already obvious from position alone."""
    # fill/stroke for an explicit mark must be nested under ":mark" — a flat sibling
    # "fill:" next to "mark: symbol(...)" is silently ignored by GeoServer's CSS
    # compiler, which falls back to its default (gray) mark fill instead of erroring.
    # The nested ":mark { }" block must come LAST in the rule — any flat property
    # declared after it is a parse error ("Invalid input ..., expected ... '}'").
    # "/* @title ... */" immediately before a rule is GeoServer CSS's own syntax for
    # a rule title — without it, GetLegendGraphic draws the swatch with no caption.
    lines = [f"/* {title} — ponto colorido por {field} (mesma paleta dos polígonos), tamanho {mark_size}px */"]
    for cat, color in zip(categories, colors):
        cat_escaped = cat.replace("'", "\\'")
        legend_title = legend_titles.get(cat, cat)
        rule = f"""/* @title {legend_title} */
[{field} = '{cat_escaped}'] {{
  mark: symbol(circle);
  mark-size: {mark_size};"""
        if label_field:
            rule += f"""
  label: [{label_field}];
  font-fill: #232323;
  font-size: 9;
  halo-color: #ffffff;
  halo-radius: 1.5;
  label-anchor: 0 0.5;
  label-offset: {mark_size / 2 + 3} 0;"""
        rule += f"""
  :mark {{
    fill: {color};
    fill-opacity: 0.9;
    stroke: #232323;
    stroke-width: 0.6;
  }}
}}"""
        lines.append(rule)
    # No catch-all "* {}" rule here either — same stacking issue as the polygon
    # styles (see write_categorical_polygon_css).
    with open(os.path.join(OUTPUT_DIR, filename), 'w', encoding='utf-8') as f:
        f.write("\n\n".join(lines) + "\n")
    print(f"  wrote {filename}")


def main():
    print("Loading data for category lists...")
    gdf_btl_poly = gpd.read_file(os.path.join(OUTPUT_DIR, "pmesp_batalhoes_sp_polygon.geojson"))
    combos = gdf_btl_poly[['id_comando', 'nome_comando']].drop_duplicates().sort_values('id_comando')
    comandos = combos['id_comando'].tolist()
    legend_titles = dict(zip(combos['id_comando'], combos['nome_comando']))
    colors = gen_colors(len(comandos))
    print(f"  {len(comandos)} comandos found for categorical coloring.")

    print("Writing polygon layer styles (categorical by id_comando)...")
    write_categorical_polygon_css(
        "pmesp_municipios_sp_polygon.css", "id_comando", comandos, colors, legend_titles,
        "pmesp_municipios_sp_polygon (municípios por comando)"
    )
    write_categorical_polygon_css(
        "pmesp_batalhoes_sp_polygon.css", "id_comando", comandos, colors, legend_titles,
        "pmesp_batalhoes_sp_polygon (batalhões por comando)"
    )

    print("Writing point layer styles (by id_comando, same palette as polygons, size scaled to hierarchy level)...")
    write_categorical_point_css(
        "pmesp_1_comandos_sp_pontos.css", "id_comando", comandos, colors, 16,
        None, legend_titles, "pmesp_1_comandos_sp_pontos (comandos)"
    )
    write_categorical_point_css(
        "pmesp_2_batalhoes_sp_pontos.css", "id_comando", comandos, colors, 11,
        None, legend_titles, "pmesp_2_batalhoes_sp_pontos (sedes de batalhão)"
    )
    write_categorical_point_css(
        "pmesp_3_companhias_sp_pontos.css", "id_comando", comandos, colors, 7,
        None, legend_titles, "pmesp_3_companhias_sp_pontos (companhias)"
    )
    write_categorical_point_css(
        "pmesp_4_pelotoes_sp_pontos.css", "id_comando", comandos, colors, 5,
        None, legend_titles, "pmesp_4_pelotoes_sp_pontos (pelotões)"
    )
    write_categorical_point_css(
        "pmesp_5_grupos_sp_pontos.css", "id_comando", comandos, colors, 3,
        None, legend_titles, "pmesp_5_grupos_sp_pontos (grupos/esquadras)"
    )

    print("Writing solid single-color alternatives (one flat color per layer, no categorization)...")
    # One distinct color per hierarchy level, so all 7 layers stay visually
    # distinguishable from each other when viewed together on the same map —
    # uniform within a layer, instead of the categorical-by-comando styles above.
    write_solid_polygon_css(
        "pmesp_municipios_sp_polygon_solid.css", "#e5e5e5", 0.6, "Municípios",
        "pmesp_municipios_sp_polygon (município, cor única)"
    )
    write_solid_polygon_css(
        "pmesp_batalhoes_sp_polygon_solid.css", "#fca311", 0.5, "Batalhões",
        "pmesp_batalhoes_sp_polygon (batalhão, cor única)"
    )
    write_solid_point_css(
        "pmesp_1_comandos_sp_pontos_solid.css", "#e63946", 16, None, "Comandos",
        "pmesp_1_comandos_sp_pontos (comando, cor única)"
    )
    write_solid_point_css(
        "pmesp_2_batalhoes_sp_pontos_solid.css", "#f4a261", 11, None, "Batalhões",
        "pmesp_2_batalhoes_sp_pontos (batalhão, cor única)"
    )
    write_solid_point_css(
        "pmesp_3_companhias_sp_pontos_solid.css", "#2a9d8f", 7, None, "Companhias",
        "pmesp_3_companhias_sp_pontos (companhia, cor única)"
    )
    write_solid_point_css(
        "pmesp_4_pelotoes_sp_pontos_solid.css", "#264653", 5, None, "Pelotões",
        "pmesp_4_pelotoes_sp_pontos (pelotão, cor única)"
    )
    write_solid_point_css(
        "pmesp_5_grupos_sp_pontos_solid.css", "#6a4c93", 3, None, "Grupos/Esquadras",
        "pmesp_5_grupos_sp_pontos (grupo/esquadra, cor única)"
    )

    print("\nDone. 14 CSS files written to output/ (7 categóricos por comando + 7 de cor única).")


if __name__ == "__main__":
    main()
