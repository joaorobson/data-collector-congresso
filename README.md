# Coletor de normas e proposições

## Tramitação

`https://www6ghml.senado.gov.br/dadosmateria/resources/materia-bicameral/siglas-tipos-materia-bicameral`
[
  "PDL",
  "PEC",
  "PL",
  "PLP",
  "ECD",
  "PDS",
  "PDC",
  "PLC",
  "PLS",
  "SCD",
  "VET"
]

```mermaid

    flowchart TD
        LeXML --> get_normas["get_metadados_normas.py"] --> normas[("normas.json")]
        normas --> get_textos_normas["get_urls_textos_normas.py"] --> urls_textos_normas[("urls_textos_normas.json")]

        get_proj_res_cd["get_projetos_resolucao_cd_trans_norma.py"] --> proj_res_cd[("projetos_resolucao_cd_transf_norma.json")]
        normas --> get_proposicoes_de_origem_from_normas_leg_br["get_proposicoes_de_origem_from_normas_leg_br.py"] --> props_origem_normas_leg_br[("props_origem_normas_leg_br.json")]
        normas --> get_proposicoes_de_origem_from_sf["get_proposicoes_de_origem_from_sf.py"] --> props_origem_sf[("props_origem_sf.json")]
        props_origem_sf --> get_mpv_origem_plv["get_mpv_origem_plv.py"] --> mpv_origem_plv[("mpv_origem_plv.json")]

        normas --> get_proposicao_inicial
        props_origem_sf --> get_proposicao_inicial
        props_origem_normas_leg_br --> get_proposicao_inicial
        proj_res_cd --> get_proposicao_inicial
        mpv_origem_plv --> get_proposicao_inicial
        
        get_proposicao_inicial["get_proposicao_inicial.py"] --> proposicao_inicial[("proposicao_inicial.json")] --> get_fases_tramitacao["get_fases_tramitacao.py"]
        get_fases_tramitacao --> fases_tramitacao[("fases_tramitacao.json")] --> normalize_fases_tramitacao["normalize_fases_tramitacao.py"] --> fases_tramitacao_norm[("fases_tramitacao_norm.json")]
        
        proj_res_cd --> normalize_proposicoes_origem_normas
        normas --> normalize_proposicoes_origem_normas
        props_origem_sf --> normalize_proposicoes_origem_normas
        props_origem_normas_leg_br --> normalize_proposicoes_origem_normas
        fases_tramitacao_norm --> normalize_proposicoes_origem_normas

        normalize_proposicoes_origem_normas["normalize_proposicoes_origem_normas.py"] --> proposicoes_origem_normalizadas[("proposicoes_origem_normalizadas.json")]
        normalize_proposicoes_origem_normas --> proposicoes_origem_nao_encontradas[("proposicoes_origem_nao_encontradas.json")]
        proposicoes_origem_normalizadas --> c_get_autoria_proposicoes["camara/get_autoria_proposicoes.py"] --> c_autoria[("camara/autoria_proposicoes.json")]
        proposicoes_origem_normalizadas --> c_get_proposicoes["camara/get_metadados_proposicoes.py"] --> c_proposicoes[("camara/proposicoes.json")]
        c_proposicoes --> c_get_autografos["camara/get_metadados_autografos.py"] --> c_autografos[("camara/autografos.json")]
        c_proposicoes --> c_get_avulsos["camara/get_metadados_avulsos_iniciais.py"] --> c_avulsos[("camara/avulsos_iniciais.json")]
        c_proposicoes --> c_get_emendas["camara/get_metadados_emendas.py"] --> c_emendas[("camara/emendas.json")]
        c_siglas_tipos[("camara/siglas_tipos.json")] --> c_filter_siglas_tipos_relatorios_e_pareceres["camara/filter_siglas_tipos_relatorios_e_pareceres.py"] --> c_sigla_tipos_relatorios_e_pareceres[("camara/sigla_tipos_relatorios_e_pareceres.json")]
        c_proposicoes --> c_get_relatorios["camara/get_metadados_relatorios_e_pareceres.py"] --> c_relatorios[("camara/relatorios_e_pareceres.json")]
        c_sigla_tipos_relatorios_e_pareceres --> c_get_relatorios
        
        proposicoes_origem_normalizadas --> s_get_proposicoes["senado/get_metadados_proposicoes.py"] --> s_proposicoes[("proposicoes.json")]
        s_proposicoes --> s_get_autografos["senado/get_metadados_autografos.py"] --> s_autografos[("senado/autografos.json")]
        s_proposicoes --> s_get_avulsos["senado/get_metadados_avulsos_iniciais.py"] --> s_avulsos[("senado/avulsos_iniciais.json")]
        s_proposicoes --> s_get_emendas["senado/get_metadados_emendas.py"] --> s_emendas[("senado/emendas.json")]
        s_siglas_tipos[("senado/siglas_tipos.json")] --> s_filter_siglas_tipos_relatorios_e_pareceres["senado/filter_siglas_tipos_relatorios_e_pareceres.py"] --> s_sigla_tipos_relatorios_e_pareceres[("senado/sigla_tipos_relatorios_e_pareceres.json")]
        s_proposicoes --> s_get_relatorios["senado/get_metadados_relatorios_e_pareceres.py"] --> s_relatorios[("senado/relatorios_e_pareceres.json")]
        s_sigla_tipos_relatorios_e_pareceres --> s_get_relatorios


        normas --> normalize_data["normalize_data.py"] --> normas_parquet[("normas.parquet")]
        normalize_data --> proposicoes_parquet[("proposicoes.parquet")]
        normalize_data --> emendas_parquet[("emendas.parquet")]
        normalize_data --> relatorios_parquet[("relatorios.parquet")]
        urls_textos_normas --> normalize_data
        proposicoes_origem_normalizadas --> normalize_data
        proposicoes_origem_nao_encontradas --> normalize_data
        s_proposicoes --> normalize_data
        s_autografos --> normalize_data
        s_avulsos --> normalize_data
        s_relatorios --> normalize_data
        c_proposicoes --> normalize_data
        c_autografos --> normalize_data
        c_avulsos --> normalize_data
        c_relatorios --> normalize_data
        c_autoria --> normalize_data

    classDef json fill:#d1fae5,stroke:#059669,color:#064e3b
        class s_get_autografos json
```

## Instalar dependências

```
uv sync
```

## Coleta de normas

![Coleta de dados](https://github.com/joaorobson/data-collector-congresso/blob/main/data/img/coleta_dados.png)

### Coleta dos metadados de normas a partir do LeXML

* Fonte: [LeXML](https://www.lexml.gov.br/)
* Script: 
    ```
    python -m src.tasks.data_extracion.normas.get_metadados_normas
    ```
* **Campos coletados:**
  * tipo_norma
  * titulo
  * urn
  * relacionamentos
* JSON de saída: [normas.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/normas.json)

### Coleta do nome das proposições de origem da norma no portal normas.leg.br

* Fonte: [normas.leg.br](https://normas.leg.br/)
* Campos coletados:
  * urn
  * status
  * sourceProcess
    * @type
    * name
    * @id
* Script:
    ```
    python -m src.tasks.data_extraction.normas.get_proposicoes_de_origem_from_normas_leg_br
    ```
* JSON de saída: [props_origem_normas_leg_br.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/props_origem_normas_leg_br.json)

### Coleta das proposições com origem ausnte no portal normas.leg.br

* Script:
    ```
    python -m src.tasks.data_extraction.normas.get_proposicoes_com_origem_faltante
    ```
* JSON de saída: [normas_sem_proposicao_origem.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/normas_sem_proposicao_origem.json)


### Coleta do nome das proposições com origem ausente dos Dados Abertos do SF

* Fonte: [Dados Abertos do SF](https://legis.senado.leg.br/dadosabertos/api-docs/swagger-ui/index.html)
* Dados de entrada:
  * [normas_sem_proposicao_origem.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/normas_sem_proposicao_origem.json)
* Campos coletados:
  * identificacao (nome da proposição)

* Script:
    ```
    python -m src.tasks.data_extraction.normas.get_proposicao_de_origem_from_sf
    ```
* JSON de saída: [props_origem_sf.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/props_origem_sf.json)



### Coleta do nome das proposições das Resoluções da CD

* Fonte: [Dados Abertos da CD](https://dadosabertos.camara.leg.br/swagger/api.html)
* Campos coletados:
  * id
  * nomeProposicao
  * situacao
  * nome_norma
* Scripts:
  *  Coleta de URLs dos Projetos de Resolução da CD:
      ```
      python -m src.tasks.data_extraction.normas.get_urls_projetos_resolucao_cd
      ```
  * Coleta dos dados dos Projetos de Resolução da CD:
      ```
      python -m src.tasks.data_extraction.normas.get_infos_projetos_resolucao_cd
      ``` 
  * Coleta dos Projetos de Resolução da CD transformados em norma:
      ```
      python -m src.tasks.data_extraction.normas.get_projetos_resolucao_cd_transf_norma
      ```
* JSONs de saída:
  * [urls_projetos_resolucao_cd.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/urls_projetos_resolucao_cd.json)
  * [infos_projetos_resolucao_cd.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/infos_projetos_resolucao_cd.json)
  * [projetos_resolucao_cd_transf_norma.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/projetos_resolucao_cd_transf_norma.json)

### Normalização dos metadados das proposições

* Campos gerados:
  * origem_lexml
  * origem_lexml_norm
  * origem_normas.leg.br
  * origem_normas.leg.br_norm
  * origem_sf
  * origem_sf_norm
  * origem_final
  * casas

* Script:
    ```
    python -m src.tasks.data_extraction.normas.normalize_proposicoes_origem_normas
    ```
* JSON de saída: [proposicoes_origem_normalizadas.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/normas/metadados/proposicoes_origem_normalizadas.json)

### Proposições

#### Câmara dos Deputados

##### Coletar informações gerais das proposições a partir das normas

* Campos coletados:
  * id
  * uri
  * siglaTipo
  * codTipo
  * numero
  * ano
  * ementa
  * dataApresentacao
* Script:
    ```
    python -m src.tasks.data_extraction.camara.proposicoes_from_normas.get_metadados_proposicoes_from_normas
    ```
* JSON de saída: [proposicoes.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/camara/metadados/proposicoes.json)


##### Coletar emendas das proposições


* Campos coletados:
  * id
  * uri
  * siglaTipo
  * codTipo
  * numero
  * ano
  * ementa
  * dataApresentacao
* Script:
    ```
    python -m src.tasks.data_extraction.camara.proposicoes_from_normas.get_metadados_emendas
    ```
* JSON de saída: [emendas.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/camara/metadados/emendas.json)

##### Coletar pareceres e relatórios



#### Senado Federal

##### Coletar informações gerais das proposições a partir das normas

* Campos coletados:
  * autoria
  * casaIdentificadora
  * codigoMateria
  * dataApresentacao
  * dataDeliberacao
  * dataSituacaoAtual
  * ementa
  * enteIdentificador
  * id
  * identificacao
  * normaGerada
  * siglaTipoDeliberacao
  * situacaoAtual
  * tipoConteudo
  * tipoDocumento
  * tramitando
* Script:
    ```
    python -m src.tasks.data_extraction.senado.proposicoes_from_normas.get_metadados_proposicoes_from_normas.py
    ```
* JSON de saída: [proposicoes.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/senado/metadados/proposicoes.json)


##### Coletar emendas das proposições


* Campos coletados:
    * autoria
    * casa
    * codigoColegiado
    * dataApresentacao
    * decisoes
    * descricaoDocumentoEmenda
    * id
    * idCiEmenda
    * idCiEmendado
    * idDocumentoEmenda
    * idProcesso
    * identificacao
    * nomeColegiado
    * numero
    * siglaColegiado
    * subemendas
    * tipo
    * turnoApresentacao
    * urlDocumentoEmenda
* Script:
    ```
    python -m src.tasks.data_extraction.senado.proposicoes_from_normas.get_metadados_emendas
    ```
* JSON de saída: [emendas.json](https://github.com/joaorobson/data-collector-congresso/blob/main/data/senado/metadados/emendas.json)

##### Coletar pareceres e relatórios

