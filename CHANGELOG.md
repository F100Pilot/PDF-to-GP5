# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/);
versões segundo [Semantic Versioning](https://semver.org/lang/pt-BR/).
Enquanto a versão for `0.x`, a API e as heurísticas de leitura podem mudar entre versões menores.
As alterações acumulam-se em `[Unreleased]`; a versão só sobe quando várias são publicadas em conjunto.

## [Unreleased]
### Adicionado
- Biblioteca: as músicas convertidas ficam guardadas no browser (IndexedDB) com o relatório e o áudio escolhido; "Tocar" reabre a música sem converter de novo, com o áudio e o acerto. Procura por título/artista, remoção em dois passos e espaço usado.
- Leitor: barra de reprodução fixa em baixo, com as secções da música (pela ordem em que se tocam, com repetições) por cima da barra de tempo — a atual destacada, clicar salta para lá — e Loop A–B.
- Atalhos de teclado (Espaço, ← →, 1–4, [ ], L) e Ctrl K / ⌘K para procurar páginas, músicas da biblioteca e comandos (tocar, vista, loop, tema).
- Tema do sistema, claro ou escuro, escolhido em Definições (aplicado antes de a página aparecer, sem clarão).
- Tracks: reordenar arrastando pela pega (as setas continuam, para o teclado).
- Rasgueado desenhado como linha ondulada de arpejo com seta (tabs de editor): o acorde a seguir fica com rasgueado (seta para cima = dos graves para os agudos), como já acontecia com as setas retas. O glifo rodado é colocado onde está desenhado.
- Harmónicos pinch (PH), artificiais (AH) e naturais (N.H.) nas tabs de editor: o texto por cima da pauta com traço até ao fim do intervalo marca as notas desse intervalo, também quando continua na linha seguinte; no GP5 ficam como harmónico pinch / artificial (uma oitava acima) / natural.
- Bend numa nota ligada (haste sem número, depois de uma ligadura): a curva do bend que começa nessa haste passa a dobrar a nota ligada, com o release quando a seta desce mais à frente; antes o bend perdia-se.
- Tercinas e sextinas nas tabs de editor (MuseScore): as notas por baixo de um "3" ou "6" com parêntese recto são lidas como tercina (3 no tempo de 2) e escritas como tal no GP5; antes o compasso inteiro passava a ritmo estimado pelo espaçamento. Outros números (5, 7…) continuam a dar ritmo estimado.
- Notas de passagem (grace notes) nas tabs de editor (MuseScore): os números pequenos antes de uma nota passam a nota de passagem dessa nota no GP5 (com hammer-on quando há "H"/"P"), em vez de notas normais que estragavam o ritmo do compasso; a haste cortada deixa de contar como tempo. Uma nota de passagem sem nota na mesma corda a seguir é ignorada.
- Staccato (ponto por cima da nota) nas tabs de editor.
- Crescendo e diminuendo (os "<" / ">" desenhados por baixo da pauta): o volume das notas muda gradualmente ao longo do sinal, também quando continua na linha seguinte, até à dinâmica que vem a seguir (ex.: f → ppp); sem dinâmica a seguir, sobe/desce dois níveis e fica nesse nível. No GP5 são os 8 níveis do Guitar Pro (ppp … fff).
- URL → MP3 do YouTube para uso pessoal: com a aplicação aberta no próprio computador (127.0.0.1/localhost, como abrem os scripts de arranque), o áudio de um vídeo do YouTube passa a ser obtido e convertido para MP3 — antes só vídeos Creative Commons, e a música de uma canção era sempre recusada. Pedidos de outro computador, ou por um nome público (proxy), continuam limitados ao Creative Commons.
- Quando o áudio de um endereço falha, a página diz a causa: falta o runtime JavaScript (Deno/Node.js), o YouTube pediu para confirmar que não é um robô, restrição de idade, vídeo privado ou indisponível, ou nenhum formato de áudio. Um vídeo do YouTube sem o runtime ou o `yt-dlp-ejs` é recusado logo ao pedir, com o que falta.
- Painel do áudio: ▴ colapsa-o (fica só o Tocar e o tempo; a escolha fica guardada no browser) e ✕ esconde-o, dando a largura toda à partitura; o áudio continua a tocar e o painel volta com o botão "Áudio" junto ao Tocar da partitura.
- URL → MP3, YouTube: a página envia só o ID do vídeo e o servidor valida-o e constrói o endereço (nenhum host, caminho ou parâmetro do utilizador chega ao yt-dlp); listas e canais recusados. `yt-dlp[default]` (com o `yt-dlp-ejs`, usado localmente, sem componentes remotos) e deteção do runtime JavaScript instalado (Deno, Node.js, QuickJS ou Bun), necessário para o YouTube; `/api/health` e a página indicam se falta. Os limites técnicos (listas, direto, duração) ficam separados da verificação de autorização, e o ficheiro descarregado é confirmado dentro da pasta da tarefa.
- Obter o áudio de um endereço (URL → MP3): o servidor descarrega com o yt-dlp e converte para MP3 com o FFmpeg (qualidade 128–320 kbit/s), com progresso e cancelamento; o MP3 fica logo a tocar com a partitura e pode ser guardado. Só conteúdo que pode ser descarregado (ficheiro direto, Creative Commons / domínio público, ou site próprio em `AUDIO_DOWNLOAD_HOSTS`); o resto é recusado com o motivo. Validação do endereço (só http(s), sem credenciais nem rede local), FFmpeg sem shell, limites de tamanho, duração e tempo, e pasta temporária por tarefa apagada no fim. Novas dependências: `yt-dlp` e `imageio-ffmpeg` (FFmpeg incluído).
- Partitura: só uma track de instrumento de cada vez (escolha por botão de opção), com a "Letra (voz)" opcional por baixo; a mesma track fica na pista 3D (e a letra deixa de aparecer na lista da pista 3D).
- Pista 3D: a inclinação da câmara vai até à vista de cima, na vertical (slider todo à direita), para alinhar as notas com o desenho da música no chão sem perspetiva; o ângulo lateral não se aplica nessa vista.
- O acerto do áudio fica guardado por música (artista – título) no browser: ao voltar a converter a mesma música, o início e o tempo da partitura voltam como estavam, e aparece o nome do áudio usado da última vez.
- "Tempo da partitura" no painel do áudio (±0,1 BPM, Repor): a partitura toca ao tempo da gravação quando esta não está exatamente ao BPM do PDF (o desacerto deixa de crescer ao longo da música); o vídeo e o áudio seguem-no e o .gp fica com esse tempo.
- O início da música no áudio pode ficar antes do 0 (a partitura começa antes do áudio, que espera): "Adiantar a partitura" deixa de parar no 0.
- Pista 3D: com áudio escolhido, a música aparece desenhada no chão (a intensidade ao longo do tempo), colocada com o mesmo início e tempo da reprodução, para alinhar as batidas com as notas e os tempos.
- Botões "Atrasar a partitura" / "Adiantar a partitura" (0,1 s e 1 s) nos painéis do áudio e do vídeo, em vez dos ±, com a indicação do acerto feito; funcionam a tocar.
- Controlos do áudio ao lado da partitura (na coluna do vídeo), sempre visíveis ao descer a página, com "Volume da música" e "Volume das notas" (guardados no browser); substituem a opção "Silenciar os sons da partitura" do áudio.
- Áudio da música a tocar com a partitura: Tocar (no painel do áudio ou na partitura) toca os dois, e a Pausa, o Parar, a barra de tempo e a velocidade comandam também o áudio; "Marcar início" recomeça a partitura no compasso 1 no instante marcado, com botões ±0,1 s/±1 s para afinar; opções "Tocar com a partitura" e "Silenciar os sons da partitura". Painel do áudio com o aspeto do resto da página (sem o leitor do browser).
- Ícone da aplicação no separador do browser (deixa de aparecer `GET /favicon.ico 404` no servidor).
- D.C., D.S., Segno, Coda, "To Coda" e Fine (D.C./D.S. al Coda, al Fine): lidos por cima da tab (símbolos de Segno e Coda e texto nas tabs gravadas; texto por cima da tab ou depois da linha nas tabs em texto) e escritos no GP5. A partitura, a pista 3D e a barra de tempo seguem os saltos; com "por extenso" a música fica escrita pela ordem em que se toca, com o tempo certo depois de cada salto. O resumo mostra a "Navegação".
- Mudanças de tempo a meio da música ("♩ = 90", "= 90", "Tempo 90" por cima da tab): cada uma passa para o GP5 no seu compasso (a partitura, a pista 3D, o vídeo e a barra de tempo acompanham) e aparecem no resumo. A marca do compasso 1 é o tempo da música; um tempo escolhido no formulário substitui-a.
- Opção "Escrever as repetições por extenso (para o Rocksmith, que não tem repetições)" (em Ritmo; a escolha fica guardada): o GP5/.gp fica com os compassos repetidos copiados pela ordem em que se tocam (voltas e repetições dentro de repetições incluídas, na mesma ordem que o leitor da página), sem sinais de repetição; a letra, os marcadores de secção e a pista 3D seguem cada passagem.
- Áudio da música no ficheiro Guitar Pro: depois de converter, pode escolher o mp3 (ou ogg/wav) da música; o download passa a ser um ficheiro .gp (Guitar Pro 7/8) com o áudio como faixa de áudio e o início da música marcado ("Marcar início" enquanto ouve o áudio na página). Sem áudio, o download continua a ser .gp5. O ficheiro .gp é criado no browser (com o alphaTab): o áudio não é enviado para o servidor.

### Alterado
- Interface nova, com uma página por assunto e um menu à esquerda (barra de separadores em baixo, no telemóvel): Converter, Resultado, Tocar, Áudio e Definições. Cada página tem o seu endereço (`#/tocar`…), o recuar/avançar do browser funciona e mudar de página não interrompe a música. Depois de converter abre o Resultado; "Abrir no leitor" leva à partitura. As páginas sem música mostram o que fazer. O painel de sincronização do áudio continua ao lado da partitura, a colapsar e a esconder como antes. Nova página Definições com o estado do servidor (conversão, URL → MP3, YouTube, pesquisa do vídeo) e a versão. Visual renovado (tema claro/escuro do sistema, fontes Sora e IBM Plex Sans incluídas na aplicação); o painel Novidades fica na página Converter, com altura limitada.

### Corrigido
- Compasso vazio atravessado por uma ligadura (a nota ligada não é impressa e a semibreve não tem haste): passa a ser a continuação da nota durante o compasso inteiro, em vez de pausa.
- Linha só com mínimas (hastes curtas): eram lidas como semínimas, porque a haste "normal" era medida na própria linha; o compasso ficava com ritmo estimado.
- Dinâmicas escritas com uma letra por glifo ("ppp" como três "p", "mf" como "m" + "f"): eram lidas como p e f; passam a ppp e mf.
- Pista 3D: a barra de uma corda solta (0) deixa de ocupar a janela de trastes de vários tempos (muitas vezes 5 ou mais); fica com a largura da maior posição da mão nessa janela, no mínimo 4 trastes.
- Conversão e análise do PDF falhavam ("zip() argument 2 is longer than argument 1") quando uma linha por baixo da tab só tinha marcações como "let ring" ou "PM".
- Letra: marcações "let ring", "P.M." e "palm mute" impressas na mesma linha da letra deixam de entrar na letra.

## [0.6.0] - 2026-09-29
### Adicionado
- Repetições: sinais de repetição `|: :|` (pontos de repetição nas tabs gravadas; `|:`, `:|`, `|*`, `|o` nas tabs em texto), número de vezes ("x3", "3x", "(x3)", "3 vezes"; 2 quando não está escrito) e casas de 1.ª/2.ª vez (voltas "1.", "2.", "1., 2.") passam para o GP5. Nas tabs em texto, "x4" depois de uma linha sem sinais repete a linha inteira. A partitura toca as repetições, e a pista 3D e a barra de tempo seguem a ordem em que a música é tocada (o compasso mostrado é o impresso).
- Mudanças de compasso a meio da música (ex.: um compasso em 2/4 ou uma secção em 3/4): cada compasso fica com o seu compasso no GP5, na partitura e na pista 3D; o compasso de aviso no fim da linha e o número por cima das pausas de vários compassos não contam como mudança. O resumo mostra as mudanças de compasso e o número de repetições; a pré-visualização em texto mostra `|:`, `:|x3`, `[1.]` e `[3/4]`.
- Desligar o vídeo: o botão "Vídeo YouTube" liga e desliga o vídeo. Desligado, o vídeo fica em pausa, deixa de acompanhar a partitura e o som da partitura volta (mesmo com "Silenciar os sons da partitura" marcado); a escolha fica guardada e as músicas seguintes não abrem nem pesquisam o vídeo até o voltar a ligar.
- Barra de tempo da música por baixo dos botões da partitura: tempo atual e duração ("0:42 / 3:03", tempo da música, igual a qualquer velocidade); clicar ou arrastar avança ou recua, e o vídeo e a pista 3D acompanham. Na pista 3D, a barra de progresso mostra o mesmo tempo e também se pode clicar.
- Banner "Novidades" na entrada da aplicação com as alterações das versões ainda não vistas pelo utilizador.
- Várias tracks: carregar vários PDFs (um por track, até 7) e obter um único GP5; nome, afinação e som por track, ordem ajustável; tracks mais curtas completadas com pausas (com aviso).
- Nome da track detetado no PDF ("Bass", "Electric Guitar"…) ou no nome do ficheiro ("Artista - Música - Bass.pdf" → "Bass").
- Notas entre parêntesis (ex.: `(0)`) que repetem o traste anterior são ligaduras (a nota sustenta; importadores como os do Rocksmith convertem-nas em sustain). No Guitar Pro a ligadura vê-se na pauta; o traste não é repetido na tab.
- Tracks alinhadas pelos números de compasso impressos: compassos não lidos são preenchidos com pausa no sítio certo (com aviso a indicar quais), em vez de desalinhar o resto da música.
- Setas de rasgueado (↑/↓) nas tabs gravadas convertidas em efeito de palhetada (brush) no GP5.
- Bends nas tabs gravadas: bend (seta curva), pre-bend (seta reta), release (seta descendente) e bend mantido em notas ligadas, com a quantidade indicada (½, 1, 1½, 2).
- Vibrato (linha ondulada) aplicado às notas abrangidas, incluindo notas ligadas só com haste.
- Pista 3D ao estilo Rocksmith (three.js, incluído na aplicação): uma track de cada vez, cordas nas cores do Rocksmith, notas com o traste, cordas soltas, notas longas, acordes e câmara a seguir o braço, sincronizada com a reprodução da partitura. Notas com cantos arredondados e o traste impresso na face (sem artefactos), headstock 3D com pestana, tarrachas e os nomes da afinação na cor de cada corda; brilho suave (sem clarão branco nos acordes) e nome do acorde bem acima das notas. Linhas de compasso e de tempo, número do compasso, secções, painel de progresso, inclinação e ângulo lateral da câmara, letra no topo, nome dos acordes (calculado pelas notas) e brilho com o número quando a nota chega às cordas; nos bends a nota sobe (e desce no release) em tempo real. Técnicas na pista: bends (o rasto sobe e desce como no Rocksmith), slides, hammer-on/pull-off, palm mute, harmónicos, vibrato, tapping, ghost notes e rasgueado, com legenda.
- Página em ecrã inteiro: em ecrãs largos, formulário em duas colunas, tracks lado a lado e partitura com a largura toda.
- Letra completa no GP5: track "Letra (voz)" silenciada (volume 0, som de voz), com uma nota por sílaba no sítio onde está impressa; o Guitar Pro, o TuxGuitar e os conversores para o Rocksmith (PSARC) leem a letra toda dessa track. Se já houver 7 tracks, a letra vai para a track que toca em mais compassos com letra (com aviso dos compassos que ficam sem ela). A pista 3D mostra a letra completa do PDF, no tempo certo.
- Guia para criar a chave da API do YouTube: `docs/CHAVE_YOUTUBE.md`. A chave é lida mesmo gravada com BOM ou em UTF-16 (Bloco de Notas); o servidor diz ao arrancar se a pesquisa ficou ligada ou porquê não, e o painel mostra o mesmo motivo.
- Vídeo: quando o dono do vídeo não permite vê-lo fora do YouTube, tenta também o leitor normal do YouTube e depois passa sozinho ao resultado seguinte da pesquisa até encontrar um que toque (10 resultados por pesquisa); se nenhum tocar, diz quantos foram tentados. No Brave (cujos Shields bloqueiam o leitor embutido), a mensagem diz como o desbloquear.
- Vídeo: se o leitor youtube-nocookie.com recusar a página, é usado o leitor normal do YouTube; quando o vídeo não toca, aparece "Abrir o vídeo no YouTube" (no início da música).
- Vídeo: "Marcar início" acerta o início da música no vídeo no instante em que se carrega (tempo do vídeo), botões ±0,1 s / ±1 s para afinar, mensagem clara quando o dono do vídeo não permite vê-lo fora do YouTube e pesquisa só de vídeos que podem ser vistos fora do YouTube.
- O vídeo da música é procurado automaticamente no YouTube (artista + título) e aparece no painel, com os outros resultados para escolher; precisa de uma chave da YouTube Data API (`youtube_api_key.txt` ou `YOUTUBE_API_KEY`); sem ela, ligação para a pesquisa no YouTube.
- Vídeo do YouTube num painel ao lado da partitura / pista 3D, sincronizado com Tocar, Pausa, Parar, posição e velocidade, com acerto do início e opção de silenciar os sons da partitura.
- Partitura na página depois de converter (alphaTab, incluído na aplicação): pauta e tab, só tab (com ritmo) ou só pauta; escolher as tracks visíveis; tocar, pausar, parar, velocidade e silenciar tracks.
- Cada track tem uma cor própria (1.ª azul, 2.ª laranja, 3.ª verde…), igual na aplicação e no ficheiro GP5 (Guitar Pro / TuxGuitar).
- Encerramento do servidor ao fechar a página: deixa de ficar preso em "Shutting down" quando o browser mantém ligações abertas (espera no máximo 3 s por elas e, se preciso, força a saída).
- Fechar a página da aplicação encerra o servidor local (scripts de arranque; `python -m app --close-with-browser`); recarregar a página não o encerra.
- Tabs em texto: slide de entrada (`/5`, `\5`) e de saída (`5\`, `5/`), pre-bend (`7pb9`, `7pb9r7`), harmónico natural (`<12>`), tapping (`t12`) e linhas de palm mute / let ring por cima da tab (`PM----|`, `let ring---`).
- Slides nas tabs gravadas: slide entre notas (legato com arco, shift sem arco), slide de entrada e slide de saída.
- `docs/NOTACAO.md`: registo de todas as notas e técnicas, com o estado de implementação de cada uma.
- Secções (Intro, Verse, Chorus…) convertidas em marcadores do GP5 (tabs gravadas e em texto).
- Letra da música importada para o GP5 (até 5 blocos, na track com mais notas).
- Afinação escrita no PDF ("Tuning: D A D G B E", "Drop D", "Eb standard"…) e afinações livres.
- Dinâmicas (ppp … fff) aplicadas como velocidade das notas.
- Os scripts de arranque abrem a aplicação no Chrome (no Brave o vídeo do YouTube não toca dentro da página); sem Chrome, no browser predefinido.
- Scripts de arranque para Windows: `start-trabalho.bat` (ambiente virtual fora do OneDrive) e `start-casa.bat` (sem ambiente virtual); ambos fazem `git pull` e iniciam o servidor.
### Corrigido
- Painel do vídeo: títulos longos nos resultados da pesquisa alargavam o painel para fora do ecrã; agora o painel fica na sua coluna e os títulos são cortados com "…".
- Windows: deixa de aparecer no servidor o erro `ConnectionResetError: [WinError 10054]` (`_call_connection_lost`) quando o browser fecha uma ligação; era só ruído, nada falhava.
- Depois de uma atualização, a página podia continuar a usar a versão antiga guardada no browser; os ficheiros da página passam a ser sempre revalidados.
- Tabs com mais de 7 cordas passam a dar erro claro (o formato GP5 só guarda 7 cordas; antes gerava um ficheiro inválido). Removida a afinação de 8 cordas.
- Pausas de vários compassos no início da música (a barra grossa da pausa partia a deteção da pauta e perdia-se a primeira linha).
- Ritmo: mínimas (hastes curtas), colcheias com bandeirola, notas pontuadas e hastes sem traste (continuação ligada) passam a ser lidas; símbolos musicais localizados apesar do desvio das caixas de texto da fonte.
- Setas de rasgueado deixavam de ser confundidas com barras de compasso (criavam compassos a mais).
- Segurança: limite de memória também em Windows (Job Object) e de CPU em Linux/macOS; timeout máximo por pedido; limite de compassos e de números de compasso; verificação de `Host` (`ALLOWED_HOSTS`) e de `Origin`; rate limit e concorrência verificados antes de ler o upload, com orçamento próprio para a inspeção e IPv6 agrupado por /64; falha ao arrancar o processo de conversão devolve 503.
- Interface: tamanho total dos PDFs validado antes do envio; botão Converter bloqueado durante a inspeção; nova seleção limpa o estado anterior.
### Alterado
- Porta por defeito dos scripts de arranque e da documentação passa de 8000 para 8020.
- API: `file` pode repetir-se (um por track); `track_name`, `tuning` e `instrument` aceitam um valor por PDF; o relatório tem a lista `tracks`. `/api/inspect` devolve `part_name`, `strings` e `tuning`.

## [0.5.0] - 2026-09-28
### Adicionado
- `POST /api/inspect`: deteta título, artista, BPM e compasso sem converter.
### Alterado
- Interface: ao escolher o PDF é feita logo a inspeção; a secção Metadados só aparece depois, preenchida com os valores detetados (editáveis) e o compasso detetado pré-selecionado.
- Parêntesis permitidos no nome do ficheiro descarregado.

## [0.4.0] - 2026-09-28
### Adicionado
- Ritmo lido da notação rítmica das tabs gravadas (hastes, barras de colcheia, bandeirolas, pontos, pausas); compassos cuja notação não soma a métrica são estimados pelo espaçamento, com aviso.
- Deteção automática de título, artista, BPM e compasso (texto em destaque, campos "Title:/Artist:", indicação de metrónomo, glifos de compasso, metadados do PDF).
- Versão visível na interface e em `/api/health`.
### Alterado
- API: `numerator`/`denominator` substituídos por `time_signature` (`auto` ou `N/D`); `title`, `artist` e `tempo` vazios ou omitidos significam "detetar".

## [0.3.0] - 2026-09-28
### Adicionado
- Notas entre parêntesis (ligadura ou ghost note), `H`/`P` (hammer-on/pull-off), `let ring` e `P.M.` em tabs gravadas.

## [0.2.0] - 2026-09-28
### Corrigido
- Compassos em falta em tabs gravadas: pautas sem notas, pautas curtas, linhas desenhadas por segmentos, algarismos de traste descartados, pausas de vários compassos.
- Tabs em texto: símbolos desconhecidos, espaçamento duplo, sistemas sem linha em branco.

## [0.1.0] - 2026-09-28
### Adicionado
- Primeira versão: conversão de tabs em texto e gravadas para GP5, interface web, API, isolamento do processamento.
