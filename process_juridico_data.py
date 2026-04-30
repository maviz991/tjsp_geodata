import pandas as pd
import requests
import geopandas as gpd
from shapely.geometry import Point
import os
import json
import io
import time
import re

# Configuration
FOROS_INTERESSE_PATH = "dados_input/foros_interesse_principal.csv"
REPO_BASE_URL = "https://github.com/open-geodata/sp_tjsp_divadmin/raw/refs/heads/main/sp_tjsp_divadmin/data/output/tab/"
MUNICIPIOS_CSV = REPO_BASE_URL + "Municipios.csv"
MAPPING_CSV = REPO_BASE_URL + "Unidades%2C%20Munic%C3%ADpios%20e%20Comarcas.csv"
UNIDADES_CSV = REPO_BASE_URL + "Unidades.csv"

IBGE_GEO_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?formato=application/vnd.geo+json&qualidade=maxima&intrarregiao=municipio"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_with_retry(url, method="GET", max_retries=3, delay=2, **kwargs):
    for i in range(max_retries):
        try:
            r = requests.get(url, timeout=60, verify=False, **kwargs) if method == "GET" else requests.post(url, timeout=60, verify=False, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            if i == max_retries - 1: raise e
            print(f"Retry {i+1}/{max_retries} for {url} due to {e}")
            time.sleep(delay)

def generate_sld_poly(rajs):
    # Palette of 10 pleasant colors for RAJs
    colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe"]
    rules = ""
    for i, raj in enumerate(sorted(rajs)):
        color = colors[i % len(colors)]
        rules += f"""
        <se:Rule>
          <se:Name>{raj}</se:Name>
          <se:Description>
            <se:Title>{raj}</se:Title>
          </se:Description>
          <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>nome_raj</ogc:PropertyName>
              <ogc:Literal>{raj}</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <se:PolygonSymbolizer>
            <se:Fill>
              <se:SvgParameter name="fill">{color}</se:SvgParameter>
              <se:SvgParameter name="fill-opacity">0.6</se:SvgParameter>
            </se:Fill>
            <se:Stroke>
              <se:SvgParameter name="stroke">#232323</se:SvgParameter>
              <se:SvgParameter name="stroke-width">0.5</se:SvgParameter>
            </se:Stroke>
          </se:PolygonSymbolizer>
        </se:Rule>"""
    
    sld = f"""<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.1.0" xmlns:xlink="http://www.w3.org/1999/xlink" xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/StyledLayerDescriptor.xsd" xmlns:se="http://www.opengis.net/se">
  <NamedLayer>
    <se:Name>tjsp_municipios_sp</se:Name>
    <UserStyle>
      <se:Name>tjsp_municipios_sp</se:Name>
      <se:FeatureTypeStyle>
        {rules}
      </se:FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>"""
    return sld

def main():
    print("Step 1: Loading inputs and GitHub data (June 2024 update)...")
    r_mapping = fetch_with_retry(MAPPING_CSV)
    df_mapping = pd.read_csv(io.StringIO(r_mapping.text))
    r_unidades = fetch_with_retry(UNIDADES_CSV)
    df_unidades = pd.read_csv(io.StringIO(r_unidades.text))
    
    df_mapping = df_mapping.map(lambda x: x.strip() if isinstance(x, str) else x)
    df_mapping['is_bad_raj'] = df_mapping['raj'].str.contains("0ª RAJ", na=True)
    comarca_rajs = df_mapping.sort_values(by=['comarca_tjsp', 'is_bad_raj']).drop_duplicates(subset='comarca_tjsp')[['comarca_tjsp', 'raj']]
    comarca_rajs.columns = ['comarca_tjsp', 'best_raj']
    df_mapping = df_mapping.merge(comarca_rajs, on='comarca_tjsp', how='left')
    df_mapping['raj'] = df_mapping['best_raj']
    df_mapping = df_mapping.drop_duplicates(subset='id_municipio', keep='first')
    
    POP_API_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93?localidades=N6[all]"
    print("Step 2: Fetching IBGE Population (2022 Census)...")
    pop_dict = {}
    r_pop = fetch_with_retry(POP_API_URL)
    series = r_pop.json()[0]['resultados'][0]['series']
    for s in series:
        code = int(s['localidade']['id'])
        if str(code).startswith('35'):
            val = s['serie']['2022']
            pop_dict[code] = int(val) if val and val != "..." else 0
    
    print("Step 3: Fetching IBGE Geometries...")
    r_geo = fetch_with_retry(IBGE_GEO_URL)
    gdf_mun = gpd.GeoDataFrame.from_features(r_geo.json()['features'])
    gdf_mun['cod_mun'] = gdf_mun['codarea'].astype(int)
    gdf_mun['populacao_2022'] = gdf_mun['cod_mun'].map(pop_dict).fillna(0).astype(int)
    
    print("Step 4: Processing Judicial Mapping...")
    foro_cities = df_mapping.groupby('comarca_tjsp')['municipio_tjsp'].apply(lambda x: ", ".join(sorted(x.astype(str)))).reset_index()
    foro_cities.columns = ['comarca_tjsp', 'Lista Cidades Foro']
    
    df_unidades_cj = df_unidades[['comarca_corrigido', 'cj', 'id_cj']].drop_duplicates(subset='comarca_corrigido')
    df_mapping_rich = df_mapping.merge(foro_cities, on='comarca_tjsp', how='left').merge(df_unidades_cj, left_on='comarca_tjsp', right_on='comarca_corrigido', how='left')
    
    cj_cities = df_mapping_rich.groupby('cj')['municipio_tjsp'].apply(lambda x: ", ".join(sorted(x.astype(str)))).reset_index()
    cj_cities.columns = ['cj', 'Lista Cidades CJ']
    df_mapping_rich = df_mapping_rich.merge(cj_cities, on='cj', how='left')
    
    gdf_filtered = gdf_mun.merge(df_mapping_rich, left_on='cod_mun', right_on='id_municipio', how='inner')
    gdf_filtered['id_foro'] = pd.factorize(gdf_filtered['comarca_tjsp'])[0] + 1
    def extract_raj_id(raj_str):
        if pd.isna(raj_str): return 0
        match = re.search(r'(\d+)', str(raj_str))
        return int(match.group(1)) if match else 0
    gdf_filtered['id_raj_num'] = gdf_filtered['raj'].apply(extract_raj_id)
    
    foro_pop = gdf_filtered.groupby('comarca_tjsp')['populacao_2022'].sum().reset_index()
    foro_pop.columns = ['comarca_tjsp', 'pop_foro']
    gdf_filtered = gdf_filtered.merge(foro_pop, on='comarca_tjsp', how='left')
    
    print("Step 5: Synthesizing Master Data...")
    df_unidades['is_principal'] = df_unidades['unidade'].str.contains("PRINCIPAL", case=False, na=False)
    df_seats_meta = df_unidades.sort_values(by=['comarca_corrigido', 'is_principal'], ascending=[True, False]).drop_duplicates(subset='comarca_corrigido')
    
    seat_lookup_data = []
    name_col = next((c for c in gdf_mun.columns if c.lower() in ['nome', 'nm_mun', 'nm_municipio', 'name']), None)
    for _, row in df_seats_meta.iterrows():
        foro, city, address = row['comarca_corrigido'], row['endereco_municipio'], f"{row['endereco_lougradouro']}, {row['endereco_cep']}"
        city_geo = gdf_mun[gdf_mun[name_col].str.upper() == city.upper()] if name_col else pd.DataFrame()
        if city_geo.empty: city_geo = gdf_filtered[gdf_filtered['comarca_tjsp'] == foro].head(1)
        if not city_geo.empty:
            geom = city_geo.iloc[0]['geometry'].centroid
            seat_lookup_data.append({'comarca_tjsp': foro, 'endereco_sede': address, 'latitude': geom.y, 'longitude': geom.x})
    df_seat_lookup = pd.DataFrame(seat_lookup_data)
    
    df_master = gdf_filtered.merge(df_seat_lookup, on='comarca_tjsp', how='left')
    meta_cols_map = {
        'cod_mun': 'id_municipio_ibge', 'municipio_tjsp': 'nome_municipio', 'populacao_2022': 'populacao_municipio',
        'id_foro': 'id_foro', 'comarca_tjsp': 'nome_foro', 'endereco_sede': 'endereco_sede',
        'latitude': 'latitude', 'longitude': 'longitude', 'id_cj': 'id_cj', 'cj': 'nome_cj',
        'id_raj_num': 'id_raj', 'raj': 'nome_raj', 'pop_foro': 'populacao_foro',
        'Lista Cidades Foro': 'cidades_no_foro', 'Lista Cidades CJ': 'cidades_na_cj'
    }
    df_master = df_master.rename(columns=meta_cols_map)
    final_cols = ['id_municipio_ibge', 'nome_municipio', 'populacao_municipio', 'id_foro', 'nome_foro', 'endereco_sede', 'latitude', 'longitude', 'id_cj', 'nome_cj', 'id_raj', 'nome_raj', 'populacao_foro', 'cidades_no_foro', 'cidades_na_cj']
    df_master = df_master[final_cols + ['geometry']]
    
    print("Step 6: Generating Final Outputs...")
    df_master.drop(columns=['geometry']).to_csv(os.path.join(OUTPUT_DIR, "tjsp_mapeamento_bi.csv"), index=False, sep=';', encoding='utf-8-sig')
    
    gdf_poly = gpd.GeoDataFrame(df_master, geometry='geometry', crs=gdf_mun.crs)
    gdf_poly.to_file(os.path.join(OUTPUT_DIR, "tjsp_municipios_sp.geojson"), driver='GeoJSON', encoding='utf-8')
    
    df_seats = df_master.drop_duplicates(subset=['nome_foro'])
    gdf_seats = gpd.GeoDataFrame(df_seats, geometry=[Point(x, y) for x, y in zip(df_seats.longitude, df_seats.latitude)], crs=gdf_mun.crs)
    gdf_seats.to_file(os.path.join(OUTPUT_DIR, "tjsp_foros_sedes_sp.geojson"), driver='GeoJSON', encoding='utf-8')
    
    gdf_raj = gdf_poly.dissolve(by='nome_raj', aggfunc='first').reset_index()
    gdf_raj.to_file(os.path.join(OUTPUT_DIR, "tjsp_fronteiras_raj.geojson"), driver='GeoJSON', encoding='utf-8')
    
    # Generate SLD
    with open(os.path.join(OUTPUT_DIR, "tjsp_municipios_style.sld"), "w", encoding="utf-8") as f:
        f.write(generate_sld_poly(gdf_poly['nome_raj'].unique()))
    
    print("\nProcessing complete! SLD style generated in output/tjsp_municipios_style.sld")

if __name__ == "__main__":
    main()
