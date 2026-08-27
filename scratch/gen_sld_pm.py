import geopandas as gpd
import colorsys

def xml_escape(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def gen_colors(n):
    colors = []
    for i in range(n):
        h = i / n
        r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.85)
        colors.append('#%02x%02x%02x' % (int(r*255), int(g*255), int(b*255)))
    return colors

gdf = gpd.read_file('output/pm_batalhoes_sp.geojson')
combos = gdf[['id_comando', 'nome_comando']].drop_duplicates().sort_values('id_comando')
colors = gen_colors(len(combos))

rules = []
for (id_comando, nome_comando), color in zip(combos.itertuples(index=False), colors):
    rules.append(f'''        <se:Rule>
          <se:Name>{xml_escape(id_comando)}</se:Name>
          <se:Description>
            <se:Title>{xml_escape(nome_comando)}</se:Title>
          </se:Description>
          <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>id_comando</ogc:PropertyName>
              <ogc:Literal>{xml_escape(id_comando)}</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <se:PolygonSymbolizer>
            <se:Fill>
              <se:SvgParameter name="fill">{color}</se:SvgParameter>
            </se:Fill>
            <se:Stroke>
              <se:SvgParameter name="stroke">#232323</se:SvgParameter>
              <se:SvgParameter name="stroke-width">0.5</se:SvgParameter>
              <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
            </se:Stroke>
          </se:PolygonSymbolizer>
        </se:Rule>''')

else_rule = '''        <se:Rule>
          <se:Name></se:Name>
          <se:Description>
            <se:Title>"id_comando" is ''</se:Title>
          </se:Description>
          <se:ElseFilter xmlns:se="http://www.opengis.net/se"/>
          <se:PolygonSymbolizer>
            <se:Fill>
              <se:SvgParameter name="fill">#de4624</se:SvgParameter>
            </se:Fill>
            <se:Stroke>
              <se:SvgParameter name="stroke">#232323</se:SvgParameter>
              <se:SvgParameter name="stroke-width">0.5</se:SvgParameter>
              <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
            </se:Stroke>
          </se:PolygonSymbolizer>
        </se:Rule>'''

sld = f'''<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:se="http://www.opengis.net/se" xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/StyledLayerDescriptor.xsd" version="1.1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xlink="http://www.w3.org/1999/xlink">
  <NamedLayer>
    <se:Name>pm_batalhoes_sp</se:Name>
    <UserStyle>
      <se:Name>pm_batalhoes_sp</se:Name>
      <se:FeatureTypeStyle>
{chr(10).join(rules)}
{else_rule}
      </se:FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
'''

with open('output/estilo_pm_comando.sld', 'w', encoding='utf-8') as f:
    f.write(sld)

print("SLD written with", len(combos), "rules")
