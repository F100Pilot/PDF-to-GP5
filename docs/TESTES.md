# Testes

O que é testado nesta aplicação, o que já foi verificado e o que ainda falta
testar à mão. Atualizar depois de cada teste: passar de "Por testar" para
"Confirmado", com a data e a música.

Os testes no Rocksmith (o PSARC que o RockForge cria a partir do GP) estão no
RockForge, em `docs/TESTES-NO-JOGO.md`.

**Versão atual: 0.7.0** (2026-09-30). As verificações abaixo foram feitas nesta
versão, salvo indicação em contrário; o que está "Por testar à mão" é para testar
nela. O que mudou está nas Novidades da aplicação (`CHANGELOG.md` /
`CHANGELOG.en.md`).

## Automáticos

Correm na sessão do Claude, sem ninguém a ver, e não precisam de rede.

| O quê | Como | Última vez | Resultado |
|---|---|---|---|
| Testes (`pytest`) | `.venv/bin/python -m pytest` | 2026-10-01, 0.7.0 + OCR | 488 passam (inclui `test_i18n.py`: nenhum texto sem tradução; `test_changelog.py`: as Novidades em inglês com as mesmas entradas; `test_raster.py`: tab em imagem PNG/JPEG/WebP, de 850 a 5000 px, recorte de uma pauta, PDF só com imagens, limites, telemetria do ONNX Runtime desligada; título, artista e BPM lidos de uma imagem; compasso 3/4, 6/8, 12/8, 4/4 e mudança a meio, de 1000 a 2600 px) |
| Estilo (`ruff`) | `.venv/bin/ruff check .` e `ruff format --check .` | 2026-10-01, 0.7.0 + OCR | Sem erros |
| OCR nos 13 PDFs desenhados como imagem | Cada página renderizada e lida por OCR, comparada nota a nota com a leitura do PDF vetorial | 2026-10-01 | 99,9 % das notas encontradas, 99,7 % com o traste certo, ~4 % de notas a mais |
| Técnicas escritas em imagens (H/P, P.M., let ring, PH/AH/N.H.) | 12 tabs geradas com estas marcas (letras Helvetica, tracejados), desenhadas como PNG a 1000, 1300 e 1600 px, comparadas nota a nota com a leitura do PDF vetorial; também em JPEG e numa página sem marcas (números de compasso, ruído de dígitos, cabeçalho) e numa tab com ritmo desenhado | 2026-10-11 | Todas as 1269 notas marcadas lidas como no PDF, nenhuma inventada (nas imagens em que as notas saem iguais às do PDF); JPEG 47 de 48 (um hammer-on perdido pela colocação das notas, não pela leitura da letra); nada inventado sem marcas; +0,1 a 0,3 s por página. Os teus 13 PDFs não estavam nesta sessão: por testar com prints reais (ponto 14) |
| Slides em imagens | 10 tabs geradas com slides entre notas, para dentro e para fora, desenhadas como PNG a 1000, 1300 e 1600 px e comparadas nota a nota com o PDF vetorial; 6 em JPEG; 14 páginas sem slides (H/P, P.M., harmónicos, ghost notes, bends, ritmo desenhado, compasso) | 2026-10-11 | 589 de 590 slides como no PDF, nenhum inventado (o "a mais" a 1600 px é um slide desenhado que o PDF falha); JPEG 152 de 157; 0 slides inventados em 2049 notas sem slides; +0,04 s por página. A 1000 px, com slides desenhados, o OCR dos trastes perde mais notas do que sem eles (já antes desta mudança) |
| Vibrato em imagens | 8 tabs geradas com vibratos (linha ondulada desenhada como traço, que o leitor de PDFs não vê: a referência são as notas marcadas), desenhadas como PNG a 1000, 1300 e 1600 px; 8 em JPEG; 51 páginas com palavras por cima da pauta ("minimum", "mum", "una corda", "acc.", "rit.", "wow", "uuu"…, normais, negrito e itálico, de 5 a 9 pt); 42 imagens de outros testes | 2026-10-11 | 382 de 382, nenhum inventado; JPEG 98 de 98; 0 vibratos inventados nas páginas com palavras e nas outras imagens; +0,05 s por página. "vvv"/"www" a negrito com as letras a tocar-se seriam lidos como vibrato |
| Ligaduras e arcos em imagens | 12 tabs geradas com ligaduras (nota entre parêntesis), ghost notes, legato slides (arco por cima de um slide) e ligaduras para um compasso vazio, desenhadas como PNG a 1000, 1300 e 1600 px e comparadas evento a evento com o PDF vetorial; 8 em JPEG; 69 imagens sem arcos (parêntesis, bends, slides, vibrato, palavras por cima da pauta) | 2026-10-11 | Nas pautas com os mesmos números do PDF: 116 de 117 ligaduras, 48 de 48 ghost notes, 47 de 47 legato slides, nenhum arco inventado; 63 de 63 compassos prolongados; JPEG 60 de 61; 0 arcos inventados nas 69 imagens. A leitura dos números erra mais com parêntesis e arcos ("(1)" → "11", "(11)" → três "1"): 48 de 108 pautas com algum número diferente, 10 de 108 sem parêntesis nem arcos — já antes desta mudança |
| Bends em imagens | 8 tabs geradas com bends (full e 1/2), bends com release e pre-bends, desenhadas como PNG a 1000, 1300 e 1600 px e comparadas nota a nota com o PDF vetorial; uma grelha com cada tipo em cada corda; páginas sem bends com palavras a negrito por cima da pauta, marca de tempo, ligaduras, slides e vibrato | 2026-10-11 | Nas imagens com os números iguais: a 1300 px 42 de 42 bends, 37 de 38 releases, 29 de 36 pre-bends; a 1600 px 11/11, 8/11, 11/14; a 1000 px 6/7, 3/6, 4/10. Um release falhado deixa o bend sem volta. JPEG a 1300 px: 25/25, 25/25, 18/28. Nenhum bend nem seta inventados nas páginas sem bends. +0,17 s por página. Nesta disposição apertada, 10 de 24 imagens tinham todos os números certos com bends e 14 de 24 sem eles (leitura dos números, já existia) |
| Título, artista e BPM de imagens | Página 1 dos 13 PDFs como PNG a 1000, 1300, 1600 e 2600 px, comparada com a leitura do PDF | 2026-10-01 | 52 de 52 iguais (no print do UG: "Youre A God", "Vertical Horizon", 97, Mib, 4/4 — também no PDF original, com o título e o artista em texto) |
| Jet Lag como imagem, compasso a compasso | O PDF da Jet Lag (Simple Plan) desenhado como imagem, comparado com a leitura do PDF | 2026-10-01 | 119 de 119 compassos com as mesmas notas a 1300 px, 116 a 1600, 101 a 1000; nota a nota 100 %, 99,8 % e 99,2 %. 119 compassos (números de compasso e pausas de vários compassos lidos), 145 BPM. 16 s no processo isolado; análise do formulário 3 s |
| Compasso de imagens | Todas as páginas dos 13 PDFs como imagem, comparadas com a leitura do PDF | 2026-10-01 | 13 de 13 com o 4/4 certo, nenhum compasso a mais (antes da leitura só como dígitos: "4" lido como "L" ou como carácter chinês) |
| Ligaduras vs. notas entre parêntesis | Os 13 PDFs, nota a nota, antes e depois da correção | 2026-10-01 | Mudam só notas entre parêntesis sem arco (Jet Lag 18, Happen To Me Guitar 1/Pro 38, Guitar 2/3 37 — semicolcheias em palm mute —, Guitar 4 2, September 1, Hotel California Pro 1): passam de ligadura a ghost note; conferido no PDF |
| Os 12 PDFs vetoriais não mudam com o OCR | GP5 de cada um antes e depois | 2026-10-01 | Iguais byte a byte (nenhuma página é lida por OCR) |
| GP5 igual ao alphaTab | Skill `gp-alphatab-check`, nos 12 PDFs e no `September.gp` | 2026-09-30, 0.7.0 | Tudo igual, incluindo o `.gp` exportado pelo alphaTab |
| RockForge igual ao alphaTab | Skill `rockforge-alphatab-check`, nos 12 PDFs | 2026-09-30, 0.7.0 (RockForge d0e6c11) | Tudo igual, incluindo a forma dos bends |

PDFs usados (os teus, não guardados no repositório): Daughtry "September" (Lead
Guitar); Eagles "Hotel California" (Lead 1, 2, 3 e Pro, duas versões); Russell
Dickerson "Happen To Me" (Acoustic, Guitar 1 a 4 e Pro).

## `.gp` exportados por ti, verificados aqui

| Ficheiro | Data | Verificação | Resultado |
|---|---|---|---|
| `September.gp` (6 pistas, com áudio) | 2026-09-30 | `gp-alphatab-check` | Igual ao `.gp` que o alphaTab exporta (5692 notas, 71 compassos) |
| | | `rockforge-alphatab-check` | As 6 pistas iguais, incluindo a forma dos bends |
| | | Áudio no ficheiro | `Content/Assets/backing-track.mp3` (5,7 MB), pista de áudio ativa; o RockForge encontra-o e extrai um MP3 válido |
| | | Sincronização | O RockForge lê um início de −2,15 s (o compasso 1 começa antes da gravação), sem o pôr a 0 |
| | | Bends (Lead Guitar) | Os 18 chegam ao RockForge com a curva completa; o primeiro sobe ½ tom e volta, como no alphaTab |

O que falta nestes ficheiros é abrir no Guitar Pro 8 (ponto 2 abaixo) e testar
o PSARC no jogo (RockForge, `docs/TESTES-NO-JOGO.md`).

## Prints (OCR), verificados aqui

| Ficheiro | Data | Resultado |
|---|---|---|
| `Simple_Plan_-_Jet_Lag_Rhythm_Guitar.pdf` (print do Ultimate Guitar guardado como PDF; o conteúdo é "You're A God", Vertical Horizon) | 2026-10-01 | As 8 pautas das 3 páginas lidas com 6 cordas; 36 compassos, 234 notas; afinação Mib lida da linha "Tuning"; ~7 s no processo isolado. Título lido sem espaços ("YoureAGod"), corrigir no formulário |

## Verificado aqui, no browser

Com a aplicação a correr e o Chromium sem janela (Playwright). Sem rede, sem
som e sem diálogos do sistema, por isso não substitui o teste à mão.

- Painel do áudio: o acerto com centésimas e os botões −1 −0,1 −0,01 / +0,01 +0,1 +1, em painel estreito e largo.
- Painel do áudio: fechar com ✕ e voltar a abrir com o botão "Áudio".
- Biblioteca na pasta do disco: as músicas guardadas no browser passam para a pasta, e outro browser (outro endereço) vê as mesmas músicas.
- Exportar `.gp` com áudio: o áudio fica com o nome `backing-track.mp3` dentro do ficheiro.
- Partitura desenhada pelo alphaTab, nas vistas normal e só tab.
- Relatório da conversão: a pré-visualização em texto aparece numa tab em texto e não aparece numa tab gravada ("September").
- Novidades (0.7.0): o quadro aparece em inglês ("Version 0.7.0 · Added / Changed…") e em português, conforme o idioma.
- Prints (OCR): escolher o PDF do Ultimate Guitar e um PNG; o relatório mostra o formato "imagem (OCR)" / "image (OCR)", o aviso para conferir as notas e nenhuma pré-visualização em texto; o campo de ficheiros aceita PDF, PNG, JPEG e WebP. Sem ligações à Microsoft (telemetria do ONNX Runtime desligada).
- Idiomas: a aplicação em inglês e em português, com o "September" convertido e todas as páginas abertas — em inglês não fica texto em português (fora o nome "Português" na escolha de idioma) e o `lang` da página e o título seguem o idioma.

## Por testar à mão

| # | O quê | Como testar | O que deve acontecer |
|---|---|---|---|
| 1 | **Bends no Guitar Pro e no TuxGuitar** | Converter o PDF do "September" e abrir o GP5 | Os bends aparecem, com a mesma forma que na partitura da aplicação: o bend com release sobe, fica e volta; o bend simples sobe ao longo da nota |
| 2 | **`.gp` com áudio no Guitar Pro 8** | Converter, escolher o MP3, acertar o início e exportar `.gp` | O Guitar Pro toca o áudio e a partitura em sincronia |
| 3 | **Acerto do início com música real** | Painel do áudio, com uma música | Os botões mexem o valor em 1 s, 0,1 s e 0,01 s, e ouve-se a diferença |
| 4 | **Biblioteca noutro browser** | Abrir a aplicação no Edge e no Chrome | As mesmas músicas nos dois, vindas da pasta `~/PDF-to-GP5/Biblioteca` |
| 5 | **Capa automática** | Converter uma música com artista e título | A capa do álbum aparece na biblioteca; "Procurar capa" e "Escolher imagem" funcionam |
| 6 | **Guardar o MP3 na pasta das partituras** | Chrome/Edge: escolher os PDFs, obter o MP3 de um endereço e "Guardar o MP3 na pasta das partituras" | O diálogo abre nessa pasta com o nome preenchido |
| 7 | **URL → MP3 do YouTube** | No painel do áudio, colar um link do YouTube no campo do endereço | O MP3 é obtido; se faltar o Deno/Node.js, a página diz o que falta |
| 8 | **Pesquisa automática do vídeo** | Com a chave do YouTube configurada (`docs/CHAVE_YOUTUBE.md`) | O vídeo da música é encontrado sozinho |
| 9 | **Arranque no Windows** | `start.bat` e `start_env.bat` | A aplicação abre em `http://127.0.0.1:8021` |
| 10 | **Idioma** | Mudar para English no fundo do menu lateral e usar a aplicação (converter, tocar, áudio, biblioteca) | Tudo em inglês, incluindo os avisos da conversão, os erros e as Novidades; voltar a Português repõe tudo |
| 11 | **Novidades da 0.7.0** | Abrir a aplicação depois de atualizar | Aparece o quadro das Novidades da versão 0.7.0 uma vez; depois de fechado não volta a aparecer |
| 12 | **Prints (OCR)** | Depois do `start`, que instala o OCR (~210 MB): converter um print PNG/JPG de uma tab (Songsterr, Ultimate Guitar, Guitar Pro) e um PDF só com imagens | As notas batem com o print (conferir algumas linhas); o ritmo é aproximado; aparece o aviso. Se falhar, enviar o print |
| 13 | **Ligaduras e ghost notes** | Converter o PDF da Jet Lag e abrir no RockForge, compassos 77–90 | Cada acorde entre parêntesis toca de novo (77, 79, 81…) e só continua no compasso seguinte (78, 80, 82…); o Mi solto não soa nos compassos 79–80 |
| 14 | **Técnicas escritas em prints (OCR)** | Converter um print do Ultimate Guitar ou do Songsterr com H/P, P.M. ou let ring e abrir no leitor | As notas com "H"/"P" por cima ficam ligadas (hammer-on/pull-off) e as que estão por baixo de "P.M. - - -" / "let ring - - -" ficam com palm mute / let ring, até ao fim do tracejado. Se faltar alguma, enviar o print |
| 15 | **Slides em prints (OCR)** | Converter um print com slides (entre notas, para dentro e para fora de uma nota) e abrir no leitor | Os slides aparecem nas notas certas, com a direção certa; nenhum slide onde não há. Se faltar ou sobrar algum, enviar o print |
| 16 | **Vibrato em prints (OCR)** | Converter um print com vibratos (linha ondulada por cima das notas) e abrir no leitor | As notas por baixo da linha ondulada ficam com vibrato; nenhuma palavra por cima da pauta vira vibrato. Se faltar ou sobrar algum, enviar o print |
| 17 | **Ligaduras e arcos em prints (OCR)** | Converter um print com ligaduras (nota entre parêntesis com arco), ghost notes e legato slides, e abrir no leitor | As notas ligadas continuam (não voltam a tocar), as ghost notes ficam ghost, os slides com arco ficam legato. Se faltar ou sobrar algum, ou se "(1)" aparecer como 11, enviar o print |
| 18 | **Bends em prints (OCR)** | Converter um print com bends, bends com release e pre-bends (com "full" e "1/2") e abrir no leitor | Os bends aparecem nas notas certas, com a quantidade certa, e os releases voltam; nenhum bend onde não há. Se faltar ou sobrar algum, enviar o print |

## Confirmado por ti

| O quê | Data | Música | Notas |
|---|---|---|---|
| `.gp` com áudio no RockForge: o RockForge usa o áudio do ficheiro e as notas batem com a música, com o início antes da gravação (−2,15 s) | 2026-09-30 | Daughtry "September" (Acoustic Guitar como referência) | Precisou da correção RockForge 8b61bf0: a página de sincronização punha o início a 0, mostrava a Acoustic aos 3,20 s em vez de 1,05 s e as notas 2,15 s atrasadas |
