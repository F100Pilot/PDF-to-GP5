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
| Testes (`pytest`) | `.venv/bin/python -m pytest` | 2026-09-30 | 410 passam |
| Estilo (`ruff`) | `.venv/bin/ruff check .` e `ruff format --check .` | 2026-09-30 | Sem erros |
| GP5 igual ao alphaTab | Skill `gp-alphatab-check`, nos 12 PDFs e no `September.gp` | 2026-09-30 | Tudo igual, incluindo o `.gp` exportado pelo alphaTab |
| RockForge igual ao alphaTab | Skill `rockforge-alphatab-check`, nos 12 PDFs | 2026-09-30 | Tudo igual, incluindo a forma dos bends |

PDFs usados (os teus, não guardados no repositório): Daughtry "September" (Lead
Guitar); Eagles "Hotel California" (Lead 1, 2, 3 e Pro, duas versões); Russell
Dickerson "Happen To Me" (Acoustic, Guitar 1 a 4 e Pro).

## Verificado aqui, no browser

Com a aplicação a correr e o Chromium sem janela (Playwright). Sem rede, sem
som e sem diálogos do sistema, por isso não substitui o teste à mão.

- Painel do áudio: o acerto com centésimas e os botões −1 −0,1 −0,01 / +0,01 +0,1 +1, em painel estreito e largo.
- Painel do áudio: fechar com ✕ e voltar a abrir com o botão "Áudio".
- Biblioteca na pasta do disco: as músicas guardadas no browser passam para a pasta, e outro browser (outro endereço) vê as mesmas músicas.
- Exportar `.gp` com áudio: o áudio fica com o nome `backing-track.mp3` dentro do ficheiro.
- Partitura desenhada pelo alphaTab, nas vistas normal e só tab.

## Por testar à mão

| # | O quê | Como testar | O que deve acontecer |
|---|---|---|---|
| 1 | **Bends no Guitar Pro e no TuxGuitar** | Converter o PDF do "September" e abrir o GP5 | Os bends aparecem, com a mesma forma que na partitura da aplicação: o bend com release sobe, fica e volta; o bend simples sobe ao longo da nota |
| 2 | **`.gp` com áudio no Guitar Pro 8** | Converter, escolher o MP3, acertar o início e exportar `.gp` | O Guitar Pro toca o áudio e a partitura em sincronia |
| 3 | **`.gp` com áudio no RockForge** | Importar o `.gp` do ponto 2 no RockForge | Aparece "Usar o áudio que vem dentro do ficheiro GP" e as notas batem com a música, também com um início antes do áudio (acerto negativo) |
| 4 | **Acerto do início com música real** | Painel do áudio, com uma música | Os botões mexem o valor em 1 s, 0,1 s e 0,01 s, e ouve-se a diferença |
| 5 | **Biblioteca noutro browser** | Abrir a aplicação no Edge e no Chrome | As mesmas músicas nos dois, vindas da pasta `~/PDF-to-GP5/Biblioteca` |
| 6 | **Capa automática** | Converter uma música com artista e título | A capa do álbum aparece na biblioteca; "Procurar capa" e "Escolher imagem" funcionam |
| 7 | **Guardar o MP3 na pasta das partituras** | Chrome/Edge: escolher os PDFs, obter o MP3 de um endereço e "Guardar o MP3 na pasta das partituras" | O diálogo abre nessa pasta com o nome preenchido |
| 8 | **URL → MP3 do YouTube** | No painel do áudio, colar um link do YouTube no campo do endereço | O MP3 é obtido; se faltar o Deno/Node.js, a página diz o que falta |
| 9 | **Pesquisa automática do vídeo** | Com a chave do YouTube configurada (`docs/CHAVE_YOUTUBE.md`) | O vídeo da música é encontrado sozinho |
| 10 | **Arranque no Windows** | `start-casa.bat` e `start-trabalho.bat` | A aplicação abre em `http://127.0.0.1:8021` |

## Confirmado por ti

| O quê | Data | Música | Notas |
|---|---|---|---|
| (nada registado ainda) | | | |
