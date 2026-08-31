# Metadados para Catálogo GeoNetwork: Mapeamento Territorial PMESP

## 1. Resumo (Abstract)
Este conjunto de dados geoespaciais apresenta a estrutura territorial operacional da Polícia Militar do Estado de São Paulo (PMESP), Comandos de Policiamento do Interior (CPI) e de Área Metropolitana (CPA/M), seus Batalhões (BPM/I e BPM/M) e a hierarquia completa até Companhia, Pelotão e Grupo/Esquadra, integrada à malha municipal do Estado de São Paulo (IBGE).

O diferencial desta base é cobrir os cinco níveis da cadeia de comando (Comando → Batalhão → Companhia → Pelotão → Grupo/Esquadra) como camadas de pontos georreferenciados independentes, além de duas camadas de polígono: uma por município (com o batalhão responsável e contagens agregadas de toda a hierarquia) e uma por batalhão (usando limite oficial sub-municipal do GeoSampa onde disponível, já que na Capital e Grande São Paulo um único município é dividido entre dezenas de batalhões metropolitanos).

## 2. Linhagem (Lineage)
O processo de criação desta camada envolveu a integração de múltiplas fontes de dados via pipeline automatizado (Python, `process_pm_data.py`):

1. **Extração do Cadastro Policial:** Consumo da API oficial `Pmesp.Unidades.Policiais.Api` (`servicesapp.policiamilitar.sp.gov.br`), que expõe endereço, cidade e hierarquia (Comando/Batalhão/Companhia/Pelotão/Grupo) de cada Organização Policial Militar (OPM) ativa.
2. **Filtragem Territorial:** Seleção apenas dos batalhões territoriais (BPM/I e BPM/M), excluindo unidades especializadas não-territoriais (Choque, Rodoviário, Trânsito, Ambiental, Aviação, Corpo de Bombeiros, BAEP etc.).
3. **Correção de Cadastro:** Exclusão de batalhões confirmados como extintos por fontes independentes mas ainda presentes no cadastro oficial (ex.: 44º BPM/M, fechado em 02/2022), e inserção de registros manuais documentados para preencher lacunas territoriais confirmadas resultantes dessas exclusões (ex.: área do Parque Cecap, Guarulhos).
4. **Construção da Hierarquia:** Agregação dos registros OPM em cinco níveis (comando, batalhão, companhia, pelotão, grupo/esquadra), com seleção de um registro representativo de endereço por unidade.
5. **Geocodificação Estruturada:** Geocodificação de cada endereço físico único da hierarquia via Google Geocoding API (consulta estruturada por localidade) com Nominatim/OpenStreetMap como fallback, evitando busca por texto livre.
6. **Validação Geográfica:** Conferência de cada ponto geocodificado contra o polígono do próprio município (malha do IBGE); pontos fora do município são descartados e reprocessados, com fallback final para o centroide municipal.
7. **Enriquecimento Geoespacial:** Consumo da API de Malhas do IBGE para as geometrias municipais (convertidas para MultiPolygon) e da API de Agregados para dados populacionais do Censo 2022.
8. **Limites Oficiais Sub-municipais:** Sobreposição dos limites reais de batalhões metropolitanos publicados pelo GeoSampa (Prefeitura de São Paulo) onde disponíveis, com dissolução da malha municipal do IBGE como alternativa para os demais.
9. **Atribuição por Proximidade:** Municípios sem posto policial próprio no cadastro oficial são atribuídos ao batalhão do município vizinho mais próximo já mapeado.

## 3. Propósito
Subsidiar sistemas de Business Intelligence (BI), planejamento operacional e dashboards de gestão territorial, permitindo a visualização da divisão de responsabilidade policial em relação à demanda populacional e à extensão territorial do Estado de São Paulo, em qualquer nível da cadeia de comando.

## 4. Qualidade de Dados
* **Consistência Topológica:** Geometrias poligonais validadas e promovidas a MultiPolygon para garantir compatibilidade com SGBDs espaciais; pontos validados geograficamente contra o município esperado.
* **Precisão Temporal:** Referência de 2022 para população (Censo IBGE); cadastro de unidades policiais e limites GeoSampa conforme disponíveis na data de processamento.
* **Completude:** Abrange todos os 645 municípios do Estado de São Paulo e 98 batalhões territoriais ativos (55 BPM/I + 43 BPM/M), organizados sob 22 comandos (10 CPI + 12 CPA/M), com 650 companhias, 1.433 pelotões e 1.060 grupos/esquadras geocodificados.
* **Transparência de Correções:** Toda exclusão de unidade extinta e toda inserção manual de dado inferido é documentada com fonte e sinalizada em campo próprio (`dicionario_dados_pm.md`), nunca misturada silenciosamente ao dado oficial.
* **Confiabilidade Desigual em Contatos:** Telefone/e-mail de comando (camada de pontos de comando) não constam do cadastro oficial; apenas 2 dos 22 foram verificados em fonte primária, os demais vêm de agregadores de terceiros não verificados, usar sempre com o campo `fonte_contato`.

---
**Data de Criação:** 2026-08-28
**Responsável pelo Processamento:** Pipeline Automatizado GeoJudicial-SP (`process_pm_data.py`)
**Sistema de Referência:** WGS 84 (EPSG:4326), conforme origem IBGE/GeoSampa.
