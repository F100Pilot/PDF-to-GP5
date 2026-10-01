# PDF → GP5

Aplicação web que converte tablaturas em PDF (ou em imagem) para ficheiros **Guitar Pro 5** (`.gp5`).

## Formatos suportados

| Tipo de PDF | Exemplo | Suporte |
|---|---|---|
| Tab em texto (monoespaçado) | `e|--0--3h5--|` impresso de um `.txt` / site | ✅ |
| Tab gravada por editor | Exportação PDF do Guitar Pro, MuseScore, TuxGuitar | ⚠️ experimental |
| Imagem de tab gravada (OCR) | Print/screenshot PNG, JPEG ou WebP; PDF só com imagens (print guardado como PDF, digitalização) | ⚠️ experimental: só números, linhas das cordas e barras de compasso |
| Imagem de tab em texto | Print de `e|--0--3h5--|` | ❌ ainda não (sem linhas das cordas desenhadas) |

- 4–8 cordas (baixo, guitarra 6/7/8 cordas); afinação lida das etiquetas (`e B G D A D` → Drop D) ou escolhida manualmente.
- Técnicas: hammer-on/pull-off (`h`/`p`), slides (`/`, `\`, `s`), bend (`b`, `7b9`, `7b9r7`), vibrato (`~`), nota abafada (`x`), ghost note (`(5)`).
- Tabs gravadas: bends (bend, pre-bend, release, bend mantido), vibrato (linha ondulada), setas de rasgueado (brush), notas entre parêntesis (ligadura se repetem o traste da nota que soa na corda no tempo anterior e, nos PDFs do MuseScore, que desenha as ligaduras como arcos, só quando um arco chega à nota; senão ghost note), `H`/`P` sobre a pauta (hammer-on/pull-off), `let ring` e `P.M.` com linha tracejada, pausas de vários compassos (pelos números de compasso).
- Vários sistemas e páginas são concatenados numa única pista.
- Imagens (OCR): as linhas das cordas e as barras de compasso são detetadas na imagem (OpenCV) e os números lidos por um modelo de reconhecimento de texto ([RapidOCR](https://github.com/RapidAI/RapidOCR), modelos PP-OCR em ONNX Runtime, que correm no computador, sem rede: a telemetria do ONNX Runtime é desligada com `ORT_DISABLE_TELEMETRY=1`). O título, o artista, o BPM ("♩ = 97") e a afinação ("Tuning: …") são lidos do texto por cima da primeira pauta da imagem (deteção de texto do mesmo RapidOCR); num PDF cuja página 1 é uma imagem, completam o que o texto do próprio PDF não tem (num print de uma página web, o BPM só está na imagem). O compasso (os dois números grandes na pauta, no início ou numa mudança a meio) também é lido: os dígitos são lidos só como dígitos, porque o modelo, treinado sobretudo em chinês, lê um "4" grande sozinho como um carácter chinês. O ritmo desenhado com a tab ("tab com hastes": hastes, barras de colcheia e semicolcheia, meias-barras, bandeiras, pontos de aumentação e pausas na pauta) é lido como num PDF vetorial; num compasso em que as marcas não somam certo (uma quiáltera, uma pausa de outra forma), o ritmo desse compasso é estimado pelo espaçamento. Nos 13 PDFs de teste desenhados como imagem, 96,5 % dos compassos ficam com o ritmo igual ao do PDF (66 % só pelo espaçamento); num print da web de uma tab Official do Ultimate Guitar, os 24 compassos com notas usam o ritmo desenhado. As pausas são reconhecidas pelo tamanho, como o MuseScore (e os prints do Ultimate Guitar) as desenham. As técnicas (bends, slides, ligaduras) não são lidas. Uma imagem é uma track: vários prints da mesma parte juntam-se num PDF. Melhor com a página inteira a 1000 px ou mais de largura (linhas das cordas a 10 px ou mais umas das outras). Num PDF, só as páginas sem tab em texto nem gravada, mas com imagens, são lidas por OCR. Também são lidos os números de compasso e as contagens das pausas de vários compassos (para a música ter o número certo de compassos), e as notas entre parêntesis (ghost notes ou ligaduras, como num PDF). Nos 13 PDFs de teste (exportados de editores) desenhados como imagem, 99,9 % das notas são encontradas e 99,7 % ficam com o traste certo, com cerca de 4 % de notas a mais (números que não são trastes): o relatório pede para conferir. Na Jet Lag (Simple Plan) como imagem, comparada compasso a compasso com o PDF: 119 de 119 compassos iguais a 1300 px, 116 a 1600 px e 101 a 1000 px (a essa resolução, pausas desenhadas são às vezes lidas como "9"). O título, o artista e o BPM saem iguais aos do PDF em todos (a 1000, 1300, 1600 e 2600 px), e o compasso também (sem compassos a mais).

O estado detalhado de cada nota e técnica (implementado, parcial, por implementar, sem suporte em GP5) está em [`docs/NOTACAO.md`](docs/NOTACAO.md).

### Metadados

Título, artista, BPM e compasso são detetados automaticamente quando os campos ficam vazios (texto em destaque no topo da página, linhas `Title:`/`Artist:`/`Tempo:`, indicação de metrónomo `♩ = 118`, glifos de compasso, metadados do PDF). Valores preenchidos pelo utilizador têm prioridade.

### Ritmo

Se a tab gravada tiver notação rítmica (hastes, barras, pausas — "tab com hastes" do MuseScore/Guitar Pro), as durações são lidas diretamente. Compassos com tercinas, ou cuja notação não some a métrica, usam a estimativa abaixo. Sem notação, há dois modos:

- **Pelo espaçamento** (por defeito quando há barras de compasso): as posições das notas dentro de cada compasso são quantizadas para a grelha (colcheias → semicolcheias → fusas) que melhor encaixa. Durações não representáveis numa só figura são divididas com ligaduras.
- **Duração fixa**: todas as notas têm a mesma figura e os compassos são refeitos a partir da métrica.

Todos os compassos gerados somam exatamente a métrica escolhida. Reveja sempre a pré-visualização: o ritmo é uma estimativa.

## Interface

Uma página por assunto, com o menu à esquerda (em baixo, no telemóvel): **Converter** (PDFs das tracks, metadados e ritmo), **Resultado** (resumo, avisos, pré-visualização e download), **Tocar** (partitura, tab ou pista 3D, com os painéis do áudio e do vídeo ao lado), **Áudio** (escolher o áudio da música ou obtê-lo de um endereço) e **Definições** (estado do servidor e versão). Cada página tem o seu endereço (`#/converter`, `#/tocar`…): os botões recuar/avançar do browser funcionam e nada é recarregado ao mudar de página — a música continua a tocar. Fontes Sora e IBM Plex Sans incluídas em `app/static/vendor/fonts/` (SIL OFL 1.1).

- **Leitor**: barra de reprodução sempre visível em baixo, com as secções da música (Intro, Verse, Chorus…) por cima da barra de tempo — clicar numa secção salta para lá —, velocidade e **Loop A–B** (carregar no início e no fim do trecho; outra vez para desligar).
- **Biblioteca**: cada música convertida fica guardada numa pasta do computador — por defeito `PDF-to-GP5/Biblioteca` na pasta do utilizador (ex.: `C:\Users\<nome>\PDF-to-GP5\Biblioteca`), ou a indicada em `LIBRARY_DIR` — uma subpasta por música com o `.gp5` (abre no Guitar Pro), o áudio escolhido, a capa (`capa.jpg`) e `musica.json` (relatório e dados). "Tocar" reabre-a sem converter de novo, com o áudio e o acerto. Converter a mesma música outra vez substitui o GP5 (mantendo o áudio e a capa); "Remover" apaga só os ficheiros da aplicação (outros que ponha na subpasta ficam). A pasta não depende do browser nem da porta: mudar de porta, de browser ou limpar os dados do browser não perde nada. Só existe com a aplicação aberta no próprio computador (`127.0.0.1`/`localhost`); numa cópia publicada num servidor, a biblioteca fica no browser de quem a usa (IndexedDB), como antes. Músicas que estejam no browser passam sozinhas para a pasta quando a aplicação é aberta nesse endereço (para recuperar as de outra porta, abra a aplicação uma vez nessa porta: `python -m app --port 8020`). Variáveis: `LIBRARY_DIR`, `LIBRARY_MAX_AUDIO_MB` (200, áudio de uma música).
- **Capas**: ao guardar uma música na biblioteca, o servidor procura a capa do álbum pelo artista e título na pesquisa pública do iTunes (sem chave; só um resultado do mesmo artista conta, imagem JPEG/PNG até 2 MB dos servidores da Apple, guardada em cache um dia) — precisa de internet. "Procurar capa" tenta de novo e "Escolher imagem" usa uma imagem sua (JPEG, PNG ou WebP até 5 MB). A capa fica na biblioteca, com a música.
- **MP3 na pasta das partituras** (Chrome/Edge): escolhendo os PDFs pela zona "Arraste os PDFs" (clique ou arrastar), a aplicação fica a saber em que pasta estão (sem ler mais nada); depois de obter o MP3 de um endereço, "Guardar o MP3 na pasta das partituras" abre o diálogo de gravação nessa pasta e com o nome já preenchido — basta confirmar. A pasta fica lembrada na biblioteca. O browser não deixa gravar numa pasta sem esta confirmação; noutros browsers o botão é um download normal.
- **Atalhos**: Espaço tocar/pausa · ← → compasso anterior/seguinte · 1–4 vista · [ ] atrasar/adiantar a partitura 0,1 s (com áudio) · L loop A–B · **Ctrl K** (⌘K no Mac) procura páginas, músicas da biblioteca e comandos.
- **Tema**: do sistema, claro ou escuro (Definições; fica guardado no browser).
- **Idiomas** / **Languages**: português e inglês (English). A escolha fica no fundo do menu lateral e em Definições → Aparência; por defeito segue o idioma do browser. As mensagens do servidor (erros, avisos da conversão) vêm no mesmo idioma. As Novidades também: `CHANGELOG.md` (português) e `CHANGELOG.en.md` (inglês), com as mesmas entradas. Cada idioma é um dicionário `app/static/i18n-<código>.js`, com o português como chave; texto novo tem de ter tradução em todos (ver `.claude/skills/pdf-to-gp5-i18n/SKILL.md`; `tests/test_i18n.py` falha se faltar).
- **Tracks**: a ordem muda com as setas ou arrastando pela pega ⠿.

## Arranque rápido (Windows)

Dois scripts na raiz do projeto fazem `git pull`, instalam/atualizam as dependências, abrem o browser em http://127.0.0.1:8021 e iniciam o servidor (Ctrl+C para parar):

| Script | Para | Python |
|---|---|---|
| `start.bat` | PC sem restrições | Ambiente virtual em `.venv`, na pasta do projeto, criado na primeira execução |
| `start_env.bat` | PC com restrições (sem administrador, projeto no OneDrive) | Ambiente virtual em `%USERPROFILE%\venvs\pdf-to-gp5`, criado na primeira execução |

Basta fazer duplo clique no script: a aplicação abre no Chrome (no Brave o vídeo do YouTube não toca dentro da página); sem Chrome instalado, abre no browser predefinido. O Chrome abre com um perfil só da aplicação (`%LocalAppData%\PDF-to-GP5\Chrome`, numa janela à parte), onde a aceleração gráfica de que a pista 3D precisa está sempre ligada, e com `--ignore-gpu-blocklist`, para usar a placa gráfica mesmo que o Chrome a tenha na lista das que não usa (comum em portáteis). A biblioteca não muda: fica na pasta do servidor. Porta e endereço podem ser alterados nas variáveis `PORT` e `HOST` no topo de cada ficheiro.

Para parar, basta fechar a página da aplicação no browser: o servidor encerra cerca de 8 segundos depois de fechada a última página (recarregar a página não o encerra) e a janela do script fecha-se. Também se pode usar Ctrl+C na janela do script.

## Executar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8021 --workers 1
# http://localhost:8021
```

Uso pessoal no próprio PC: `python -m app --port 8021 --close-with-browser` arranca o mesmo servidor e encerra-o quando a última página da aplicação é fechada (é o que os scripts de arranque usam). Sem `--close-with-browser` (ou com `uvicorn` diretamente) o servidor só para com Ctrl+C e ignora os avisos de presença das páginas.

Usar um único worker: o rate limiting e o limite de conversões simultâneas são por processo.

## Áudio de um endereço (URL → MP3)

Em "Áudio da música" → "Obter o áudio de um endereço (URL)": o servidor obtém o áudio com o [yt-dlp](https://github.com/yt-dlp/yt-dlp) e converte-o para MP3 (128–320 kbit/s) com o FFmpeg, mostra o progresso e entrega o MP3, que fica logo a tocar com a partitura (e pode ser guardado).

- **YouTube, para uso pessoal**: o áudio de um vídeo, quando a aplicação está aberta no próprio computador onde corre (`http://127.0.0.1:8021` ou `localhost`, como abrem os scripts de arranque). "Neste computador" quer dizer as duas coisas: o pedido vem desta máquina e é feito a um endereço local — assim, uma cópia publicada na internet (mesmo atrás de um proxy na mesma máquina) não se torna um conversor do YouTube para quem a visita, e aí só aceita vídeos Creative Commons. Os termos do YouTube não permitem descarregar fora das funções do próprio YouTube: use só com música a que tem direito.
- **Outros endereços**: um ficheiro de áudio/vídeo direto, conteúdo com licença Creative Commons ou de domínio público (conforme o site indica), ou um site seu declarado em `AUDIO_DOWNLOAD_HOSTS`. O resto é recusado com o motivo. Não são usados cookies, contas nem formatos com DRM.
- **Quando falha, diz porquê**: os avisos do yt-dlp vão para o registo do servidor (nunca para a página) e a causa reconhecida aparece na página — falta o runtime JavaScript (instalar o Deno), o YouTube pediu para confirmar que não é um robô, restrição de idade, vídeo privado ou indisponível, nenhum formato de áudio (atualizar o yt-dlp). Sem o runtime ou o `yt-dlp-ejs`, um vídeo do YouTube é recusado logo ao pedir, com o que falta.
- Segurança: só `http(s)`, sem credenciais no endereço, sem endereços da rede local (exceto sites declarados); o FFmpeg corre com argumentos em lista (sem shell); limite de tamanho e de duração, tempo máximo por tarefa; uma pasta temporária por tarefa, apagada depois do download, em caso de erro ou ao fim de 15 min.
- YouTube: aceita o link (`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`) ou só o ID do vídeo. A página envia apenas o ID; o servidor volta a validá-lo (11 caracteres `A–Z a–z 0–9 _ -`) e constrói o endereço — nenhum host, caminho ou parâmetro (`list=`, `t=`) do utilizador chega ao yt-dlp. Listas de reprodução e canais são recusados.
- Dependências (instaladas pelos scripts de arranque com `requirements.txt`): `yt-dlp[default]` (inclui o `yt-dlp-ejs`, os scripts de que o YouTube precisa, usados localmente — nunca descarregados durante a execução) e `imageio-ffmpeg`, que traz o FFmpeg para Windows, macOS e Linux. Sem elas, a secção avisa que não está disponível.
- O YouTube precisa também de um runtime JavaScript instalado no PC: **Deno** (recomendado; Windows: `winget install DenoLand.Deno`) ou **Node.js** (`winget install OpenJS.NodeJS.LTS`); QuickJS e Bun também servem. A aplicação usa o que encontrar no PATH (reinicie o servidor depois de instalar). Sem nenhum, a secção avisa e os outros endereços continuam a funcionar; `/api/health` indica o estado em `audio_youtube`.
- Variáveis: `AUDIO_DOWNLOAD_HOSTS` (ex.: `musica.meusite.pt,nas.local`), `AUDIO_MAX_MB` (200), `AUDIO_MAX_DURATION_S` (1200), `AUDIO_TIMEOUT_S` (300), `AUDIO_TTL_S` (900), `AUDIO_JOBS_PER_MINUTE` (5), `AUDIO_CONCURRENT_JOBS` (1).
- API: `POST /api/audio/jobs` `{"url", "bitrate", "authorized": true}` → `{id, status, progress, message}`; `GET /api/audio/jobs/{id}` (progresso); `GET /api/audio/jobs/{id}/file` (o MP3, uma vez); `DELETE /api/audio/jobs/{id}` (cancelar).

## Repetições

Os sinais de repetição, o número de vezes ("x3"), as voltas (1.ª/2.ª vez) e os saltos D.C./D.S./To Coda/Fine passam para o ficheiro, tal como as mudanças de tempo. Para o Rocksmith, que não tem repetições, marque em Ritmo "Escrever as repetições por extenso": os compassos repetidos são copiados pela ordem em que se tocam (a escolha fica guardada no browser).

## Áudio (ficheiro .gp)

Depois de converter, pode escolher o áudio da música (mp3, ogg ou wav, até 100 MB). O áudio toca em sincronia com a partitura, a pista 3D e o vídeo (Tocar, Pausa, Parar, barra de tempo e velocidade). Os controlos (Tocar, início da música, "Marcar início", "Atrasar" / "Adiantar a partitura" — o início pode ficar antes do 0 —, "Tempo da partitura" para uma gravação que não está exatamente ao BPM do PDF, volume da música e volume das notas) ficam ao lado da partitura. Na pista 3D, a música aparece desenhada no chão, alinhada com a reprodução. O início e o tempo ficam guardados por música neste browser. Com áudio, "Descarregar" dá um ficheiro `.gp` (Guitar Pro 7/8) com o áudio como faixa de áudio e um ponto de sincronização no compasso 1 ("Marcar início" enquanto ouve o áudio na página; a sincronização pode ser afinada no Guitar Pro). Sem áudio, o download é o `.gp5` de sempre (o formato GP5 não guarda áudio). O `.gp` é criado no browser pelo alphaTab: o áudio não sai do computador. Dentro do `.gp`, o áudio fica como `Content/Assets/backing-track.mp3` (ou `.ogg`/`.wav`), com extensão como nos ficheiros do Guitar Pro e do Songsterr — o alphaTab grava-o sem extensão e há programas que assim não o encontram. Confirme que o seu conversor (por exemplo para Rocksmith) aceita `.gp`; senão use o `.gp5`.

## Letra

A letra impressa no PDF vai completa para o GP5 numa track própria, "Letra (voz)", silenciada (volume 0): uma nota por sílaba, no sítio onde a sílaba está impressa. Assim o Guitar Pro, o TuxGuitar e os conversores de GP5 para o Rocksmith (PSARC) leem a letra toda. Com 7 tracks já ocupadas, a letra vai para a track que toca em mais compassos com letra e a página avisa dos compassos que ficam sem ela.

## Partitura

Depois de converter, a página mostra a partitura do GP5 gerado (pauta e tab, só tab ou só pauta), com todas as tracks ou só as escolhidas, cada uma com a sua cor, e toca-a (tocar/pausa/parar, velocidade, silenciar tracks; clicar numa nota começa a tocar daí). Usa o [alphaTab](https://alphatab.net) 1.8.4, incluído em `app/static/vendor/alphatab/` (funciona sem internet) e carregado só quando há um resultado para mostrar. Licenças: alphaTab MPL-2.0, fonte Bravura SIL OFL 1.1, sons Sonivox Apache-2.0 (ficheiros de licença na mesma pasta). O botão "Vídeo YouTube" liga e desliga o vídeo (desligado, fica em pausa e o som da partitura volta; a escolha é lembrada). A barra de tempo por baixo dos botões mostra o tempo atual e a duração da música; clicar ou arrastar nela avança ou recua (o vídeo e a pista 3D acompanham).

**Pista 3D (Rocksmith)**: na Vista, "Pista 3D" mostra uma track como no Rocksmith — cordas nas cores do Rocksmith (Mi grave vermelho em cima), notas com o traste a chegar à linha de ataque, cordas soltas como barra, rasto nas notas longas e ligadas, quadro nos acordes, linhas de compasso e de tempo com o número do compasso e as secções, painel com o compasso atual e o progresso, câmara a seguir a zona do braço, inclinação e ângulo lateral ajustáveis, letra no topo com a sílaba atual, nome do acorde por cima do quadro (calculado pelas notas; sem nome quando não é um acorde conhecido) e brilho com o número na corda quando a nota é tocada (nas notas com bend, a nota sobe e desce na corda em tempo real, conforme o bend). Notas com cantos arredondados e o traste impresso; headstock no traste 0 (cabeça de madeira, pestana e tarrachas, com o nome de cada corda solta na cor da corda). Técnicas: bends e pre-bends (o rasto sobe com o bend — um tom chega à corda seguinte — e desce no release; seta e quantidade), slides (rasto inclinado até ao traste de destino; entrada e saída), hammer-on/pull-off (H/P, nota translúcida), palm mute (PM), harmónicos (losango), vibrato (rasto ondulado), tapping (T), ghost notes (n) e direção do rasgueado. Segue o mesmo áudio, velocidade e posição da partitura. Usa o [three.js](https://threejs.org) 0.186.1 (MIT, em `app/static/vendor/three/`) e precisa de WebGL (aceleração gráfica); sem WebGL a página avisa e mantém a partitura.

**Vídeo do YouTube ao lado**: depois de converter, a aplicação procura o vídeo da música (artista + título) e abre o painel com o primeiro resultado; os outros ficam numa lista para escolher. O vídeo escolhido e o acerto do início ficam guardados por música no browser. A pesquisa automática usa a YouTube Data API e precisa de uma chave gratuita (guia passo a passo em [`docs/CHAVE_YOUTUBE.md`](docs/CHAVE_YOUTUBE.md)):

1. Em https://console.cloud.google.com crie um projeto, ative a "YouTube Data API v3" e, em Credenciais, crie uma "Chave de API" (restrinja-a a essa API).
2. Guarde a chave na primeira linha de um ficheiro `youtube_api_key.txt` na pasta do projeto (ao lado dos scripts de arranque; o ficheiro não vai para o git) ou na variável de ambiente `YOUTUBE_API_KEY`, e reinicie o servidor.

A quota gratuita dá cerca de 100 pesquisas por dia (cada música é pesquisada uma vez por dia no máximo; o servidor guarda os resultados). Sem chave, o painel mostra "Procurar no YouTube" (abre a pesquisa já preenchida) e pode colar-se o endereço do vídeo. O início da música no vídeo acerta-se com "Marcar início" (com o vídeo a tocar, carregar no primeiro tempo do compasso 1) e afina-se com os botões ±0,1 s / ±1 s. Se o dono do vídeo não permitir vê-lo fora do YouTube, o painel diz isso (escolha outro vídeo); com a chave, a pesquisa só devolve vídeos que podem ser vistos fora do YouTube. No painel também se pode colar o endereço de outro vídeo (`youtube.com/watch?v=…`, `youtu.be/…`, `/shorts/…`; um `t=` no endereço preenche o início). O vídeo acompanha Tocar/Pausa/Parar, a posição e a velocidade da partitura, com um acerto do início da música no vídeo (em segundos, guardado por música no browser); pode silenciar-se o som da partitura para ouvir só o vídeo. Usa o leitor oficial `youtube-nocookie.com` controlado por mensagens (`postMessage`), sem scripts do YouTube na página; precisa de internet.

## API

| Método | Rota | Resposta |
|---|---|---|
| `GET` | `/api/health` | estado |
| `GET` | `/api/options` | afinações, instrumentos, limites |
| `GET` | `/api/changelog` | versões publicadas e respetivas alterações |
| `POST` | `/api/inspect` | JSON: título, artista, BPM e compasso detetados (sem converter) |
| `POST` | `/api/convert` | JSON: `filename`, `gp5_base64`, `report` (avisos, pré-visualização) |
| `POST` | `/api/convert/gp5` | ficheiro `.gp5` |

Campos (multipart):
- `file` (obrigatório; PDF, PNG, JPEG ou WebP; repetir para várias tracks, até 7, pela ordem das tracks).
- Por track (um valor por PDF, ou um só valor para todos): `track_name`, `tuning`, `instrument`.
- Da música: `title`, `artist`, `tempo` (20–400), `time_signature` (`auto` ou `N/D`, ex. `6/8`), `rhythm_mode` (`auto`/`spacing`/`fixed`), `fixed_value` (4/8/16), `parentheses` (`tie` = ligadura, `note` = nota normal).

Campos omitidos ou `auto` são detetados nos PDFs.

```bash
curl -F file=@tab.pdf -F tuning=drop_d -o tab.gp5 http://localhost:8021/api/convert/gp5
curl -F file=@guitarra.pdf -F file=@baixo.pdf -F track_name=Guitarra -F track_name=Baixo \
     -o musica.gp5 http://localhost:8021/api/convert/gp5
```

## Segurança

- A aplicação não guarda ficheiros: os PDFs e as imagens são processados em memória. Uploads acima de 1 MB são colocados pelo servidor (Starlette) num ficheiro temporário, apagado no fim do pedido.
- Validação: tamanho máximo (cabeçalho `Content-Length` **e** contagem em streaming), assinatura `%PDF-` (ou PNG/JPEG/WebP), limite de páginas, de páginas lidas por OCR, de píxeis por imagem e de notas, campos validados.
- Cada conversão corre num processo filho com **timeout** por pedido (processo morto) e **limite de memória** (`RLIMIT_AS` + `RLIMIT_CPU` em Linux/macOS; Job Object em Windows); o resultado volta em JSON (nunca `pickle`) com tamanho máximo. Número de compassos limitado.
- Concorrência limitada (HTTP 503) e rate limiting por IP (HTTP 429; IPv6 agrupado por /64), verificados antes de ler o corpo do pedido; inspeção com orçamento próprio.
- Só responde aos nomes em `ALLOWED_HOSTS` (bloqueia DNS rebinding) e recusa POST de outra origem (`Origin` diferente do `Host`).
- Cabeçalhos: CSP estrita sem scripts nem estilos inline (os dois blocos de estilo do alphaTab são autorizados pelo hash; workers só do próprio site; só o leitor youtube-nocookie.com pode ser embebido), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` na API; HSTS opcional.
- Erros internos nunca são expostos ao cliente; nomes de ficheiro e metadados GP5 são sanitizados.
- Documentação OpenAPI desativada por defeito. `pip-audit` no CI.

Atrás de um reverse proxy, o rate limiting usa o IP do proxy a menos que se configure `uvicorn --proxy-headers --forwarded-allow-ips=<ip do proxy>`.

### Configuração (variáveis de ambiente)

| Variável | Por defeito |
|---|---|
| `MAX_UPLOAD_MB` (por PDF) | 10 |
| `MAX_TOTAL_UPLOAD_MB` (todos os PDFs) | 40 |
| `MAX_PAGES` | 40 |
| `MAX_IMAGE_PAGES` (páginas lidas por OCR, por ficheiro) | 15 |
| `MAX_IMAGE_MEGAPIXELS` (por imagem) | 40 |
| `MAX_EVENTS` | 50000 |
| `CONVERSION_TIMEOUT_S` | 30 |
| `WORKER_MEMORY_MB` | 2048 (o OCR precisa de ~1,5 GB de espaço de endereços) |
| `MAX_CONCURRENT_CONVERSIONS` | 2 |
| `RATE_LIMIT_PER_MINUTE` | 20 |
| `INSPECT_RATE_LIMIT_PER_MINUTE` | 60 |
| `MAX_JOB_TIMEOUT_S` (pedido inteiro) | 90 |
| `MAX_MEASURES` | 2000 |
| `ALLOWED_HOSTS` (separados por vírgula) | `127.0.0.1,localhost,[::1]` |
| `YOUTUBE_API_KEY` (ou ficheiro `youtube_api_key.txt`) | — (pesquisa automática do vídeo desligada) |
| `VIDEO_SEARCH_PER_MINUTE` | 10 |
| `ENABLE_DOCS` | desligado |
| `ENABLE_HSTS` | desligado |

## Limitações conhecidas

- Tabs em texto com fonte proporcional desalinham as colunas; acordes podem ser separados.
- Em tabs gravadas, hastes/figuras rítmicas, técnicas desenhadas como curvas e a pauta de notação não são interpretadas.
- Em imagens (OCR): só números, linhas das cordas e barras de compasso; números que tocam na linha da corda (sem o espaço em branco que os editores deixam) ou imagens muito pequenas podem falhar. Tab em texto numa imagem ainda não é lida.
- Uma track por PDF (dentro de cada PDF, linhas com número de cordas diferente do maioritário são ignoradas, com aviso). Máximo de 7 tracks (canais MIDI da porta 1, sem o canal de percussão).
- Acordes por extenso, ritardando/accelerando ("rit.", "accel.") e, nas tabs em texto, mudanças de compasso não são convertidos. Repetições, voltas, D.C./D.S./Coda/Fine e marcas de tempo só são lidos por cima da própria tab (numa pauta com notação e tab, os sinais impressos só na notação não são lidos). O GP5 guarda cada sinal de navegação (Segno, Coda, D.S. al Coda…) uma só vez por música.

## Versões

[Semantic Versioning](https://semver.org/lang/pt-BR/): `MAJOR.MINOR.PATCH`, definida em `app/__init__.py`, visível na interface e em `/api/health`, com tag git `vX.Y.Z` por versão. Alterações em `CHANGELOG.md`.

- Cada alteração é registada em `## [Unreleased]` no `CHANGELOG.md`, sem mudar a versão.
- A versão só sobe quando várias alterações são publicadas em conjunto: a secção `[Unreleased]` passa a `[X.Y.Z] - data` e `__version__` é atualizado.
- Ao abrir a aplicação, um banner "Novidades" mostra as versões publicadas desde a última que o utilizador viu (guardada no browser); fecha-se com "Fechar". Alterações ainda não publicadas não aparecem.

## Desenvolvimento

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
.venv/bin/pytest -q
.venv/bin/pip-audit -r requirements.txt
```

Estrutura:

```
app/
  extract/        pdf_reader (chars + linhas), ascii_tab, engraved_tab
  rhythm.py       colunas → compassos com durações
  gp5_writer.py   Score → .gp5 (PyGuitarPro)
  converter.py    pipeline
  sandbox.py      processo isolado com timeout/limite de memória
  security.py     cabeçalhos, limites, rate limiting, sanitização
  main.py         API FastAPI + frontend estático
  static/         index.html, app.js, styles.css
tests/            testes unitários, API e round-trip GP5
```
