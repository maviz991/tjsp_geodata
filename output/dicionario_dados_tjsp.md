# Dicionário de Dados e Metadados: Mapeamento Judiciário TJSP (BI)

Este documento descreve a estrutura da camada final gerada pelo pipeline de dados (`process_juridico_data.py`), disponível nos formatos `GeoJSON` e `CSV`. A camada consolida a divisão administrativa do Tribunal de Justiça de São Paulo (TJSP) com a malha territorial e dados populacionais do IBGE.

## Estrutura da Tabela (Atributos)

| Coluna | Tipo (PostGIS) | Descrição | Origem |
| :--- | :--- | :--- | :--- |
| `id_municipio_ibge` | INTEGER | Código IBGE do Município (7 dígitos) que representa o território físico. | IBGE (Malhas) |
| `nome_municipio` | VARCHAR | Nome oficial do Município territorial. | TJSP (Divisão Admin) |
| `populacao_municipio` | INTEGER | População residente do Município (Censo IBGE 2022). | API IBGE (Agregados) |
| `id_foro` | INTEGER | Código IBGE do Município que é a **Sede da Comarca** (Foro) à qual este município pertence. | TJSP / Relacionamento |
| `nome_foro` | VARCHAR | Nome oficial da Comarca / Foro. | TJSP |
| `total_varas_foro` | INTEGER | Contagem total de varas judiciais, juizados e ofícios disponíveis em toda a Comarca. Calculado com base na lista real de varas. | TJSP (Setores) |
| `entrancia` | VARCHAR | Nível de jurisdição da Comarca (ex: Inicial, Intermediária, Final). | TJSP (Unidades) |
| `endereco_sede` | VARCHAR | Endereço físico e CEP do Fórum principal (Sede) da Comarca. | TJSP (Unidades) |
| `latitude` | DOUBLE | Latitude do centroide do município Sede da Comarca (para plotagem de pontos). | IBGE (Centroide) |
| `longitude` | DOUBLE | Longitude do centroide do município Sede da Comarca (para plotagem de pontos). | IBGE (Centroide) |
| `id_cj` | INTEGER | Código numérico da Circunscrição Judiciária (CJ). | TJSP |
| `nome_cj` | VARCHAR | Nome formatado da Circunscrição Judiciária com ordinal (ex: "14ª Barretos"). | Tratamento TJSP |
| `id_raj` | INTEGER | Código numérico da Região Administrativa Judiciária (RAJ). | TJSP |
| `nome_raj` | VARCHAR | Nome formatado da Região Administrativa Judiciária (ex: "8ª São José do Rio Preto"). | Tratamento TJSP |
| `populacao_foro` | INTEGER | Soma populacional (Censo 2022) de todos os municípios que compõem a Comarca. | Agregação Geométrica |
| `qt_cidades_foro` | INTEGER | Quantidade de municípios atendidos por aquela Comarca. | Agregação Relacional |
| `cidades_no_foro` | TEXT | Lista separada por vírgula dos municípios que fazem parte da Comarca. | Agregação Relacional |
| `qt_cidades_cj` | INTEGER | Quantidade de municípios que compõem toda a Circunscrição Judiciária. | Agregação Relacional |
| `cidades_na_cj` | TEXT | Lista separada por vírgula dos municípios pertencentes à CJ. | Agregação Relacional |
| `unidades` | TEXT | Nomes dos edifícios/fóruns físicos do TJSP localizados fisicamente neste município específico. Vazio se não houver prédio físico. | TJSP (Unidades) |
| `total_varas_municipio` | INTEGER | Quantidade total de varas judiciais instaladas fisicamente no território deste município. | TJSP (Setores) |
| `varas_municipio` | TEXT | Lista ordenada das varas/juizados fisicamente instalados neste município. | TJSP (Setores) |
| `varas_foro` | TEXT | Lista ordenada de todas as varas/juizados disponíveis em toda a Comarca (soma das varas da sede e anexos). | TJSP (Setores) |
| `geometry` | MULTIPOLYGON | (Apenas GeoJSON/PostGIS) Geometria poligonal do território municipal. Todas as feições são convertidas para MultiPolygon para garantir compatibilidade com SGBDs espaciais. | IBGE |

## Considerações Analíticas
* **Municípios Sem Prédio (Anexos):** Municípios que pertencem a uma Comarca maior terão `total_varas_municipio = 0` e `varas_municipio` vazio, mas exibirão corretamente os dados da Comarca nos campos `_foro`.
* **Deduplicação de Varas:** As listas em `varas_municipio` e `varas_foro` excluem estruturas estritamente administrativas (Copa, Seção de Distribuição, etc.) baseando-se em filtros textuais específicos ("VARA", "JUIZADO", "OFÍCIO").
* **Uso no QGIS/PostGIS:** Recomenda-se utilizar o campo `id_municipio_ibge` como chave primária nas ingestões do banco de dados (ETL).

## Arquivos Gerados
1. `tjsp_municipios_sp.geojson`: Polígonos de todos os municípios paulistas com o metadado judicial atrelado.
2. `tjsp_municipios_pontos_sp.geojson`: Centroides de todos os municípios (formato de pontos).
3. `tjsp_mapeamento_bi.csv`: Tabela alfanumérica leve e ideal para ser conectada a ferramentas como PowerBI, Tableau ou Metabase (sem a coluna geometry).
