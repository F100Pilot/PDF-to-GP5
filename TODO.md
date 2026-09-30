# TODO

Ideias por fazer. Cada item diz em que projeto se faz: **PDF-to-GP5** (esta aplicação) ou **RockForge**.

## Conversão PDF → GP5 (PDF-to-GP5)

- [ ] **Nomes dos acordes** (PDF-to-GP5 + RockForge). Os símbolos por cima da tab ("Am", "G/B"…) iriam para o GP5. Os PDFs que tenho aqui (Songsterr) não têm nenhum, portanto faltam PDFs para testar. Do lado do RockForge também há trabalho: hoje descarta os nomes do GP e grava o `chordName` do Rocksmith vazio (`domain/chords.py`); os nomes que mostra são calculados a partir das notas.
- [ ] **Quintinas e septinas (5 e 7).** Hoje só as tercinas e as sextinas são exatas; as outras ficam com ritmo estimado pelo espaçamento.
- [ ] **Técnicas em falta:** tremolo picking (traços na haste), trilo (tr~~), alavanca (dip/dive) e volume swell. O RockForge já trata o tremolo e o trilo. Preciso de PDFs que as tenham.
- [ ] **rit. / accel.** como mudanças graduais de andamento.
- [ ] **Ler tabs a partir de um print** (imagem PNG/JPG, ou um print guardado como PDF: o PDF só tem a imagem, sem texto). Hoje só se leem PDFs com texto; um PDF só com imagem dá "PDFs digitalizados exigem OCR". Nesse caso, cada página do PDF é desenhada como imagem e segue o mesmo caminho de um PNG/JPG, também num PDF que misture páginas com texto e páginas só com imagem. **À espera de prints de exemplo** para escolher a fase e testar o OCR antes de mexer na app. Ideia: transformar o print no mesmo formato interno dos PDFs (linhas e caracteres com posição) e reaproveitar a leitura que já existe.
  1. Print de tab em texto (`e|--0--3h5--|`): OCR com a posição de cada carácter e a leitura de tab em texto atual. Trabalho médio; boa qualidade com imagens nítidas.
  2. Print de tab gravada (Songsterr, Guitar Pro): detetar cordas e barras de compasso e reconhecer os números. Trabalho grande; o ritmo fica estimado pelo espaçamento.
  3. Técnicas desenhadas (bends, slides, hastes, vibrato): trabalho muito grande, qualidade incerta.
  - Precisa de uma biblioteca de OCR (ex.: Tesseract, que no Windows se instala à parte); por escolher e testar.
  - Aceitar PNG/JPG no ecrã de conversão, processar no processo isolado com limites de tamanho e de pixels, e avisar no relatório que a leitura veio de um print e deve ser conferida.

## Ligação ao RockForge

- [x] **Comparação RockForge ↔ alphaTab:** skill `rockforge-alphatab-check`. Encontrou o let ring perdido nos `.gp` (RockForge a566e91).
- [x] **Teste de ponta a ponta até ao chart do Rocksmith:** RockForge `tests/test_gp_to_chart.py`, de GP5 até XML e SNG, verificado também com o September. Encontrou o bend comprimido quando a nota é encurtada e a curva perdida ao reler o XML (RockForge cdbdd97). Sem o jogo, que não corre aqui.
- [x] **Bends de 3 pontos como no alphaTab** (RockForge + PDF-to-GP5). "Sobe até meio da nota e fica" passa a subir ao longo da nota toda, e o mesmo nos pre-bends com release. No Rocksmith a subida fica como um único ponto no fim da nota, sem ponto no início. A skill `rockforge-alphatab-check` compara agora também a forma do bend.
- [x] **Pre-bend simples como no alphaTab** (RockForge): fica dobrado desde o início da nota, em vez de uma subida. Por testar no jogo.
- [ ] **Bends de 4 pontos que não são bend + release** (ex.: sobe e fica, com dois pontos no meio): o alphaTab também os simplifica; o RockForge usa a curva do ficheiro. Não aparecem nos ficheiros que este programa gera.

## Aplicação (PDF-to-GP5)

- [ ] **Biblioteca: cópia de segurança.** Exportar e importar a biblioteca inteira num ficheiro, e um botão para abrir a pasta da música.
- [ ] **PDFs com linhas de número de cordas diferente** (7 cordas, baixo): hoje essas linhas são ignoradas, com aviso.
