# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/);
versões segundo [Semantic Versioning](https://semver.org/lang/pt-BR/).
Enquanto a versão for `0.x`, a API e as heurísticas de leitura podem mudar entre versões menores.
As alterações acumulam-se em `[Unreleased]`; a versão só sobe quando várias são publicadas em conjunto.

## [Unreleased]
### Adicionado
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
- Vídeo: quando o dono do vídeo não permite vê-lo fora do YouTube, passa sozinho ao resultado seguinte da pesquisa até encontrar um que toque (10 resultados por pesquisa).
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
- Scripts de arranque para Windows: `start-trabalho.bat` (ambiente virtual fora do OneDrive) e `start-casa.bat` (sem ambiente virtual); ambos fazem `git pull` e iniciam o servidor.
### Corrigido
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
