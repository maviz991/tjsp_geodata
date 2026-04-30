import pandas as pd
import requests
import geopandas as gpd
from shapely.geometry import Point
import os
import json

# Configuration
FOROS_INTERESSE_PATH = "dados_input/foros_interesse_principal.csv"
REPO_BASE_URL = "https://github.com/open-geodata/sp_tjsp_divadmin/raw/refs/heads/main/sp_tjsp_divadmin/data/output/tab/"
MUNICIPIOS_CSV = REPO_BASE_URL + "Municipios.csv"
MAPPING_CSV = REPO_BASE_URL + "Unidades%2C%20Munic%C3%ADpios%20e%20Comarcas.csv"
UNIDADES_CSV = REPO_BASE_URL + "Unidades.csv"

IBGE_GEO_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?formato=application/vnd.geo+json&qualidade=maxima&intrarregiao=municipio"
SIDRA_URL = "https://api.sidra.ibge.gov.br/v1/values/t/9514/v/93/p/2022/n6/all?f=c"

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

import io
import time

def fetch_with_retry(url, method="GET", max_retries=3, delay=2, **kwargs):
    for i in range(max_retries):
        try:
            if method == "GET":
                r = requests.get(url, timeout=60, verify=False, **kwargs)
            else:
                r = requests.post(url, timeout=60, verify=False, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            if i == max_retries - 1:
                raise e
            print(f"Retry {i+1}/{max_retries} for {url} due to {e}")
            time.sleep(delay)

def main():
    print("Step 1: Loading inputs and GitHub data (June 2024 update)...")
    # Load foros of interest
    df_interesse = pd.read_csv(FOROS_INTERESSE_PATH, sep=';')
    df_interesse['foro_clean'] = df_interesse['foros_interesse_principal'].str.replace("Foro de ", "").str.strip()
    foros_list = set(df_interesse['foro_clean'].tolist())
    
    # Load mappings from GitHub
    r_mapping = fetch_with_retry(MAPPING_CSV)
    df_mapping = pd.read_csv(io.StringIO(r_mapping.text))
    r_unidades = fetch_with_retry(UNIDADES_CSV)
    df_unidades = pd.read_csv(io.StringIO(r_unidades.text))
    
    # Clean up mapping
    df_mapping = df_mapping.map(lambda x: x.strip() if isinstance(x, str) else x)
    
    # Propagate RAJ info: Some municipalities have "0ª RAJ" but others in the same Comarca have the correct one
    # 1. Identify "bad" RAJs
    df_mapping['is_bad_raj'] = df_mapping['raj'].str.contains("0ª RAJ", na=True)
    
    # 2. For each Comarca, find the best RAJ (first non-bad one)
    comarca_rajs = df_mapping.sort_values(by=['comarca_tjsp', 'is_bad_raj']).drop_duplicates(subset='comarca_tjsp')[['comarca_tjsp', 'raj']]
    comarca_rajs.columns = ['comarca_tjsp', 'best_raj']
    
    # 3. Merge back and override
    df_mapping = df_mapping.merge(comarca_rajs, on='comarca_tjsp', how='left')
    df_mapping['raj'] = df_mapping['best_raj']
    
    # 4. Final deduplication by municipality
    df_mapping = df_mapping.drop_duplicates(subset='id_municipio', keep='first')
    
    POP_API_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93?localidades=N6[all]"
    print("Step 2: Fetching IBGE Population (2022 Census)...")
    pop_dict = {}
    try:
        r_pop = fetch_with_retry(POP_API_URL, max_retries=2)
        pop_json = r_pop.json()
        series = pop_json[0]['resultados'][0]['series']
        for s in series:
            code = int(s['localidade']['id'])
            if str(code).startswith('35'): # Only SP
                val = s['serie']['2022']
                pop_dict[code] = int(val) if val and val != "..." else 0
        print(f"  - Successfully fetched population for {len(pop_dict)} municipalities.")
    except Exception as e:
        print(f"WARNING: Could not fetch population data ({e}). Continuing with 0 values.")
    
    print("Step 3: Fetching IBGE Geometries...")
    r_geo = fetch_with_retry(IBGE_GEO_URL)
    geo_json = r_geo.json()
    
    if 'features' in geo_json:
        gdf_mun = gpd.GeoDataFrame.from_features(geo_json['features'])
    elif isinstance(geo_json, list):
        gdf_mun = gpd.GeoDataFrame.from_features(geo_json)
    else:
        # Check if it's a TopoJSON or other
        print(f"Unexpected GeoJSON structure. Keys: {geo_json.keys() if isinstance(geo_json, dict) else 'Not a dict'}")
        # Try to use it directly if it's a FeatureCollection without 'features' key (unlikely)
        gdf_mun = gpd.GeoDataFrame.from_features(geo_json)
    gdf_mun['cod_mun'] = gdf_mun['codarea'].astype(int)
    gdf_mun['populacao_2022'] = gdf_mun['cod_mun'].map(pop_dict).fillna(0).astype(int)
    
    print("Step 4: Merging and Processing (Entire State with Rich Metadata)...")
    
    # Get CJ info for each Comarca from df_unidades
    df_comarca_cj = df_unidades[['comarca_corrigido', 'cj', 'id_cj']].drop_duplicates(subset='comarca_corrigido')
    
    # Merge mapping with CJ info
    df_full_map = df_mapping.merge(df_comarca_cj, left_on='comarca_tjsp', right_on='comarca_corrigido', how='left')
    
    # Ensure one entry per municipality to avoid duplicate geometries
    df_mapping_unique = df_full_map.drop_duplicates(subset='id_municipio').copy()
    
    # Pre-calculate aggregated lists of cities
    foro_cities = df_mapping_unique.groupby('comarca_tjsp', sort=False)['municipio_tjsp'].apply(lambda x: ", ".join(sorted(x.astype(str)))).reset_index()
    foro_cities.columns = ['comarca_tjsp', 'Lista Cidades Foro']
    
    # Note: 'cj' comes from df_unidades
    cj_cities = df_mapping_unique.groupby('cj', sort=False)['municipio_tjsp'].apply(lambda x: ", ".join(sorted(x.astype(str)))).reset_index()
    cj_cities.columns = ['cj', 'Lista Cidades CJ']
    
    # Merge mappings with these lists
    df_mapping_rich = df_mapping_unique.merge(foro_cities, on='comarca_tjsp', how='left')
    df_mapping_rich = df_mapping_rich.merge(cj_cities, on='cj', how='left')
    
    # Merge IBGE Geometries with Rich Mapping
    gdf_filtered = gdf_mun.merge(df_mapping_rich, left_on='cod_mun', right_on='id_municipio', how='inner')
    
    # Prepare metadata for Polygons
    meta_cols = {
        'comarca_tjsp': 'Nome do Foro',
        'id_comarca': 'ID Foro',
        'cj': 'Nome da CJ',
        'id_cj': 'ID CJ',
        'raj': 'Nome da RAJ',
        'municipio_tjsp': 'Nome do Municipio',
        'populacao_2022': 'Populacao',
        'Lista Cidades Foro': 'Cidades no Foro',
        'Lista Cidades CJ': 'Cidades na CJ'
    }
    
    available_cols = ['geometry'] + [c for c in meta_cols.keys() if c in gdf_filtered.columns]
    gdf_poly = gdf_filtered[available_cols].copy()
    gdf_poly.columns = ['geometry'] + [meta_cols[c] for c in available_cols if c != 'geometry']
    
    print("Step 5: Generating Layers...")
    
    # Layer 2: Municipalities (Polygons)
    poly_path = os.path.join(OUTPUT_DIR, "municipios_atendidos_sp.geojson")
    gdf_poly.to_file(poly_path, driver='GeoJSON', encoding='utf-8')
    print(f"  - Rich Polygon layer saved to {poly_path}")
    
    # Layer 1: Forum Seats (Points)
    df_unidades['is_principal'] = df_unidades['unidade'].str.contains("PRINCIPAL", case=False, na=False)
    df_seats_meta = df_unidades.sort_values(by=['comarca_corrigido', 'is_principal'], ascending=[True, False])
    df_seats_meta = df_seats_meta.drop_duplicates(subset='comarca_corrigido')
    
    df_seats_final = df_seats_meta.merge(df_mapping_rich.drop_duplicates(subset='comarca_tjsp'), 
                                         left_on='comarca_corrigido', right_on='comarca_tjsp', how='inner')
    
    seats_spatial = []
    name_col = next((c for c in gdf_mun.columns if c.lower() in ['nome', 'nm_mun', 'nm_municipio', 'name']), None)

    for _, row in df_seats_final.iterrows():
        foro = row['comarca_tjsp']
        city = row['endereco_municipio']
        address = f"{row['endereco_lougradouro']}, {row['endereco_cep']}"
        
        city_geo = gdf_mun[gdf_mun[name_col].str.upper() == city.upper()] if name_col else pd.DataFrame()
        if city_geo.empty:
            # Filter using the original column name in gdf_filtered
            city_geo = gdf_filtered[gdf_filtered['comarca_tjsp'] == foro].head(1)
            
        if not city_geo.empty:
            geom = city_geo.iloc[0]['geometry'].centroid
            seats_spatial.append({
                'geometry': geom,
                'ID Foro': row.get('id_comarca_x', row.get('id_comarca', '')),
                'Nome do Foro': foro,
                'Endereco': address,
                'Nome da CJ': row.get('cj_x', row.get('cj', '')),
                'ID CJ': row.get('id_cj_x', row.get('id_cj', '')),
                'Nome da RAJ': row.get('raj', ''),
                'Cidades no Foro': row.get('Lista Cidades Foro', ''),
                'Cidades na CJ': row.get('Lista Cidades CJ', ''),
                'Populacao Municipio Sede': city_geo.iloc[0]['populacao_2022'] if 'populacao_2022' in city_geo.columns else 0
            })
            
    gdf_seats = gpd.GeoDataFrame(seats_spatial, crs=gdf_filtered.crs)
    points_path = os.path.join(OUTPUT_DIR, "foros_sedes_sp.geojson")
    gdf_seats.to_file(points_path, driver='GeoJSON', encoding='utf-8')
    print(f"  - Rich Point layer saved to {points_path}")
    
    print("\nProcessing complete!")
    print(f"Total forums processed: {len(gdf_seats)}")
    print(f"Total municipalities included: {len(gdf_poly)}")

if __name__ == "__main__":
    main()
