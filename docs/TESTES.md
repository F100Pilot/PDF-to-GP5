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
| Testes (`pytest`) | `.venv/bin/python -m pytest` | 2026-10-01, 0.7.0 + OCR | 479 passam (inclui `test_i18n.py`: nenhum texto sem tradução; `test_changelog.py`: as Novidades em inglês com as mesmas entradas; `test_raster.py`: tab em imagem PNG/JPEG/WebP, de 850 a 5000 px, recorte de uma pauta, PDF só com imagens, limites, telemetria do ONNX Runtime desligada; título, artista e BPM lidos de uma imagem; compasso 3/4, 6/8, 12/8, 4/4 e mudança a meio, de 1000 a 2600 px) |
| Estilo (`ruff`) | `.venv/bin/ruff check .` e `ruff format --check .` | 2026-10-01, 0.7.0 + OCR | Sem erros |
| OCR nos 12 PDFs desenhados como imagem | Cada página renderizada e lida por OCR, comparada nota a nota com a leitura do PDF vetorial | 2026-10-01 | 99,9 % das notas encontradas, 99,1 % com o traste certo, ~2 % de notas a mais |
| Título, artista e BPM de imagens | Página 1 dos 13 PDFs como PNG a 1000, 1300, 1600 e 2600 px, comparada com a leitura do PDF | 2026-10-01 | 52 de 52 iguais (no print do UG: "Youre A God", "Vertical Horizon", 97, Mib, 4/4 — também no PDF original, com o título e o artista em texto) |
| Compasso de imagens | Todas as páginas dos 13 PDFs como imagem, comparadas com a leitura do PDF | 2026-10-01 | 13 de 13 com o 4/4 certo, nenhum compasso a mais (antes da leitura só como dígitos: "4" lido como "L" ou como carácter chinês) |
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

## Confirmado por ti

| O quê | Data | Música | Notas |
|---|---|---|---|
| `.gp` com áudio no RockForge: o RockForge usa o áudio do ficheiro e as notas batem com a música, com o início antes da gravação (−2,15 s) | 2026-09-30 | Daughtry "September" (Acoustic Guitar como referência) | Precisou da correção RockForge 8b61bf0: a página de sincronização punha o início a 0, mostrava a Acoustic aos 3,20 s em vez de 1,05 s e as notas 2,15 s atrasadas |
