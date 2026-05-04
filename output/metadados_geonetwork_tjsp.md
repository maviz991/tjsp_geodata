# Metadados para Catálogo GeoNetwork: Mapeamento Judiciário TJSP

## 1. Resumo (Abstract)
Este conjunto de dados geoespaciais apresenta a malha municipal do Estado de São Paulo enriquecida com a estrutura administrativa e judiciária do Tribunal de Justiça de São Paulo (TJSP). A camada integra dados de divisões territoriais (Municípios) com suas respectivas Comarcas (Foros), Circunscrições Judiciárias (CJ) e Regiões Administrativas Judiciárias (RAJ). 

O diferencial desta base é a granularidade da informação judicial, contendo o endereço das sedes, a entrância da comarca, a população atendida por foro e, principalmente, a listagem detalhada de todas as Varas, Juizados e Ofícios Judiciais instalados em cada território. Os dados foram normalizados para garantir que municípios sem fórum próprio exibam corretamente os dados da comarca à qual estão vinculados, facilitando análises de densidade judiciária e planejamento logístico.

## 2. Linhagem (Lineage)
O processo de criação desta camada envolveu a integração de múltiplas fontes de dados via pipeline automatizado (Python):

1. **Extração de Dados Judiciais:** Download das tabelas oficiais de "Unidades", "Municípios e Comarcas" e "Setores" do repositório de dados abertos do TJSP (GitHub/open-geodata).
2. **Filtragem e Limpeza:** Os setores foram filtrados por expressões regulares para identificar apenas unidades judiciárias ativas (Vara, Juizado, Ofício), descartando setores administrativos para evitar inflação nas contagens.
3. **Normalização Geográfica:** Mapeamento dos nomes dos municípios do TJSP para os códigos oficiais do IBGE (7 dígitos).
4. **Enriquecimento Geoespacial:** Consumo da API de Malhas do IBGE para obtenção das geometrias (convertidas para MultiPolygon para compatibilidade com PostGIS) e da API de Agregados para dados populacionais do Censo 2022.
5. **Cálculo de Métricas:** Agregação de população por Foro e cálculo dinâmico do número de varas por município e por foro baseado na lista de setores.
6. **Herança Administrativa:** Implementação de lógica de herança onde municípios "satélites" herdam os metadados de RAJ e CJ da sua cidade sede, corrigindo inconsistências da base de origem.

## 3. Propósito
Subsidiar sistemas de Business Intelligence (BI) e dashboards de gestão territorial, permitindo a visualização da capacidade instalada do judiciário em relação à demanda populacional e extensão territorial do Estado de São Paulo.

## 4. Qualidade de Dados
* **Consistência Topológica:** Geometrias validadas e promovidas a MultiPolygon para garantir compatibilidade com SGBDs espaciais.
* **Precisão Temporal:** Referência de 2022 para população e dados judiciais atualizados conforme o repositório oficial do TJSP na data de processamento.
* **Completude:** Abrange todos os 645 municípios do Estado de São Paulo sem omissões de vínculo administrativo.

---
**Data de Criação:** 2026-05-04
**Responsável pelo Processamento:** Pipeline Automatizado GeoJudicial-SP
**Sistema de Referência:** SIRGAS 2000 (EPSG:4674) / WGS 84 (EPSG:4326) conforme origem IBGE.
