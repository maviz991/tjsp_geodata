import pandas as pd
import numpy as np
import geopandas as gpd
import requests
import json
import os
import re
import time
import unicodedata
from collections import Counter
from dotenv import load_dotenv
from shapely.geometry import Point, Polygon, MultiPolygon

load_dotenv()

# Configuration
OPM_API = "https://servicesapp.policiamilitar.sp.gov.br/Pmesp.Unidades.Policiais.Api/api/v1/unidadespoliciais/Opm/enderecos"
IBGE_GEO_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?formato=application/vnd.geo+json&intrarregiao=municipio"
IBGE_MUN_LIST_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35/municipios"
IBGE_POP_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/9514/periodos/2022/variaveis/93?localidades=N6[all]"
GEOSAMPA_WFS = "http://wfs.geosampa.prefeitura.sp.gov.br/geoserver/ows"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "juridico-pm-mapeamento-sp/1.0 (matheus.aviz27@gmail.com)"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GEOCODE_CACHE_PATH = os.path.join("scratch", "geocode_cache.json")

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BTL_PATTERN = re.compile(r'^\d+\.BPM/[IM]$')

# PM city names that don't auto-match IBGE names after accent-stripping
# (apostrophe variants and one hyphenated name)
MANUAL_NAME_FIX = {
    "APARECIDA D OESTE": "APARECIDA D'OESTE",
    "ESTRELA D OESTE": "ESTRELA D'OESTE",
    "GUARANI D OESTE": "GUARANI D'OESTE",
    "MOGI-MIRIM": "MOGI MIRIM",
    "SANTA BARBARA D OESTE": "SANTA BARBARA D'OESTE",
    "SANTA CLARA D OESTE": "SANTA CLARA D'OESTE",
    "SANTA RITA D OESTE": "SANTA RITA D'OESTE",
    "SAO JOAO DO PAU D ALHO": "SAO JOAO DO PAU D'ALHO",
}

# Battalions that still appear in the official OPM registry but are confirmed extinct
# in practice — the API hasn't caught up. Excluded entirely rather than remapped: we
# only know the unit was subordinated to another, not how each of its sub-units
# (companies/platoons) individually redistributed, so folding its records into the
# surviving battalion's counts would be a guess. Add entries here as more are found
# and confirmed (see dicionario_dados_pm.md for sourcing on each).
KNOWN_DEFUNCT_BATTALIONS = {
    # 44º BPM/M (Parque Cecap, Guarulhos): fechado em 02/2022, atividades unificadas
    # ao 31º BPM/M (nota oficial da SSP-SP via clickguarulhos.com.br, 21/02/2022).
    # O prédio reabriu em 04/2022 como sede do 15º BAEP (unidade tática, não
    # territorial) — confirmado por reportagem e nota do governo (guarulhosweb.com.br,
    # bibliotecajuridica.sp.gov.br). Achado e reportado pelo usuário via Street View.
    "44.BPM/M": "Fechado em 02/2022; área incorporada ao 31º BPM/M; prédio hoje é sede do 15º BAEP.",
}

# Telefone/e-mail dos 22 comandos — o cadastro OPM não tem esses campos (só
# endereço). CPI-1 e CPA/M-2 foram conferidos direto em páginas do próprio site
# policiamilitar.sp.gov.br; o resto veio de agregadores/diretórios de terceiros
# (não oficiais) e não foi verificado na fonte primária — pelo menos 2 números
# encontrados nesses agregadores tinham DDD "01" (inexistente no Brasil) e foram
# descartados por completo em vez de incluídos errados.
COMANDO_CONTATOS = {
    'CPI-1': {'telefone': '(12) 3922-9666', 'email': 'cpi1@policiamilitar.sp.gov.br',
              'fonte_contato': 'Verificado (policiamilitar.sp.gov.br)'},
    'CPI-2': {'telefone': '(19) 3772-6777', 'email': None,
              'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPI-3': {'telefone': '(16) 3969-9998', 'email': None,
              'fonte_contato': 'Não verificado (agregador terceiro; fontes divergem entre ...9998 e ...9999)'},
    'CPI-4': {'telefone': '(14) 3222-3172', 'email': None,
              'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPI-5': {'telefone': '(17) 3231-7771', 'email': None,
              'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPI-6': {'telefone': None, 'email': None, 'fonte_contato': None},
    'CPI-7': {'telefone': '(15) 3229-3943', 'email': None,
              'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPI-8': {'telefone': '(18) 3221-8990', 'email': None,
              'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPI-9': {'telefone': '(19) 3421-4515', 'email': 'cpi9uge@polmil.sp.gov.br',
              'fonte_contato': 'Não verificado (agregador terceiro; outra fonte lista (19) 3413-0550)'},
    'CPI-10': {'telefone': '(18) 2102-5200', 'email': None,
               'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPA/M-1': {'telefone': None, 'email': None, 'fonte_contato': None},
    'CPA/M-2': {'telefone': '(11) 3546-1333', 'email': 'cpam2@policiamilitar.sp.gov.br',
                'fonte_contato': 'Verificado (policiamilitar.sp.gov.br)'},
    'CPA/M-3': {'telefone': '(11) 2287-6306', 'email': 'cpam3uge@policiamilitar.sp.gov.br',
                'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPA/M-4': {'telefone': None, 'email': 'cpam4uge@polmil.sp.gov.br',
                'fonte_contato': 'E-mail não verificado (agregador terceiro); telefone descartado (DDD "01" inválido na fonte)'},
    'CPA/M-5': {'telefone': '(11) 3769-2014', 'email': None,
                'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPA/M-6': {'telefone': '(11) 4436-4991', 'email': None,
                'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPA/M-7': {'telefone': None, 'email': 'cpam7uge@polmil.sp.gov.br',
                'fonte_contato': 'E-mail não verificado (agregador terceiro); telefone descartado (DDD "01" inválido na fonte)'},
    'CPA/M-8': {'telefone': None, 'email': None, 'fonte_contato': None},
    'CPA/M-9': {'telefone': None, 'email': None, 'fonte_contato': None},
    'CPA/M-10': {'telefone': None, 'email': 'cpam10p5@policiamilitar.sp.gov.br',
                 'fonte_contato': 'E-mail não verificado (agregador terceiro)'},
    'CPA/M-11': {'telefone': '(11) 295-3614', 'email': 'cpam11p4@polmil.sp.gov.br',
                 'fonte_contato': 'Não verificado (agregador terceiro)'},
    'CPA/M-12': {'telefone': None, 'email': None, 'fonte_contato': None},
}

# Registros inseridos manualmente para preencher lacunas confirmadas do cadastro OPM
# (não são dados oficiais da PM — cada um documenta a fonte/raciocínio da inferência).
# Seguem o mesmo formato de linha da API (opmcod/cpa/btl/cia/pel/gp/cidade/endereco/
# bairro/opmNome/opmDescricao) para fluir pelos mesmos passos de qualquer outro OPM.
MANUAL_HIERARCHY_ADDITIONS = [
    {
        # Cecap (Guarulhos) não aparece sob nenhum batalhão ativo no cadastro OPM: só
        # existe vinculado ao 44º BPM/M (excluído, extinto) e ao 15º BAEP (unidade
        # tática, fora do escopo territorial). A nota oficial de fechamento do 44º BPM/M
        # (02/2022) diz que a responsabilidade administrativa foi unificada ao 31º
        # BPM/M — não ao 15º BPM/M, cuja placa "15º" no prédio (confirmada pelo usuário
        # via Street View) é do 15º BAEP, não do batalhão metropolitano. Endereço
        # idêntico ao antigo registro do 44º BPM/M.
        'opmcod': 'INFERIDO-CECAP-31BPMM', 'diretoria': 'ORG EXEC', 'cpa': 'CPA/M-7',
        'btl': '31.BPM/M', 'cia': 'CECAP (AJUSTE MANUAL)', 'pel': '', 'gp': '',
        'opmtip': 'O', 'cidade': 'GUARULHOS',
        'endereco': 'AVENIDA ODAIR SANTANELI, 215', 'bairro': 'CECAP', 'cep': '',
        'opmNome': 'ÁREA DO PARQUE CECAP (AJUSTE MANUAL — sem registro OPM oficial; '
                   'responsabilidade unificada ao 31º BPM/M após o fechamento do 44º '
                   'BPM/M em 02/2022, não confirmada unidade a unidade)',
        'opmDescricao': 'CPA/M-7 31.BPM/M CECAP (AJUSTE MANUAL)',
    },
]


def fetch_with_retry(url, method="GET", max_retries=3, delay=2, **kwargs):
    for i in range(max_retries):
        try:
            r = requests.get(url, timeout=60, verify=False, **kwargs) if method == "GET" else requests.post(url, timeout=60, verify=False, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            if i == max_retries - 1:
                raise e
            time.sleep(delay)


def norm(s):
    """Uppercase, accent-stripped, apostrophe-neutral key for name matching."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    s = s.replace("'", " ")
    return re.sub(r'\s+', ' ', s).strip().upper()


def format_comando(cpa_code):
    """'CPI-3' -> ('interior', 3, '3º Comando de Policiamento do Interior')
       'CPA/M-11' -> ('metropolitano', 11, '11º Comando de Policiamento de Área Metropolitana')"""
    if cpa_code.startswith('CPI-'):
        n = int(cpa_code.split('-')[1])
        return 'interior', n, f"{n}º Comando de Policiamento do Interior (CPI-{n})"
    elif cpa_code.startswith('CPA/M-'):
        n = int(cpa_code.split('-')[1])
        return 'metropolitano', n, f"{n}º Comando de Policiamento de Área Metropolitana (CPA/M-{n})"
    return 'outro', 0, cpa_code


def format_batalhao(btl_code):
    """'9.BPM/I' -> '9º BPM/I'"""
    num, tipo = btl_code.split('.')
    return f"{num}º {tipo}"


def addr_query(row):
    return f"{row['endereco']}, {row['bairro']}, {row['cidade'].title()}, São Paulo, Brasil"


def geocode_nominatim(row):
    """Structured geocoding via Nominatim (OpenStreetMap): street/city/state/country
    passed as separate fields (not one free-text blob) so the city is a hard filter,
    not just a hint — a loose free-text query for a street name that also exists in a
    much bigger city (e.g. "Avenida Faria Lima" in Jacareí vs. São Paulo Capital) can
    otherwise match the wrong, more prominent place. Respects the 1 req/sec usage
    policy and identifies the app + contact in the User-Agent, as required."""
    query = addr_query(row)
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={
                'street': f"{row['endereco']}, {row['bairro']}",
                'city': row['cidade'].title(),
                'state': 'São Paulo',
                'country': 'Brasil',
                'format': 'jsonv2', 'limit': 1, 'countrycodes': 'br',
            },
            headers={'User-Agent': NOMINATIM_USER_AGENT},
            timeout=15,
            verify=False,
        )
        r.raise_for_status()
        results = r.json()
        if results:
            return float(results[0]['lat']), float(results[0]['lon'])
    except Exception as e:
        print(f"    geocoding failed for '{query}': {e}")
    finally:
        time.sleep(1.1)
    return None, None


def geocode_google(row, api_key):
    """Google Geocoding API. Uses `components` to hard-filter the match to the
    expected locality (see geocode_nominatim's docstring for why a free-text-only
    query can silently return the wrong city's namesake street/square). Returns
    (lat, lon, error) where error is None on success, or a short reason string (e.g.
    'REQUEST_DENIED' when the API isn't enabled for this key) so the caller can
    decide whether to keep trying."""
    try:
        r = requests.get(
            GOOGLE_GEOCODE_URL,
            params={
                'address': f"{row['endereco']}, {row['bairro']}",
                'components': f"locality:{row['cidade'].title()}|administrative_area:São Paulo|country:BR",
                'key': api_key,
            },
            timeout=15,
            verify=False,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get('status')
        if status == 'OK' and data.get('results'):
            loc = data['results'][0]['geometry']['location']
            return loc['lat'], loc['lng'], None
        if status == 'ZERO_RESULTS':
            return None, None, None
        return None, None, data.get('error_message', status)
    except Exception as e:
        return None, None, str(e)


def geocode_many(query_rows, cache):
    """Geocode a {query_string: representative_row} mapping — Google first, Nominatim
    as fallback — reusing/persisting the shared on-disk cache (keyed by query_string
    for continuity with earlier runs; the actual API calls use each row's structured
    fields). Returns {query: (lat, lon, source)}."""
    results = {}
    google_disabled_reason = None
    n_cached = n_google = n_nominatim = 0
    for query, row in query_rows.items():
        cached = cache.get(query)
        if cached is not None:
            results[query] = (cached['lat'], cached['lon'], cached['source'])
            n_cached += 1
            continue
        lat, lon, source = None, None, None
        if GOOGLE_MAPS_API_KEY and not google_disabled_reason:
            g_lat, g_lon, g_err = geocode_google(row, GOOGLE_MAPS_API_KEY)
            if g_lat is not None:
                lat, lon, source = g_lat, g_lon, 'Google Geocoding API'
                n_google += 1
            elif g_err and g_err not in ('ZERO_RESULTS',):
                google_disabled_reason = g_err
                print(f"  Google Geocoding API indisponível para esta chave ({g_err}) — "
                      f"desativando fallback Google pelo resto desta execução.")
        if lat is None:
            n_lat, n_lon = geocode_nominatim(row)
            if n_lat is not None:
                lat, lon, source = n_lat, n_lon, 'Nominatim (OpenStreetMap)'
                n_nominatim += 1
        if lat is not None:
            cache[query] = {'lat': lat, 'lon': lon, 'source': source}
        results[query] = (lat, lon, source)
    n_ok = sum(1 for v in results.values() if v[0] is not None)
    print(f"  Geocoded {n_ok}/{len(query_rows)} unique addresses "
          f"({n_cached} from cache, {n_google} new via Google, {n_nominatim} new via Nominatim).")
    return results


def fetch_json_validated(url, validate_fn, description, max_retries=5, delay=4, **kwargs):
    """fetch_with_retry only catches network/HTTP-level failures. On this network,
    interception sometimes returns a 200 OK with truncated/empty content instead of
    an error, so we also validate the parsed payload's shape and retry when it
    doesn't look right, rather than letting a bad response propagate silently."""
    last_data = None
    for i in range(max_retries):
        r = fetch_with_retry(url, **kwargs)
        try:
            data = r.json()
            if validate_fn(data):
                return data
            last_data = data
        except Exception as e:
            last_data = e
        print(f"  {description}: unexpected/incomplete response (attempt {i + 1}/{max_retries}), retrying...")
        time.sleep(delay)
    raise RuntimeError(f"{description}: failed to get a valid response after {max_retries} attempts "
                        f"(likely network interception). Last response: {last_data!r:.200}")


def load_geocode_cache():
    if not os.path.exists(GEOCODE_CACHE_PATH):
        return {}
    with open(GEOCODE_CACHE_PATH, encoding='utf-8') as f:
        raw = json.load(f)
    # Migrate the old Nominatim-only cache format ([lat, lon]) to the current
    # {lat, lon, source} shape used now that there's more than one provider.
    cache = {}
    for k, v in raw.items():
        if isinstance(v, list):
            cache[k] = {'lat': v[0], 'lon': v[1], 'source': 'Nominatim (OpenStreetMap)'}
        else:
            cache[k] = v
    return cache


def save_geocode_cache(cache):
    os.makedirs(os.path.dirname(GEOCODE_CACHE_PATH), exist_ok=True)
    with open(GEOCODE_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)


def safe_to_file(gdf, path, max_retries=6, delay=3, **kwargs):
    """Write via a temp file then swap into place, retrying the swap on
    PermissionError (OneDrive/editor/indexer briefly locking the destination
    right after a previous write to the same folder)."""
    tmp_path = path + '.tmp'
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    gdf.to_file(tmp_path, **kwargs)
    for i in range(max_retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if i == max_retries - 1:
                raise
            time.sleep(delay)


def main():
    print("Step 1: Fetching PMESP OPM unit registry...")

    def _validate_opm(d):
        recs = d.get('resultado', {}).get('opmEnderecos', [])
        if len(recs) <= 1000:
            return False
        # A truncated/intercepted response can coincidentally match on record
        # count alone, so also check the real content we depend on downstream.
        n_terr = sum(1 for r in recs if BTL_PATTERN.match(r.get('btl', '')))
        return n_terr > 500

    opm_data = fetch_json_validated(OPM_API, validate_fn=_validate_opm, description="OPM registry")
    opm = opm_data['resultado']['opmEnderecos']
    df_opm = pd.DataFrame(opm)

    print("Step 2: Filtering territorial battalions (BPM/I e BPM/M)...")
    df_terr = df_opm[df_opm['btl'].str.match(BTL_PATTERN, na=False)].copy()
    assert len(df_terr) > 500, (
        f"Only {len(df_terr)} territorial records after filtering (expected ~2550) — "
        "the OPM registry response looks wrong despite passing validation; aborting "
        "instead of producing bad output."
    )
    if KNOWN_DEFUNCT_BATTALIONS:
        n_before = len(df_terr)
        df_terr = df_terr[~df_terr['btl'].isin(KNOWN_DEFUNCT_BATTALIONS)].copy()
        for btl, reason in KNOWN_DEFUNCT_BATTALIONS.items():
            print(f"  Excluding {btl} (confirmed extinct): {reason}")
        print(f"  {n_before - len(df_terr)} records dropped for {len(KNOWN_DEFUNCT_BATTALIONS)} defunct battalion(s).")

    if MANUAL_HIERARCHY_ADDITIONS:
        df_manual = pd.DataFrame(MANUAL_HIERARCHY_ADDITIONS)
        df_terr = pd.concat([df_terr, df_manual], ignore_index=True)
        print(f"  Adding {len(df_manual)} manually-inferred record(s) — not official OPM data, see dicionário.")

    df_terr['cidade_norm'] = df_terr['cidade'].apply(norm)
    df_terr['tipo_batalhao'] = df_terr['btl'].apply(lambda x: 'Interior' if x.endswith('/I') else 'Metropolitano')

    # btl -> comando (1:1, verified no battalion spans multiple commands)
    btl_to_cpa = df_terr.groupby('btl')['cpa'].first().to_dict()

    # Representative-row picker shared by every level of the hierarchy: prefer the
    # unit's own "bare" administrative record (nothing filled in below it), then its
    # Estado-Maior (staff) record, then just the first row seen.
    def pick_bare(g, blank_cols):
        bare = g
        for c in blank_cols:
            bare = bare[bare[c] == '']
        if len(bare):
            return bare.iloc[0]
        if 'cia' in g.columns and 'pel' in g.columns:
            em = g[(g['cia'] == 'EM') & (g['pel'] == '')]
            if len(em):
                return em.iloc[0]
        return g.iloc[0]

    print("Step 2b: Building the full hierarchy (comando/batalhão/companhia/pelotão/grupo)...")
    # Battalion HQ: one representative row per btl.
    # include_groups=False: pandas >=2.2 deprecates (and pandas 3.0 enforces) dropping
    # the grouping column from what's passed to apply(); since apply() here returns a
    # Series (not group_keys=False), the result already comes back indexed by the key.
    df_hq = df_terr.groupby('btl').apply(lambda g: pick_bare(g, ['cia', 'pel', 'gp']), include_groups=False)

    # Comando HQ: the OPM registry has a distinct physical-HQ record for each comando
    # (btl field holding the comando's own code, e.g. btl='CPI-3'), separate from any
    # of its battalions' addresses.
    comando_codes = sorted(set(btl_to_cpa.values()))
    df_comando_src = df_opm[df_opm['btl'].isin(comando_codes)].copy()
    df_comando_hq = df_comando_src.groupby('btl').apply(lambda g: pick_bare(g, ['cia', 'pel', 'gp']), include_groups=False)

    # Companhia: one representative row per (btl, cia).
    df_cia_hq = (df_terr[df_terr['cia'] != '']
                 .groupby(['btl', 'cia']).apply(lambda g: pick_bare(g, ['pel', 'gp']), include_groups=False))

    # Pelotão: one representative row per (btl, cia, pel).
    df_pel_hq = (df_terr[df_terr['pel'] != '']
                 .groupby(['btl', 'cia', 'pel']).apply(lambda g: pick_bare(g, ['gp']), include_groups=False))

    # Grupo/Esquadra: already the leaf level, just dedupe.
    df_grupo_hq = (df_terr[df_terr['gp'] != '']
                   .drop_duplicates(subset=['btl', 'cia', 'pel', 'gp'], keep='first')
                   .set_index(['btl', 'cia', 'pel', 'gp']))

    print(f"  {len(df_comando_hq)} comandos, {len(df_hq)} batalhões, {len(df_cia_hq)} companhias, "
          f"{len(df_pel_hq)} pelotões, {len(df_grupo_hq)} grupos/esquadras.")

    print("Step 2c: Geocoding every unique HQ address across the whole hierarchy "
          "(Google, Nominatim as fallback)...")
    query_rows = {}
    for df in (df_hq, df_comando_hq, df_cia_hq, df_pel_hq, df_grupo_hq):
        for _, row in df.iterrows():
            query_rows.setdefault(addr_query(row), row)
    geocode_cache = load_geocode_cache()
    geo_results = geocode_many(query_rows, geocode_cache)
    save_geocode_cache(geocode_cache)

    print("Step 3: Building município -> batalhão(ões) e hierarquia -> município...")
    # Presence weight per (city, btl): number of OPM sub-units, used to pick the
    # dominant/primary battalion when a município is split among several.
    presence = df_terr.groupby(['cidade_norm', 'btl']).size().reset_index(name='n_unidades')

    def build_city_row(g):
        g = g.sort_values(['n_unidades', 'btl'], ascending=[False, True])
        primary = g.iloc[0]['btl']
        btls = sorted(g['btl'].tolist(), key=lambda b: (btl_to_cpa[b], int(b.split('.')[0])))
        return pd.Series({
            'batalhao_principal': primary,
            'qt_batalhoes': len(btls),
            'batalhoes_lista': ", ".join(format_batalhao(b) for b in btls),
            'batalhoes_codigos': btls,
        })

    city_battalions = presence.groupby('cidade_norm').apply(build_city_row, include_groups=False).reset_index()

    def build_city_hierarchy(g):
        comandos = sorted(set(g['cpa']))
        n_cia = g[g['cia'] != ''][['btl', 'cia']].drop_duplicates().shape[0]
        n_pel = g[g['pel'] != ''][['btl', 'cia', 'pel']].drop_duplicates().shape[0]
        n_grp = g[g['gp'] != ''][['btl', 'cia', 'pel', 'gp']].drop_duplicates().shape[0]
        return pd.Series({
            'qt_comandos': len(comandos),
            'comandos_lista': ", ".join(comandos),
            'qt_companhias': int(n_cia),
            'qt_pelotoes': int(n_pel),
            'qt_grupos': int(n_grp),
        })

    city_hierarchy = df_terr.groupby('cidade_norm').apply(build_city_hierarchy, include_groups=False).reset_index()
    city_battalions = city_battalions.merge(city_hierarchy, on='cidade_norm', how='left')
    HIERARCHY_FILL_COLS = ['batalhao_principal', 'qt_batalhoes', 'batalhoes_lista',
                            'qt_comandos', 'comandos_lista', 'qt_companhias', 'qt_pelotoes', 'qt_grupos']

    print("Step 4: Loading IBGE municipality list and matching names...")
    ibge_list_data = fetch_json_validated(
        IBGE_MUN_LIST_URL, validate_fn=lambda d: isinstance(d, list) and len(d) > 500,
        description="IBGE municipality list",
    )
    df_ibge_list = pd.DataFrame(ibge_list_data)
    df_ibge_list['nome_norm_raw'] = df_ibge_list['nome'].apply(norm)

    city_battalions['nome_norm_fixed'] = city_battalions['cidade_norm'].apply(lambda c: norm(MANUAL_NAME_FIX.get(c, c)))
    df_mun_match = df_ibge_list.merge(city_battalions, left_on='nome_norm_raw', right_on='nome_norm_fixed', how='left')

    matched = df_mun_match['batalhao_principal'].notna().sum()
    print(f"  Matched {matched}/{len(df_mun_match)} municípios directly from OPM registry.")

    print("Step 5: Fetching IBGE geometries and 2022 population...")
    pop_dict = {}
    pop_data = fetch_json_validated(
        IBGE_POP_URL,
        validate_fn=lambda d: len(d[0]['resultados'][0]['series']) > 500,
        description="IBGE population",
    )
    for s in pop_data[0]['resultados'][0]['series']:
        if str(s['localidade']['id']).startswith('35'):
            pop_dict[int(s['localidade']['id'])] = int(s['serie']['2022']) if s['serie']['2022'] and s['serie']['2022'] != "..." else 0

    geo_data = fetch_json_validated(
        IBGE_GEO_URL, validate_fn=lambda d: len(d.get('features', [])) > 500,
        description="IBGE municipality geometries",
    )
    gdf_mun = gpd.GeoDataFrame.from_features(geo_data['features'])
    gdf_mun['id_municipio_ibge'] = gdf_mun['codarea'].astype(int)
    gdf_mun['populacao_municipio'] = gdf_mun['id_municipio_ibge'].map(pop_dict).fillna(0).astype(int)
    gdf_mun = gdf_mun.set_crs(epsg=4674, allow_override=True).to_crs(epsg=4326)
    gdf_mun['centroid'] = gdf_mun.geometry.centroid

    gdf_state = gdf_mun.merge(df_mun_match, left_on='id_municipio_ibge', right_on='id', how='left')

    print("Step 6: Resolving municípios with no direct OPM record via nearest battalion...")
    unmatched_mask = gdf_state['batalhao_principal'].isna()
    n_unmatched = unmatched_mask.sum()
    print(f"  {n_unmatched} municípios without a direct PM post; assigning via nearest matched neighbor.")

    gdf_known = gdf_state[~unmatched_mask].copy()
    gdf_unknown = gdf_state[unmatched_mask].copy()
    if len(gdf_unknown):
        gdf_known_pts = gdf_known.copy()
        gdf_known_pts['geometry'] = gdf_known_pts['centroid']
        gdf_unknown_pts = gdf_unknown.copy()
        gdf_unknown_pts['geometry'] = gdf_unknown_pts['centroid']
        nearest = gpd.sjoin_nearest(
            gdf_unknown_pts[['id_municipio_ibge', 'geometry']],
            gdf_known_pts[['id_municipio_ibge', 'geometry'] + HIERARCHY_FILL_COLS],
            how='left', distance_col='dist'
        )
        nearest = nearest.drop_duplicates(subset='id_municipio_ibge_left')
        fill_map = nearest.set_index('id_municipio_ibge_left')[HIERARCHY_FILL_COLS]
        for col in HIERARCHY_FILL_COLS:
            gdf_state.loc[unmatched_mask, col] = gdf_state.loc[unmatched_mask, 'id_municipio_ibge'].map(fill_map[col])

    gdf_state['fonte_atribuicao'] = np.where(unmatched_mask.values, 'Atribuição por proximidade (sem posto PM próprio)', 'Registro direto PMESP')

    print("Step 7: Attaching battalion/comando metadata to município layer...")
    gdf_state['nome_comando'] = gdf_state['batalhao_principal'].map(lambda b: format_comando(btl_to_cpa[b])[2])
    gdf_state['id_comando'] = gdf_state['batalhao_principal'].map(btl_to_cpa)
    gdf_state['tipo_comando'] = gdf_state['batalhao_principal'].map(lambda b: format_comando(btl_to_cpa[b])[0])
    gdf_state['nome_batalhao_principal'] = gdf_state['batalhao_principal'].map(format_batalhao)
    gdf_state['endereco_sede_batalhao'] = gdf_state['batalhao_principal'].map(
        lambda b: f"{df_hq.loc[b, 'endereco']}, {df_hq.loc[b, 'bairro']} - {df_hq.loc[b, 'cidade'].title()}"
    )
    gdf_state = gdf_state.rename(columns={'nome': 'nome_municipio'})

    # City centroid fallback for any HQ address that neither Google nor Nominatim found.
    gdf_state_uniq = gdf_state.drop_duplicates(subset='nome_municipio')
    city_centroid_lookup = gdf_state_uniq.set_index(gdf_state_uniq['nome_municipio'].apply(norm))['centroid']
    # ~0.03° (~3km at this latitude) of slack for rooftop/edge imprecision — small next
    # to the scale of a wrong-city geocode (tens to hundreds of km), the actual failure
    # mode we're guarding against (a street/square name that also exists in a much
    # bigger, more prominent city matches that instead — e.g. "Avenida Faria Lima" in
    # Jacareí resolving to the famous one in São Paulo Capital).
    city_geom_lookup = gdf_state_uniq.set_index(gdf_state_uniq['nome_municipio'].apply(norm))['geometry'].buffer(0.03)

    print("Step 7b: Validating geocoded points fall inside their expected município...")
    n_rejected = 0
    rejected_queries = set()
    for query, row in query_rows.items():
        lat, lon, source = geo_results.get(query, (None, None, None))
        if lat is None or source == 'Centroide do município-sede (endereço não geocodificado)':
            continue
        poly = city_geom_lookup.get(norm(row['cidade']))
        if poly is not None and poly.contains(Point(lon, lat)):
            continue
        # Rejected: try a fresh, city-constrained Nominatim lookup as a second opinion
        # before giving up (skip if that's exactly what already failed).
        retry_lat, retry_lon = (None, None)
        if source != 'Nominatim (OpenStreetMap)':
            retry_lat, retry_lon = geocode_nominatim(row)
        if retry_lat is not None and poly is not None and poly.contains(Point(retry_lon, retry_lat)):
            geo_results[query] = (retry_lat, retry_lon, 'Nominatim (OpenStreetMap)')
            geocode_cache[query] = {'lat': retry_lat, 'lon': retry_lon, 'source': 'Nominatim (OpenStreetMap)'}
            print(f"    rejected {source} result for '{query}' (outside {row['cidade'].title()}); "
                  f"Nominatim retry landed inside the município, using it.")
        else:
            geo_results[query] = (None, None, None)
            geocode_cache.pop(query, None)
            rejected_queries.add(query)
            print(f"    rejected {source} result for '{query}' (outside {row['cidade'].title()}); "
                  f"no valid alternative found, will fall back to município centroid.")
        n_rejected += 1
    if n_rejected:
        save_geocode_cache(geocode_cache)
    print(f"  {n_rejected} geocoded point(s) rejected for falling outside their município.")

    def resolve_coords(cidade, query):
        lat, lon, source = geo_results.get(query, (None, None, None))
        if lat is not None:
            return lat, lon, source
        c = city_centroid_lookup.get(norm(cidade))
        if c is None:
            return None, None, None
        if query in rejected_queries:
            return c.y, c.x, 'Centroide do município-sede (geocodificação rejeitada: fora dos limites do município)'
        return c.y, c.x, 'Centroide do município-sede (endereço não geocodificado)'

    def sede_coords(b):
        row = df_hq.loc[b]
        return resolve_coords(row['cidade'], addr_query(row))

    sede_lookup = {b: sede_coords(b) for b in df_hq.index}
    gdf_state['latitude_sede_batalhao'] = gdf_state['batalhao_principal'].map(lambda b: sede_lookup[b][0])
    gdf_state['longitude_sede_batalhao'] = gdf_state['batalhao_principal'].map(lambda b: sede_lookup[b][1])
    gdf_state['fonte_geocodificacao_sede'] = gdf_state['batalhao_principal'].map(lambda b: sede_lookup[b][2])

    clean_cols_mun = [
        'id_municipio_ibge', 'nome_municipio', 'populacao_municipio',
        'id_comando', 'nome_comando', 'tipo_comando',
        'nome_batalhao_principal', 'qt_batalhoes', 'batalhoes_lista',
        'endereco_sede_batalhao', 'latitude_sede_batalhao', 'longitude_sede_batalhao',
        'fonte_geocodificacao_sede',
        'qt_comandos', 'comandos_lista', 'qt_companhias', 'qt_pelotoes', 'qt_grupos',
        'fonte_atribuicao'
    ]

    def finalize(gdf, cols):
        out = gdf.copy()
        for c in cols:
            if c not in out.columns:
                out[c] = None
        out['geometry'] = [MultiPolygon([g]) if isinstance(g, Polygon) else g for g in out.geometry]
        return out[cols + ['geometry']]

    print("Step 8: Fetching GeoSampa official battalion/comando polygons (Capital/Grande SP)...")
    def fetch_geosampa_layer(typename):
        params = {
            'service': 'wfs', 'version': '2.0.0', 'request': 'GetFeature',
            'typeName': typename, 'outputFormat': 'application/json', 'srsName': 'EPSG:4326'
        }
        data = fetch_json_validated(
            GEOSAMPA_WFS, validate_fn=lambda d: len(d.get('features', [])) > 10,
            description=f"GeoSampa {typename}", params=params,
        )
        return gpd.GeoDataFrame.from_features(data['features'], crs='EPSG:4326')

    gdf_geosampa_btl = fetch_geosampa_layer('geoportal:batalhao_policia_militar')
    gdf_geosampa_btl['btl_num'] = gdf_geosampa_btl['nm_batalhao_policia_militar'].apply(lambda s: re.match(r'\s*(\d+)', s).group(1))
    gdf_geosampa_btl['btl_code'] = gdf_geosampa_btl['btl_num'] + '.BPM/M'
    # A battalion polygon can be split into disjoint parts in the source layer; dissolve to one feature.
    gdf_geosampa_btl = gdf_geosampa_btl.dissolve(by='btl_code').reset_index()

    print("Step 9: Building camada 2 (batalhões) - real polygon where available, dissolved municípios otherwise...")
    all_btls = sorted(btl_to_cpa.keys(), key=lambda b: (btl_to_cpa[b], int(b.split('.')[0])))
    geosampa_btl_codes = set(gdf_geosampa_btl['btl_code'])

    dissolved = gdf_state.dissolve(by='batalhao_principal', aggfunc={
        'populacao_municipio': 'sum',
        'nome_municipio': lambda x: ", ".join(sorted(x)),
        'id_municipio_ibge': 'count',
    }).reset_index().rename(columns={
        'nome_municipio': 'municipios_atendidos',
        'id_municipio_ibge': 'qt_municipios',
        'populacao_municipio': 'populacao_atendida',
    })
    dissolved_map = dissolved.set_index('batalhao_principal')

    # Fallback for battalions that are never the *primary* battalion of any município
    # (they only share territory with another battalion in the same city, e.g. two
    # BPM/M in São Bernardo do Campo) and have no official GeoSampa polygon either:
    # dissolve every município where they have ANY presence, so they still get a
    # (shared/overlapping) boundary instead of being dropped.
    presence_exploded = gdf_state[['batalhoes_codigos', 'populacao_municipio', 'nome_municipio', 'id_municipio_ibge', 'geometry']].explode('batalhoes_codigos')
    dissolved_presence = presence_exploded.dissolve(by='batalhoes_codigos', aggfunc={
        'populacao_municipio': 'sum',
        'nome_municipio': lambda x: ", ".join(sorted(x)),
        'id_municipio_ibge': 'count',
    }).reset_index().rename(columns={
        'nome_municipio': 'municipios_atendidos',
        'id_municipio_ibge': 'qt_municipios',
        'populacao_municipio': 'populacao_atendida',
    })
    dissolved_presence_map = dissolved_presence.set_index('batalhoes_codigos')

    rows = []
    for btl in all_btls:
        tipo, n, nome_comando = format_comando(btl_to_cpa[btl])
        hq = df_hq.loc[btl]
        sede_lat, sede_lon, sede_fonte = sede_lookup[btl]
        base = {
            'nome_batalhao': format_batalhao(btl),
            'tipo_batalhao': 'Interior' if btl.endswith('/I') else 'Metropolitano',
            'id_comando': btl_to_cpa[btl],
            'nome_comando': nome_comando,
            'cidade_sede': hq['cidade'].title(),
            'endereco_sede': f"{hq['endereco']}, {hq['bairro']} - {hq['cidade'].title()}",
            'latitude_sede': sede_lat,
            'longitude_sede': sede_lon,
            'fonte_geocodificacao_sede': sede_fonte,
        }
        if btl in geosampa_btl_codes:
            geom = gdf_geosampa_btl.loc[gdf_geosampa_btl['btl_code'] == btl, 'geometry'].iloc[0]
            base['fonte_geometria'] = 'Limite oficial GeoSampa (sub-municipal)'
            base['qt_municipios'] = None
            base['municipios_atendidos'] = None
            base['populacao_atendida'] = None
            base['geometry'] = geom
            rows.append(base)
        elif btl in dissolved_map.index:
            d = dissolved_map.loc[btl]
            base['fonte_geometria'] = 'Dissolução da malha municipal IBGE (batalhão principal)'
            base['qt_municipios'] = int(d['qt_municipios'])
            base['municipios_atendidos'] = d['municipios_atendidos']
            base['populacao_atendida'] = int(d['populacao_atendida'])
            base['geometry'] = d['geometry']
            rows.append(base)
        elif btl in dissolved_presence_map.index:
            d = dissolved_presence_map.loc[btl]
            base['fonte_geometria'] = 'Dissolução da malha municipal IBGE (área compartilhada com outro batalhão no(s) mesmo(s) município(s))'
            base['qt_municipios'] = int(d['qt_municipios'])
            base['municipios_atendidos'] = d['municipios_atendidos']
            base['populacao_atendida'] = int(d['populacao_atendida'])
            base['geometry'] = d['geometry']
            rows.append(base)
        else:
            print(f"  WARNING: no geometry source for {btl}, skipping.")

    gdf_batalhoes = gpd.GeoDataFrame(rows, crs='EPSG:4326')
    gdf_batalhoes['geometry'] = [MultiPolygon([g]) if isinstance(g, Polygon) else g for g in gdf_batalhoes.geometry]

    print("Step 10: Building hierarchy point layers (comando/companhia/pelotão/grupo)...")
    n_batalhoes_by_cpa = Counter(btl_to_cpa.values())

    # Not every comando has its own administrative-HQ record in the OPM registry
    # (only 5 of 12 CPA/M do; all 10 CPI do). For the rest, approximate the comando's
    # location with its lowest-numbered battalion's HQ — in practice a comando often
    # shares a building with one of its battalions (confirmed for CPA/M-7, whose HQ is
    # in the same building as 15º BPM/M).
    comando_pts = []
    for cpa_code in comando_codes:
        tipo, n, nome_comando = format_comando(cpa_code)
        if cpa_code in df_comando_hq.index:
            row = df_comando_hq.loc[cpa_code]
            lat, lon, fonte = resolve_coords(row['cidade'], addr_query(row))
            opm_nome, opm_codigo = row['opmNome'], row['opmcod']
        else:
            proxy_btl = min((b for b, c in btl_to_cpa.items() if c == cpa_code), key=lambda b: int(b.split('.')[0]))
            row = df_hq.loc[proxy_btl]
            lat, lon, base_fonte = resolve_coords(row['cidade'], addr_query(row))
            fonte = (f"Aproximado: sem sede administrativa própria no cadastro OPM; "
                     f"usada a sede do {format_batalhao(proxy_btl)} ({base_fonte})")
            opm_nome, opm_codigo = row['opmNome'], row['opmcod']
        contato = COMANDO_CONTATOS.get(cpa_code, {})
        comando_pts.append({
            'id_comando': cpa_code,
            'nome_comando': nome_comando,
            'tipo_comando': tipo,
            'qt_batalhoes': int(n_batalhoes_by_cpa.get(cpa_code, 0)),
            'cidade_sede': row['cidade'].title(),
            'endereco_sede': f"{row['endereco']}, {row['bairro']} - {row['cidade'].title()}",
            'latitude': lat, 'longitude': lon, 'fonte_geocodificacao': fonte,
            'telefone': contato.get('telefone'), 'email': contato.get('email'),
            'fonte_contato': contato.get('fonte_contato'),
            'opm_nome': opm_nome, 'opm_codigo': opm_codigo,
            'geometry': Point(lon, lat) if lat is not None else None,
        })
    gdf_comandos_pts = gpd.GeoDataFrame([p for p in comando_pts if p['geometry'] is not None], crs='EPSG:4326')

    def build_level_points(df_level, extra_cols):
        pts = []
        for key, row in df_level.iterrows():
            btl = key[0] if isinstance(key, tuple) else key
            lat, lon, fonte = resolve_coords(row['cidade'], addr_query(row))
            rec = {
                'id_comando': btl_to_cpa[btl],
                'nome_comando': format_comando(btl_to_cpa[btl])[2],
                'nome_batalhao': format_batalhao(btl),
                'tipo_batalhao': 'Interior' if btl.endswith('/I') else 'Metropolitano',
            }
            for col in extra_cols:
                rec[col] = key[extra_cols.index(col) + 1] if isinstance(key, tuple) else row[col]
            rec['cidade'] = row['cidade'].title()
            rec['endereco'] = f"{row['endereco']}, {row['bairro']} - {row['cidade'].title()}"
            rec['latitude'] = lat
            rec['longitude'] = lon
            rec['fonte_geocodificacao'] = fonte
            rec['opm_nome'] = row['opmNome']
            rec['opm_descricao'] = row['opmDescricao']
            rec['opm_codigo'] = row['opmcod']
            rec['geometry'] = Point(lon, lat) if lat is not None else None
            pts.append(rec)
        return gpd.GeoDataFrame([p for p in pts if p['geometry'] is not None], crs='EPSG:4326')

    gdf_cias_pts = build_level_points(df_cia_hq, ['companhia'])
    gdf_pels_pts = build_level_points(df_pel_hq, ['companhia', 'pelotao'])
    gdf_grupos_pts = build_level_points(df_grupo_hq, ['companhia', 'pelotao', 'grupo'])

    print(f"  {len(gdf_comandos_pts)} comandos, {len(gdf_cias_pts)} companhias, "
          f"{len(gdf_pels_pts)} pelotões, {len(gdf_grupos_pts)} grupos/esquadras geocodificados com sucesso.")

    print("Step 11: Exporting outputs...")
    safe_to_file(finalize(gdf_state, clean_cols_mun), os.path.join(OUTPUT_DIR, "pm_municipios_sp.geojson"), driver='GeoJSON', encoding='utf-8')

    btl_cols = ['nome_batalhao', 'tipo_batalhao', 'id_comando', 'nome_comando', 'cidade_sede',
                'endereco_sede', 'latitude_sede', 'longitude_sede', 'fonte_geocodificacao_sede',
                'fonte_geometria', 'qt_municipios', 'municipios_atendidos', 'populacao_atendida']
    safe_to_file(gdf_batalhoes[btl_cols + ['geometry']], os.path.join(OUTPUT_DIR, "pm_batalhoes_sp.geojson"), driver='GeoJSON', encoding='utf-8')

    # Points layer: one point per battalion HQ, geocoded from its street address
    # (falls back to the município-sede centroid when nothing resolves the address).
    pts = []
    for btl in all_btls:
        lat, lon, fonte = sede_lookup[btl]
        if lat is None:
            continue
        hq = df_hq.loc[btl]
        pts.append({
            'nome_batalhao': format_batalhao(btl),
            'tipo_batalhao': 'Interior' if btl.endswith('/I') else 'Metropolitano',
            'id_comando': btl_to_cpa[btl],
            'nome_comando': format_comando(btl_to_cpa[btl])[2],
            'cidade_sede': hq['cidade'].title(),
            'endereco_sede': f"{hq['endereco']}, {hq['bairro']} - {hq['cidade'].title()}",
            'latitude_sede': lat,
            'longitude_sede': lon,
            'fonte_geocodificacao_sede': fonte,
            'fonte_geometria': None,
            'qt_municipios': None,
            'municipios_atendidos': None,
            'populacao_atendida': None,
            'geometry': Point(lon, lat),
        })
    gdf_pts_final = gpd.GeoDataFrame(pts, crs='EPSG:4326')
    safe_to_file(gdf_pts_final[btl_cols + ['geometry']], os.path.join(OUTPUT_DIR, "pm_batalhoes_sedes_pontos_sp.geojson"), driver='GeoJSON', encoding='utf-8')

    comando_cols = ['id_comando', 'nome_comando', 'tipo_comando', 'qt_batalhoes', 'cidade_sede',
                     'endereco_sede', 'latitude', 'longitude', 'fonte_geocodificacao',
                     'telefone', 'email', 'fonte_contato', 'opm_nome', 'opm_codigo']
    safe_to_file(gdf_comandos_pts[comando_cols + ['geometry']], os.path.join(OUTPUT_DIR, "pm_comandos_pontos_sp.geojson"), driver='GeoJSON', encoding='utf-8')

    level_cols_base = ['id_comando', 'nome_comando', 'nome_batalhao', 'tipo_batalhao']
    level_cols_tail = ['cidade', 'endereco', 'latitude', 'longitude', 'fonte_geocodificacao',
                        'opm_nome', 'opm_descricao', 'opm_codigo']
    safe_to_file(gdf_cias_pts[level_cols_base + ['companhia'] + level_cols_tail + ['geometry']],
                 os.path.join(OUTPUT_DIR, "pm_companhias_pontos_sp.geojson"), driver='GeoJSON', encoding='utf-8')
    safe_to_file(gdf_pels_pts[level_cols_base + ['companhia', 'pelotao'] + level_cols_tail + ['geometry']],
                 os.path.join(OUTPUT_DIR, "pm_pelotoes_pontos_sp.geojson"), driver='GeoJSON', encoding='utf-8')
    safe_to_file(gdf_grupos_pts[level_cols_base + ['companhia', 'pelotao', 'grupo'] + level_cols_tail + ['geometry']],
                 os.path.join(OUTPUT_DIR, "pm_grupos_pontos_sp.geojson"), driver='GeoJSON', encoding='utf-8')

    print(f"\nSuccess! {len(gdf_state)} municípios, {len(gdf_batalhoes)} batalhões, "
          f"{len(gdf_comandos_pts)} comandos, {len(gdf_cias_pts)} companhias, "
          f"{len(gdf_pels_pts)} pelotões, {len(gdf_grupos_pts)} grupos/esquadras exportados.")


if __name__ == "__main__":
    main()
