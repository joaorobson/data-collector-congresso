# Coletor de normas e proposições

## Normas

![Coleta de dados](https://github.com/joaorobson/data-collector-congresso/blob/main/data/img/coleta_dados.png)

### Coleta da lista de normas a partir do LeXML

* Fonte: [LeXML](https://www.lexml.gov.br/)
* Script: 
    ```
    python -m src.tasks.normas.collect_normas
    ```
* **Campos coletados:**
  * tipo_norma
  * titulo
  * urn
  * relacionamentos

### Coleta das proposições de origem da norma

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
    python -m src.tasks.data_extraction.normas.collect_proposicoes_de_origem_from_normas_leg_br
    ```

### Coleta das proposições sem origem dos Dados Abertos do SF

* Fonte: [Dados Abertos do SF](https://legis.senado.leg.br/dadosabertos/api-docs/swagger-ui/index.html)
* Campos coletados:
  * identificacao (nome da proposição)

* Script:
    ```
    python -m src.tasks.data_extraction.normas.collect_proposicao_de_origem_from_sf
    ```


### Coleta das proposições das Resoluções da CD
* Fonte: [Dados Abertos da CD](https://dadosabertos.camara.leg.br/swagger/api.html)
* Campos coletados:
  * id
  * nomeProposicao
  * situacao
  * nome_norma
* Scripts:
  *  Coleta de URLs dos Projetos de Resolução da CD:
      ```
      python -m src.tasks.data_extraction.normas.collect_urls_projetos_resolucao_cd
      ```
  * Coleta dos dados dos Projetos de Resolução da CD:
      ```
      python -m src.tasks.data_extraction.normas.collect_infos_projetos_resolucao_cd
      ``` 
  * Coleta dos Projetos de Resolução da CD transformados em norma:
      ```
      python -m src.tasks.data_extraction.normas.collect_projetos_resolucao_cd_transf_norma
      ```

### Proposições
