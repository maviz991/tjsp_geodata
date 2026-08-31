# Dicionário de Dados e Metadados: Mapeamento Territorial PMESP (BI)

Este documento descreve a estrutura das camadas geradas pelo pipeline de dados (`process_pm_data.py`), disponíveis em `GeoJSON`. As camadas consolidam a divisão territorial operacional da Polícia Militar do Estado de São Paulo (PMESP) — Comandos de Policiamento do Interior (CPI) e de Área Metropolitana (CPA/M) e seus Batalhões (BPM/I e BPM/M) — com a malha municipal do IBGE e, onde disponível, com os limites oficiais sub-municipais dos batalhões (Capital e Grande São Paulo).

## Diferença estrutural em relação ao mapeamento judiciário (TJSP)

No mapeamento do TJSP cada município pertence integralmente a uma única Comarca. Na PM isso só é verdade no **interior** (CPI-1 a CPI-10): lá cada batalhão responde por municípios inteiros. Na **Capital e Grande São Paulo** (CPA/M-1 a CPA/M-12), um único município pode ser dividido entre dezenas de batalhões — a cidade de São Paulo, por exemplo, é policiada por 27 Batalhões de Polícia Militar Metropolitanos (BPM/M) simultaneamente, cada um responsável por um conjunto de bairros/distritos, não pelo município inteiro.

Por isso este produto tem **duas camadas de polígono com propósitos distintos**, mais **cinco camadas de pontos georreferenciados** — uma para cada nível da hierarquia operacional da PM:

```
Comando (CPA/M ou CPI)
 └── Batalhão (BPM/M ou BPM/I)
      └── Companhia (Cia PM)
           └── Pelotão (Pel PM)
                └── Grupo / Esquadra (menor subdivisão operacional)
```

* **Camada 1 (`pm_municipios_sp`)** — um polígono por município (malha IBGE), útil para join com dados socioeconômicos municipais. Carrega o "batalhão principal" (o de maior presença de efetivo/unidades no município), a lista completa de todos os batalhões presentes, e contagens agregadas de toda a hierarquia (comandos/companhias/pelotões/grupos) presente no município — ver Camada 1 abaixo.
* **Camada 2 (`pm_batalhoes_sp`)** — um polígono por batalhão, esta sim representando de fato "os limites da área do batalhão". Usa o limite oficial sub-municipal do GeoSampa quando disponível; caso contrário, é construída dissolvendo os municípios do IBGE atribuídos àquele batalhão.
* **Camadas 3 a 7** — um ponto georreferenciado por unidade, uma camada por nível da hierarquia (comando, batalhão, companhia, pelotão, grupo/esquadra).

## Fontes de Dados

1. **Registro de Unidades Policiais (PMESP)** — API oficial `Pmesp.Unidades.Policiais.Api` (`servicesapp.policiamilitar.sp.gov.br`), que expõe o endereço, cidade e hierarquia (Comando → Batalhão → Companhia → Pelotão → Grupo) de cada Organização Policial Militar (OPM) ativa. É a fonte primária da relação município ↔ batalhão.
2. **GeoSampa (Prefeitura de São Paulo) — WFS `geoportal:batalhao_policia_militar`** — limites oficiais poligonais dos batalhões metropolitanos que cobrem a Capital e parte da Grande São Paulo (27 dos 44 BPM/M têm limite oficial nesta fonte).
3. **Malha Municipal do IBGE** (API de Malhas, `estados/35`, nível município) — geometria de todos os 645 municípios de São Paulo.
4. **População do Censo IBGE 2022** (API de Agregados, tabela 9514) — população residente por município.
5. **Google Geocoding API** (via chave em `GOOGLE_MAPS_API_KEY` no `.env`), com **Nominatim (OpenStreetMap)** como fallback caso o Google falhe — geocodificação do endereço de cada unidade da hierarquia (comando, batalhão, companhia, pelotão, grupo/esquadra), usada para posicionar cada ponto com maior precisão do que um centroide municipal.

## Camada 1: `pm_municipios_sp.geojson` (um polígono por município)

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_municipio_ibge` | INTEGER | Código IBGE do município (7 dígitos). |
| `nome_municipio` | VARCHAR | Nome oficial do município. |
| `populacao_municipio` | INTEGER | População residente (Censo IBGE 2022). |
| `id_comando` | VARCHAR | Código do comando ao qual pertence o batalhão principal do município (ex.: `CPI-8`, `CPA/M-6`). |
| `nome_comando` | VARCHAR | Nome formatado do comando (ex.: "8º Comando de Policiamento do Interior (CPI-8)"). |
| `tipo_comando` | VARCHAR | `interior` ou `metropolitano`. |
| `nome_batalhao_principal` | VARCHAR | Batalhão com maior presença de unidades (Cia/Pel/Grupamento) no município — usado para visualização em municípios com mais de um batalhão. |
| `qt_batalhoes` | INTEGER | Quantidade de batalhões distintos com alguma unidade sediada no município. `1` na quase totalidade do interior; até `27` em São Paulo (Capital). |
| `batalhoes_lista` | TEXT | Lista de todos os batalhões presentes no município, separados por vírgula. |
| `endereco_sede_batalhao` | VARCHAR | Endereço da sede do batalhão principal. |
| `latitude_sede_batalhao` / `longitude_sede_batalhao` | DOUBLE | Coordenadas da sede do batalhão principal, geocodificadas a partir do endereço (ver `fonte_geocodificacao_sede`). |
| `fonte_geocodificacao_sede` | VARCHAR | `Nominatim (OpenStreetMap)` ou `Google Geocoding API` conforme qual serviço encontrou o endereço; `Centroide do município-sede (endereço não geocodificado)` quando nenhum dos dois retornou resultado. |
| `qt_comandos` | INTEGER | Quantidade de comandos (CPI/CPA-M) distintos com alguma unidade no município — normalmente `1`; maior nos poucos municípios cobertos por batalhões de comandos diferentes. |
| `comandos_lista` | TEXT | Lista dos comandos presentes no município, separados por vírgula. |
| `qt_companhias` | INTEGER | Quantidade de companhias (Cia PM) distintas com alguma unidade sediada no município. |
| `qt_pelotoes` | INTEGER | Quantidade de pelotões (Pel PM) distintos com alguma unidade sediada no município. |
| `qt_grupos` | INTEGER | Quantidade de grupos/esquadras distintos sediados no município. |
| `fonte_atribuicao` | VARCHAR | `Registro direto PMESP` quando o município tem posto/unidade PM próprio no cadastro oficial; `Atribuição por proximidade` para os 19 municípios sem unidade cadastrada localmente, atribuídos ao batalhão do município vizinho mais próximo com registro. |
| `geometry` | MULTIPOLYGON | Geometria poligonal do território municipal (malha IBGE). |

As contagens `qt_companhias`/`qt_pelotoes`/`qt_grupos` só trazem números agregados (não listas de nomes) porque em municípios grandes — sobretudo a Capital — a lista completa seria enorme; para o detalhe unidade a unidade, use as Camadas 5 a 7 (pontos de companhia/pelotão/grupo) filtrando por `cidade`.

## Camada 2: `pm_batalhoes_sp.geojson` (um polígono por batalhão — 98 no total)

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `nome_batalhao` | VARCHAR | Identificação do batalhão (ex.: "9º BPM/I", "22º BPM/M"). |
| `tipo_batalhao` | VARCHAR | `Interior` (BPM/I, 55 batalhões) ou `Metropolitano` (BPM/M, 43 batalhões). |
| `id_comando` | VARCHAR | Código do comando ao qual o batalhão está subordinado. |
| `nome_comando` | VARCHAR | Nome formatado do comando. |
| `cidade_sede` | VARCHAR | Município onde fica a sede do batalhão. |
| `endereco_sede` | VARCHAR | Endereço completo da sede. |
| `latitude_sede` / `longitude_sede` | DOUBLE | Coordenadas da sede, geocodificadas a partir do endereço (ver `fonte_geocodificacao_sede`). |
| `fonte_geocodificacao_sede` | VARCHAR | `Nominatim (OpenStreetMap)` ou `Google Geocoding API` conforme qual serviço encontrou o endereço; `Centroide do município-sede (endereço não geocodificado)` quando nenhum dos dois retornou resultado. |
| `fonte_geometria` | VARCHAR | Origem da geometria da área do batalhão — ver seção seguinte. |
| `qt_municipios` | INTEGER | Quantidade de municípios dissolvidos para formar o polígono (nulo quando a geometria vem do limite oficial GeoSampa, que é sub-municipal). |
| `municipios_atendidos` | TEXT | Lista dos municípios dissolvidos (nulo quando a geometria vem do GeoSampa). |
| `populacao_atendida` | INTEGER | Soma da população dos municípios dissolvidos (nulo quando a geometria vem do GeoSampa, por não representar a população real da área sub-municipal). |
| `geometry` | MULTIPOLYGON | Geometria do território do batalhão. |

### Valores de `fonte_geometria`

* **Limite oficial GeoSampa (sub-municipal)** — 27 batalhões metropolitanos com polígono oficial publicado pela Prefeitura de São Paulo. Mais preciso; não segue limites municipais.
* **Dissolução da malha municipal IBGE (batalhão principal)** — 69 batalhões (majoritariamente do interior) cujo polígono é a união dos municípios do IBGE em que este é o batalhão de maior presença.
* **Dissolução da malha municipal IBGE (área compartilhada com outro batalhão no(s) mesmo(s) município(s))** — 2 batalhões (40º BPM/M, 55º BPM/I) que nunca são o batalhão "principal" de nenhum município (dividem sede com outro batalhão maior no mesmo município) e não têm limite GeoSampa próprio. O polígono resultante **se sobrepõe** ao de outro batalhão — tratar como aproximação, não como limite exclusivo.

## Correções de cadastro aplicadas

O cadastro oficial de OPMs consultado (fonte 1) reflete a estrutura administrativa da PMESP, mas pode ficar desatualizado em relação a reorganizações reais. Batalhões confirmados como extintos por fontes independentes são excluídos do processamento (não aparecem em nenhuma das camadas), em vez de remapeados para o batalhão sucessor — sabe-se que a responsabilidade foi transferida, mas não como cada subunidade (companhia/pelotão) foi individualmente redistribuída, então remapear seria um chute.

| Batalhão excluído | Motivo | Fontes |
| :--- | :--- | :--- |
| 44º BPM/M (Parque Cecap, Guarulhos) | Fechado em 02/2022; atividades unificadas ao 31º BPM/M, que assumiu a responsabilidade administrativa pela região. O prédio reabriu em 04/2022 como sede do 15º BAEP (unidade tática, não territorial) — achado reportado pelo usuário via Google Street View, ainda listado no cadastro oficial com o endereço antigo. | [Click Guarulhos, 21/02/2022](https://www.clickguarulhos.com.br/2022/02/21/batalhao-da-policia-militar-no-cecap-e-fechado/); [GuarulhosWeb](https://guarulhosweb.com.br/dois-meses-apos-encerramento-novo-batalhao-da-policia-e-inaugurado-no-cecap/); [Biblioteca Jurídica SP (nota oficial)](https://www.bibliotecajuridica.sp.gov.br/governo-de-sp-inaugura-15o-batalhao-de-acoes-especiais-de-policia-em-guarulhos/) |

Novas divergências encontradas devem ser adicionadas a `KNOWN_DEFUNCT_BATTALIONS` em `process_pm_data.py`, com a fonte que confirma a mudança.

### Registros inseridos manualmente (`MANUAL_HIERARCHY_ADDITIONS`)

Ao excluir o 44º BPM/M inteiro (em vez de remapear suas subunidades), a área do Parque Cecap ficou sem nenhum registro sob um batalhão ativo — o cadastro OPM só a vincula ao 44º (excluído) e ao 15º BAEP (fora do escopo territorial). Para não deixar essa lacuna silenciosa, foi inserido manualmente **1 registro de companhia** representando essa área, com o mesmo endereço do antigo 44º BPM/M, sob o **31º BPM/M** — não o 15º BPM/M: a nota de fechamento diz que a responsabilidade foi unificada ao 31º, e a placa "15º" visível no prédio (Street View, confirmado pelo usuário) é do 15º BAEP, uma unidade diferente.

Diferente das correções de exclusão (que só removem dado comprovadamente errado), esta é uma **inferência nossa, não um dado oficial da PM** — por isso o registro é sinalizado de forma explícita em vários campos para não ser confundido com um registro real do cadastro:

| Campo | Valor |
| :--- | :--- |
| `companhia` (Camada 5) | `CECAP (AJUSTE MANUAL)` |
| `opm_nome` | `ÁREA DO PARQUE CECAP (AJUSTE MANUAL — sem registro OPM oficial; responsabilidade unificada ao 31º BPM/M após o fechamento do 44º BPM/M em 02/2022, não confirmada unidade a unidade)` |
| `opm_codigo` | `INFERIDO-CECAP-31BPMM` (não é um código OPM real — os códigos oficiais são só numéricos) |

Filtrar por `opm_codigo` começando com `INFERIDO-` (ou `companhia` contendo `AJUSTE MANUAL`) identifica todo registro inserido dessa forma. Novas adições devem seguir o mesmo padrão em `MANUAL_HIERARCHY_ADDITIONS`, com a fonte/raciocínio documentado em comentário no código.

## Camada 3: `pm_batalhoes_sedes_pontos_sp.geojson`

Um ponto por batalhão (98 pontos), geocodificado a partir do endereço de sede (logradouro + bairro + cidade) — mais preciso do que o centroide municipal usado como proxy no mapeamento do TJSP. Batalhões cujo endereço não for encontrado recebem, em vez disso, o centroide do município-sede (ver `fonte_geocodificacao_sede`). Mesmos atributos da Camada 2 (exceto geometria, que é `POINT`).

## Camada 4: `pm_comandos_pontos_sp.geojson`

Um ponto por comando (22 no total: 10 CPI + 12 CPA/M).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_comando` | VARCHAR | Código do comando (ex.: `CPI-3`, `CPA/M-11`). |
| `nome_comando` | VARCHAR | Nome formatado do comando. |
| `tipo_comando` | VARCHAR | `interior` ou `metropolitano`. |
| `qt_batalhoes` | INTEGER | Quantidade de batalhões ativos subordinados a este comando. |
| `cidade_sede` | VARCHAR | Município da sede do comando. |
| `endereco_sede` | VARCHAR | Endereço da sede. |
| `latitude` / `longitude` | DOUBLE | Coordenadas geocodificadas. |
| `fonte_geocodificacao` | VARCHAR | Ver nota sobre sede aproximada abaixo. |
| `telefone` | VARCHAR | Telefone de contato do comando. Ver nota sobre confiabilidade abaixo. |
| `email` | VARCHAR | E-mail de contato do comando. Ver nota sobre confiabilidade abaixo. |
| `fonte_contato` | VARCHAR | Origem do `telefone`/`email` desta linha — ver nota abaixo. |
| `opm_nome` / `opm_codigo` | VARCHAR | Nome e código da unidade no cadastro OPM de origem. |
| `geometry` | POINT | |

**Sede aproximada (7 dos 22 comandos):** apenas 15 comandos têm um registro de sede administrativa própria no cadastro OPM (todos os 10 CPI, e 5 dos 12 CPA/M). Para os outros 7 (`CPA/M-1, 3, 4, 5, 7, 8, 11`), o ponto usa a sede do batalhão de menor numeração subordinado a esse comando como aproximação — na prática o comando costuma dividir prédio com um de seus batalhões (confirmado para o CPA/M-7, cuja sede fica no mesmo endereço do 15º BPM/M, achado do usuário via Street View). Esses casos têm `fonte_geocodificacao` começando com `"Aproximado: sem sede administrativa própria no cadastro OPM..."` — filtrar por esse prefixo para identificá-los.

**Telefone/e-mail — confiabilidade desigual, leia antes de usar:** o cadastro OPM (fonte 1) não tem nenhum campo de contato — nem telefone, nem e-mail, em nenhum nível da hierarquia. Os campos `telefone`/`email` desta camada vieram de uma pesquisa à parte, fora do cadastro oficial, com apenas **2 dos 22 comandos verificados na fonte primária** (CPI-1 e CPA/M-2, conferidos direto em páginas do site `policiamilitar.sp.gov.br`). Os outros 20 vieram de sites agregadores/diretórios de terceiros (não oficiais, tipo "consulta CNPJ") e **não foram verificados** — durante a pesquisa, pelo menos 2 números encontrados nesses agregadores tinham DDD `"01"` (não existe no Brasil) e foram descartados por completo em vez de incluídos errados; outros 2 casos (CPI-3, CPI-9) têm números diferentes conforme a fonte consultada (ambos registrados em `fonte_contato`). **Sempre conferir `fonte_contato` antes de usar um telefone/e-mail desta camada** — `"Verificado (policiamilitar.sp.gov.br)"` é confiável; qualquer variação de `"Não verificado"` deve ser tratada como pista, não como dado confirmado. `telefone`/`email` nulos significam que a pesquisa não encontrou nada (não que o comando não tenha contato).

## Camadas 5 a 7: `pm_companhias_pontos_sp.geojson`, `pm_pelotoes_pontos_sp.geojson`, `pm_grupos_pontos_sp.geojson`

Um ponto por unidade em cada nível — 650 companhias, 1.433 pelotões, 1.060 grupos/esquadras. Mesma estrutura de colunas nas três camadas, cada uma acrescentando o código do próprio nível:

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_comando` / `nome_comando` | VARCHAR | Comando ao qual a unidade pertence. |
| `nome_batalhao` / `tipo_batalhao` | VARCHAR | Batalhão ao qual a unidade pertence. |
| `companhia` | VARCHAR | Código da companhia conforme o cadastro OPM (ex.: `1.CIA`, `EM`, `CIA FT`) — presente nas 3 camadas. |
| `pelotao` | VARCHAR | Código do pelotão (ex.: `1.PEL PM`, `ADM`, `CGP`, `TERRITORIAL`) — presente em `pm_pelotoes_pontos_sp` e `pm_grupos_pontos_sp`. |
| `grupo` | VARCHAR | Código do grupo/esquadra — presente só em `pm_grupos_pontos_sp`. |
| `cidade` | VARCHAR | Município onde a unidade está sediada. |
| `endereco` | VARCHAR | Endereço completo. |
| `latitude` / `longitude` | DOUBLE | Coordenadas geocodificadas. |
| `fonte_geocodificacao` | VARCHAR | `Google Geocoding API`, `Nominatim (OpenStreetMap)` ou o fallback de centroide do município. |
| `opm_nome` | VARCHAR | Nome descritivo da unidade no cadastro (mais legível que os códigos brutos — ex.: "1ª COMPANHIA DE POLÍCIA MILITAR", "SEÇÃO DE POLÍCIA JUDICIÁRIA MILITAR E DISCIPLINA"). |
| `opm_descricao` | VARCHAR | Caminho hierárquico completo conforme o cadastro (ex.: `CPI-1 1.BPM/I 1.CIA PM 0 GP/PM`). |
| `opm_codigo` | VARCHAR | Código único da unidade no cadastro OPM. |
| `geometry` | POINT | |

**Sobre os códigos `companhia`/`pelotao`/`grupo`:** vêm literalmente do cadastro da PM e nem sempre são um número — muitos são siglas administrativas (`ADM` = Administração, `CGP` = Comando de Grupo Patrulha, `EM` = Estado-Maior, `TERRITORIAL`, `P/2`/`P/3`/`P/5` = seções do estado-maior, `MOTOMEC` = motomecanizado) em vez de "1º Pelotão" etc. — a companhia, o pelotão ou o grupo pode ser uma subdivisão funcional, não geográfica. O valor `"0"` (50 casos em pelotão, 416 em grupo) é um marcador de "sem subdivisão adicional nesse nível", não uma unidade "zero" real — mesmo assim o endereço/ponto geocodificado é real e válido.

**Um único endereço geocodificado para toda a hierarquia:** o pipeline geocodifica cada endereço físico **uma única vez** (por `logradouro+bairro+cidade`) e reaproveita o resultado em todos os níveis que compartilham aquele endereço — por isso a Camada 3 (batalhões, 98 pontos) e as Camadas 4 a 7 juntas totalizam apenas **1.473 geocodificações únicas**, não a soma bruta de todas as unidades (~3.264). O Nominatim é mantido como fallback: nesta rede, boa parte das suas requisições é silenciosamente redirecionada para um host chamado `proxy` (visível nos avisos `InsecureRequestWarning` do `urllib3` durante a execução) — sinal de um antivírus/EDR/VPN corporativo com inspeção de HTTPS bloqueando parte do tráfego para `nominatim.openstreetmap.org`. O script mantém um cache em `scratch/geocode_cache.json` (por endereço, com a fonte que resolveu cada um) — reexecuções não geocodificam de novo o que já foi resolvido.

**Consulta estruturada, não texto livre:** tanto o Google quanto o Nominatim recebem o logradouro/bairro separado do município (`components=locality:...` no Google; `street`/`city`/`state`/`country` no Nominatim) em vez de uma única string livre — isso evita que um nome de rua/praça comum em várias cidades ("Avenida Faria Lima", "Praça da República") seja casado com a ocorrência mais famosa (quase sempre em São Paulo Capital) em vez da cidade correta.

**Validação geográfica pós-geocodificação:** mesmo com consulta estruturada, o Google às vezes ainda retorna um ponto fora do município pedido. Por isso, depois de geocodificar, cada ponto é conferido contra o polígono do próprio município (malha do IBGE, com ~3 km de folga para imprecisão de endereço/fachada); se cair fora, o resultado é descartado, uma segunda tentativa é feita no Nominatim, e se essa também falhar (ou também cair fora), o ponto usa o centroide do município com `fonte_geocodificacao` = `"Centroide do município-sede (geocodificação rejeitada: fora dos limites do município)"` — diferente do caso em que o endereço simplesmente não foi encontrado por nenhum serviço. **Nesta execução, 31 dos 1.473 endereços (2,1%) foram rejeitados dessa forma** (ex.: "Praça da República, 55, Centro" em Pereiras e "Avenida Faria Lima, 241" em Jacareí, ambos originalmente casados com os endereços homônimos mais famosos, em São Paulo Capital — achados reportados pelo usuário) e usam o centroide do município. Entradas rejeitadas também são removidas do cache em disco, então uma reexecução tenta geocodificá-las de novo (útil se o Google corrigir o resultado no futuro).

## Considerações Analíticas

* **Municípios sem posto PM próprio (19 casos):** Biritiba Mirim, Borebi, Castilho, Dois Córregos, Gabriel Monteiro, Iaras, Itatinga, Juquitiba, Lavínia, Palmeira d'Oeste, Pereira Barreto, Pirapora do Bom Jesus, Reginópolis, Rio Grande da Serra, Salesópolis, Santa Isabel, São Lourenço da Serra, Valparaíso e Vinhedo. Não têm unidade cadastrada no registro oficial de OPMs consultado; foram atribuídos por proximidade geométrica ao batalhão do município vizinho mais próximo já mapeado. Revisar caso a área de policiamento real seja conhecida.
* **Municípios com múltiplos batalhões:** além da Capital (27 batalhões), há sobreposição em cidades grandes do interior e da Grande São Paulo — Campinas, Ribeirão Preto, Bauru, Sorocaba, Piracicaba, Jundiaí, Jacareí, São José dos Campos, São Bernardo do Campo, Guarulhos, Palmital, Dracena e Nova Granada — em geral porque a sede administrativa de mais de um batalhão fica na mesma cidade. A coluna `batalhoes_lista` (Camada 1) preserva todos os batalhões envolvidos.
* **Uso recomendado:** para análises que exigem o limite territorial real de um batalhão, usar a Camada 2 (`pm_batalhoes_sp`) e dar preferência às feições com `fonte_geometria = 'Limite oficial GeoSampa'`. Para join com dados socioeconômicos por município (IBGE, DataSUS etc.), usar a Camada 1 (`pm_municipios_sp`).
* **Data de referência:** cadastro de unidades policiais e limites GeoSampa conforme disponíveis na data de processamento (ver campo `dt_atualizacao` das camadas de origem). População: Censo IBGE 2022.

## Arquivos Gerados

`process_pm_data.py` grava com os nomes abaixo à esquerda (não foi alterado); os nomes à direita são como os arquivos estão hoje em `output/`, renomeados manualmente para publicação no GeoServer, no padrão `pmesp_{numero}_tipo_sp_pontos` para as camadas de ponto (número = ordem hierárquica) e `pmesp_tipo_sp_polygon` para as duas de polígono (sem número, fora da sequência). Os estilos CSS (gerados por `scratch/gen_css_pm.py`) já saem direto com esse nome. Renomear os `.geojson` de novo após cada execução do script continua manual.

| Gerado pelo script | Nome atual em `output/` | Conteúdo |
| :--- | :--- | :--- |
| `pm_municipios_sp.geojson` | `pmesp_municipios_sp_polygon.geojson` | Polígonos dos 645 municípios com batalhão/comando e contagens da hierarquia (Camada 1). |
| `pm_batalhoes_sp.geojson` | `pmesp_batalhoes_sp_polygon.geojson` | Polígonos dos 98 batalhões ativos, geometria oficial ou dissolvida (Camada 2). |
| `pm_comandos_pontos_sp.geojson` | `pmesp_1_comandos_sp_pontos.geojson` | Pontos dos 22 comandos, com telefone/e-mail (Camada 3). |
| `pm_batalhoes_sedes_pontos_sp.geojson` | `pmesp_2_batalhoes_sp_pontos.geojson` | Pontos das sedes dos 98 batalhões (Camada 4). |
| `pm_companhias_pontos_sp.geojson` | `pmesp_3_companhias_sp_pontos.geojson` | Pontos das 650 companhias (Camada 5). |
| `pm_pelotoes_pontos_sp.geojson` | `pmesp_4_pelotoes_sp_pontos.geojson` | Pontos dos 1.433 pelotões (Camada 6). |
| `pm_grupos_pontos_sp.geojson` | `pmesp_5_grupos_sp_pontos.geojson` | Pontos dos 1.060 grupos/esquadras (Camada 7). |

**Estilos (CSS do GeoServer — compilam para SLD internamente; nomes já batem com o arquivo atual de cada camada; gerados por `scratch/gen_css_pm.py`):**

9. `estilo_pm_comando.sld`: estilo XML legado (22 cores por Comando), gerado originalmente para a Camada 2 — mantido por compatibilidade, mas substituído em uso pelo CSS abaixo.
10. `pmesp_municipios_sp_polygon.css` / `pmesp_batalhoes_sp_polygon.css`: preenchimento categórico por `id_comando` (22 cores).
11. `pmesp_1_comandos_sp_pontos.css` a `pmesp_5_grupos_sp_pontos.css`: ponto colorido pelo **mesmo `id_comando`/mesma paleta dos polígonos** (não por `tipo_batalhao`/`tipo_comando`) — assim um ponto casa visualmente com a cor da região do comando por baixo dele quando as camadas são vistas juntas, em vez de só marcar interior/metropolitano, o que já fica óbvio pela posição. Tamanho decrescente por nível hierárquico (16px comando, 11px batalhão, 7px companhia, 5px pelotão, 3px grupo/esquadra). Sem rótulo em nenhuma das 5 (removido — 22 rótulos por camada em cima uns dos outros ficava mais confuso que útil); a identificação da unidade fica pela cor + pela tabela de atributos.
12. `pmesp_municipios_sp_polygon_solid.css`, `pmesp_batalhoes_sp_polygon_solid.css`, `pmesp_1_comandos_sp_pontos_solid.css` a `pmesp_5_grupos_sp_pontos_solid.css`: **alternativa de cor única por camada** (sem categorizar por comando) — útil pra ver as 7 camadas juntas distinguindo só o *nível* hierárquico, não o comando. Cada camada tem uma cor fixa própria: município `#e5e5e5`, batalhão (polígono) `#fca311`, comando (ponto) `#e63946`, batalhão (ponto) `#f4a261`, companhia `#2a9d8f`, pelotão `#264653`, grupo/esquadra `#6a4c93`.

**Cuidados ao editar esses CSS — pegadinhas do módulo CSS do GeoServer que já pegaram nessa sessão:**
* **Não adicionar um `* { ... }` de fallback junto com regras categóricas.** Diferente do CSS de navegador, "a última regra que bate vence" não existe aqui — quando mais de uma regra combina com a mesma feição, **as duas são desenhadas, uma sobre a outra** (pensado pra empilhar símbolos, tipo contorno + preenchimento). Como toda feição aqui sempre tem um `id_comando` válido, um `*{}` de fallback bate em cima da regra colorida específica E desenha por cima — foi isso que deixou os 22 comandos aparecendo cinza da primeira vez. Os arquivos categóricos não têm fallback por causa disso; os `_solid` usam `* { ... }` sozinho, sem conflito, porque é a única regra do arquivo.
* **`mark: symbol(circle)` sem aspas.** Com aspas (`symbol('circle')`) o nome da marca não é reconhecido e cai no padrão cinza do GeoServer.
* **`fill`/`stroke` de um mark explícito vão dentro de `:mark { ... }`**, nunca soltos ao lado de `mark: symbol(...)` — soltos, são ignorados silenciosamente (sem erro) e o símbolo usa o preenchimento cinza padrão.
* **O bloco `:mark { ... }` tem que ser o último item da regra.** Qualquer propriedade solta depois dele (como `label:`) dá erro de parse (`Invalid input ..., expected ... '}'`).
* **Título de legenda vem de um comentário `/* @title ... */` imediatamente antes da regra**, não é gerado automaticamente a partir do seletor — sem ele, a legenda mostra o símbolo colorido sem nenhum texto ao lado.
