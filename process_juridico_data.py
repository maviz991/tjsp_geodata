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
REPO_BASE_URL = "https://github.com/open-geodata/sp_tjsp_divadmin/raw/refs/heads/main/sp_tjsp_divadmin/data/output/tab/"
MAPPING_CSV = REPO_BASE_URL + "Unidades%2C%20Munic%C3%ADpios%20e%20Comarcas.csv"
UNIDADES_CSV = REPO_BASE_URL + "Unidades.csv"

IBGE_GEO_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?formato=application/vnd.geo+json&intrarregiao=municipio"
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
            time.sleep(delay)

def main():
    print("Step 1: Loading inputs and GitHub data...")
    r_mapping = fetch_with_retry(MAPPING_CSV)
    df_mapping = pd.read_csv(io.StringIO(r_mapping.text)).map(lambda x: x.strip() if isinstance(x, str) else x)
    r_unidades = fetch_with_retry(UNIDADES_CSV)
    df_unidades = pd.read_csv(io.StringIO(r_unidades.text)).map(lambda x: x.strip() if isinstance(x, str) else x)
    
    # Cast and Clean
    df_mapping['id_municipio'] = df_mapping['id_municipio'].astype(int)
    df_unidades['id_comarca'] = pd.to_numeric(df_unidades['id_comarca'], errors='coerce').fillna(0).astype(int)
    df_unidades['id_cj'] = pd.to_numeric(df_unidades['id_cj'], errors='coerce').fillna(0).astype(int)
    df_unidades['num_varas_instaladas'] = pd.to_numeric(df_unidades['num_varas_instaladas'], errors='coerce').fillna(0).astype(int)

    print("Step 2: Linking Units and Varas...")
    # Map unit name to its vara count and entrancia
    # Note: Using comarca_key + unit_name to avoid duplicates across state
    df_unidades['unit_key'] = df_unidades['comarca_corrigido'] + "_" + df_unidades['unidade']
    df_mapping['unit_key'] = df_mapping['comarca_tjsp'] + "_" + df_mapping['unidades']
    
    unit_meta = df_unidades[['unit_key', 'num_varas_instaladas', 'entrancia']].drop_duplicates(subset='unit_key')
    df_mapping = df_mapping.merge(unit_meta, on='unit_key', how='left')

    print("Step 3: Consolidating Municipality Data...")
    # Aggregate by municipality
    agg_dict = {
        'unidades': lambda x: ", ".join(sorted(set(x.astype(str)))),
        'num_varas_instaladas': 'sum',
        'comarca_tjsp': 'first',
        'municipio_tjsp': 'first',
        'raj': 'first',
        'comarca_sede': 'max'
    }
    df_mun_agg = df_mapping.groupby('id_municipio').agg(agg_dict).reset_index()
    df_mun_agg = df_mun_agg.rename(columns={'num_varas_instaladas': 'total_varas_municipio'})

    # Step 4: Seat Mapping and Foro Data
    comarca_seat_map = df_mapping[df_mapping['comarca_sede'] == 1][['comarca_tjsp', 'id_municipio']].drop_duplicates()
    comarca_seat_map.columns = ['comarca_tjsp', 'id_foro_ibge']
    df_mun_agg = df_mun_agg.merge(comarca_seat_map, on='comarca_tjsp', how='left')
    
    # Foro Varas and Entrancia
    foro_meta = df_mun_agg.groupby('id_foro_ibge')['total_varas_municipio'].sum().reset_index()
    foro_meta.columns = ['id_foro_ibge', 'populacao_foro_varas'] # Temporary name
    
    # Get Seat Entrancia
    seat_entrancia = df_unidades.sort_values(by=['id_comarca', 'entrancia']).drop_duplicates(subset='id_comarca')[['id_comarca', 'entrancia']]
    seat_entrancia.columns = ['id_foro_ibge', 'entrancia_foro']

    print("Step 5: Fetching Geometries and Population...")
    pop_dict = {}
    r_pop = fetch_with_retry("https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93?localidades=N6[all]")
    for s in r_pop.json()[0]['resultados'][0]['series']:
        if str(s['localidade']['id']).startswith('35'): pop_dict[int(s['localidade']['id'])] = int(s['serie']['2022']) if s['serie']['2022'] and s['serie']['2022'] != "..." else 0
    
    gdf_mun = gpd.GeoDataFrame.from_features(fetch_with_retry(IBGE_GEO_URL).json()['features'])
    gdf_mun['id_municipio_ibge'] = gdf_mun['codarea'].astype(int)
    gdf_mun['populacao_municipio'] = gdf_mun['id_municipio_ibge'].map(pop_dict).fillna(0).astype(int)
    gdf_mun['centroid'] = gdf_mun.geometry.centroid

    print("Step 6: Final Join...")
    df_seats = df_unidades.sort_values(by=['id_comarca', 'unidade']).drop_duplicates(subset='id_comarca').copy()
    df_seats['endereco_sede'] = df_seats['endereco_lougradouro'] + ", " + df_seats['endereco_cep']
    df_seats = df_seats.merge(gdf_mun[['id_municipio_ibge', 'centroid']], left_on='id_comarca', right_on='id_municipio_ibge', how='left')
    df_seats['latitude'] = df_seats['centroid'].apply(lambda p: p.y if pd.notnull(p) else None)
    df_seats['longitude'] = df_seats['centroid'].apply(lambda p: p.x if pd.notnull(p) else None)
    
    # Merge all into rich mapping
    df_final = df_mun_agg.merge(foro_meta, on='id_foro_ibge', how='left')
    df_final = df_final.merge(seat_entrancia, on='id_foro_ibge', how='left')
    df_final = df_final.merge(df_seats[['id_comarca', 'endereco_sede', 'latitude', 'longitude', 'cj', 'id_cj']], left_on='id_foro_ibge', right_on='id_comarca', how='left')
    
    # CJ Meta
    cj_cities = df_final.groupby('id_cj')['municipio_tjsp'].apply(lambda x: ", ".join(sorted(set(x.astype(str))))).reset_index()
    cj_cities.columns = ['id_cj', 'cidades_na_cj']
    df_final = df_final.merge(cj_cities, on='id_cj', how='left')
    
    # Foro Cities Meta
    foro_cities = df_final.groupby('id_foro_ibge')['municipio_tjsp'].apply(lambda x: ", ".join(sorted(set(x.astype(str))))).reset_index()
    foro_cities.columns = ['id_foro_ibge', 'cidades_no_foro']
    df_final = df_final.merge(foro_cities, on='id_foro_ibge', how='left')

    # Final Schema Formatting
    gdf_state = gdf_mun.merge(df_final, left_on='id_municipio_ibge', right_on='id_municipio', how='inner')
    
    # Pop per foro
    foro_pop = gdf_state.groupby('id_foro_ibge')['populacao_municipio'].sum().reset_index()
    foro_pop.columns = ['id_foro_ibge', 'populacao_foro']
    gdf_state = gdf_state.merge(foro_pop, on='id_foro_ibge', how='left')
    
    gdf_state['id_foro'] = gdf_state['id_foro_ibge']
    gdf_state['id_raj'] = gdf_state['raj'].apply(lambda x: int(re.search(r'(\d+)', str(x)).group(1)) if re.search(r'(\d+)', str(x)) else 0)
    gdf_state['nome_foro'] = gdf_state['comarca_tjsp']
    gdf_state['nome_municipio'] = gdf_state['municipio_tjsp']
    gdf_state = gdf_state.rename(columns={'cj': 'nome_cj', 'raj': 'nome_raj', 'populacao_foro_varas': 'total_varas_foro', 'entrancia_foro': 'entrancia'})

    clean_cols = [
        'id_municipio_ibge', 'nome_municipio', 'populacao_municipio',
        'id_foro', 'nome_foro', 'total_varas_foro', 'entrancia',
        'endereco_sede', 'latitude', 'longitude',
        'id_cj', 'nome_cj', 'id_raj', 'nome_raj',
        'populacao_foro', 'cidades_no_foro', 'cidades_na_cj', 'unidades', 'total_varas_municipio'
    ]

    def finalize_layer(gdf):
        for col in clean_cols:
            if col not in gdf.columns: gdf[col] = None
        return gdf[clean_cols + (['geometry'] if 'geometry' in gdf.columns else [])]

    # Export
    print("Step 7: Saving Output Files...")
    finalize_layer(gdf_state).to_file(os.path.join(OUTPUT_DIR, "tjsp_municipios_sp.geojson"), driver='GeoJSON', encoding='utf-8')
    finalize_layer(gdf_state).drop(columns=['geometry']).to_csv(os.path.join(OUTPUT_DIR, "tjsp_mapeamento_bi.csv"), index=False, sep=';', encoding='utf-8-sig')
    
    # Points layer
    gdf_pts = gdf_state[gdf_state['id_municipio_ibge'] == gdf_state['id_foro_ibge']].copy()
    gdf_pts['geometry'] = gdf_pts['centroid']
    if not gdf_pts.empty:
        finalize_layer(gdf_pts).to_file(os.path.join(OUTPUT_DIR, "tjsp_foros_sedes_sp.geojson"), driver='GeoJSON', encoding='utf-8')

    print(f"\nSuccess! Mapping enriched with Varas and Entrancia.")

if __name__ == "__main__":
    main()
