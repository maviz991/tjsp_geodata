import os
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Carrega credenciais do .env
load_dotenv()

def upload_to_postgis():
    # Configuração da conexão
    try:
        db_url = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        engine = create_engine(db_url)
        
        print(f"Conectando ao banco {os.getenv('DB_NAME')} em {os.getenv('DB_HOST')}...")
        
        # 1. Upload dos Municípios (Polígonos)
        poly_file = "output/tjsp_municipios_sp.geojson"
        if os.path.exists(poly_file):
            print("Subindo Polígonos (Municípios/Distritos)...")
            gdf_poly = gpd.read_file(poly_file)
            gdf_poly.to_postgis("tjsp_municipios_sp", engine, if_exists='replace', index=False)
        
        # 2. Upload das Sedes (Pontos)
        seats_file = "output/tjsp_foros_sedes_sp.geojson"
        if os.path.exists(seats_file):
            print("Subindo Pontos (Sedes dos Foros)...")
            gdf_seats = gpd.read_file(seats_file)
            gdf_seats.to_postgis("tjsp_foros_sedes_sp", engine, if_exists='replace', index=False)
        
        # 3. Upload da Tabela BI (CSV)
        csv_file = "output/tjsp_mapeamento_bi.csv"
        if os.path.exists(csv_file):
            print("Subindo Tabela BI (CSV)...")
            df_bi = pd.read_csv(csv_file, sep=';', encoding='utf-8-sig')
            df_bi.to_sql("tjsp_mapeamento_bi", engine, if_exists='replace', index=False)
        
        print("\nETL concluído com sucesso!")
    except Exception as e:
        print(f"Erro no ETL: {e}")

if __name__ == "__main__":
    upload_to_postgis()
