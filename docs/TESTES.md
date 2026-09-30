# Testes

O que é testado nesta aplicação, o que já foi verificado e o que ainda falta
testar à mão. Atualizar depois de cada teste: passar de "Por testar" para
"Confirmado", com a data e a música.

Os testes no Rocksmith (o PSARC que o RockForge cria a partir do GP) estão no
RockForge, em `docs/TESTES-NO-JOGO.md`.

## Automáticos

Correm na sessão do Claude, sem ninguém a ver, e não precisam de rede.

| O quê | Como | Última vez | Resultado |
|---|---|---|---|
| Testes (`pytest`) | `.venv/bin/python -m pytest` | 2026-09-30 | 445 passam (inclui `test_i18n.py`: nenhum texto sem tradução) |
| Estilo (`ruff`) | `.venv/bin/ruff check .` e `ruff format --check .` | 2026-09-30 | Sem erros |
| GP5 igual ao alphaTab | Skill `gp-alphatab-check`, nos 12 PDFs e no `September.gp` | 2026-09-30 | Tudo igual, incluindo o `.gp` exportado pelo alphaTab |
| RockForge igual ao alphaTab | Skill `rockforge-alphatab-check`, nos 12 PDFs | 2026-09-30 | Tudo igual, incluindo a forma dos bends |

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

## Verificado aqui, no browser

Com a aplicação a correr e o Chromium sem janela (Playwright). Sem rede, sem
som e sem diálogos do sistema, por isso não substitui o teste à mão.

- Painel do áudio: o acerto com centésimas e os botões −1 −0,1 −0,01 / +0,01 +0,1 +1, em painel estreito e largo.
- Painel do áudio: fechar com ✕ e voltar a abrir com o botão "Áudio".
- Biblioteca na pasta do disco: as músicas guardadas no browser passam para a pasta, e outro browser (outro endereço) vê as mesmas músicas.
- Exportar `.gp` com áudio: o áudio fica com o nome `backing-track.mp3` dentro do ficheiro.
- Partitura desenhada pelo alphaTab, nas vistas normal e só tab.
- Relatório da conversão: a pré-visualização em texto aparece numa tab em texto e não aparece numa tab gravada ("September").
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
| 9 | **Arranque no Windows** | `start-casa.bat` e `start-trabalho.bat` | A aplicação abre em `http://127.0.0.1:8021` |
| 10 | **Idioma** | Mudar para English no fundo do menu lateral e usar a aplicação (converter, tocar, áudio, biblioteca) | Tudo em inglês, incluindo os avisos da conversão e os erros; voltar a Português repõe tudo |

## Confirmado por ti

| O quê | Data | Música | Notas |
|---|---|---|---|
| `.gp` com áudio no RockForge: o RockForge usa o áudio do ficheiro e as notas batem com a música, com o início antes da gravação (−2,15 s) | 2026-09-30 | Daughtry "September" (Acoustic Guitar como referência) | Precisou da correção RockForge 8b61bf0: a página de sincronização punha o início a 0, mostrava a Acoustic aos 3,20 s em vez de 1,05 s e as notas 2,15 s atrasadas |
