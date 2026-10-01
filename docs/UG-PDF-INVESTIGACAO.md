# Ultimate Guitar → PDF vetorial: investigação (fase 1)

Pedido: a partir de um endereço de uma tab da Ultimate Guitar (UG), gerar um PDF
vetorial igual ao que a app Android da UG exporta. Tab de referência: Simple Plan,
"Jet Lag", Official, id 2157405. PDF de referência: `Simple Plan - Jet Lag - Pro.pdf`
(exportado pelo utilizador na app Android).

Este documento é só a investigação: nada foi implementado. Cada afirmação está
marcada **CONFIRMADO** (medido ou visto numa fonte que foi aberta), **PROVÁVEL**
ou **DESCONHECIDO**. As medições podem ser repetidas com
`tools/ug_pdf_inspect.py` (precisa de `pikepdf pymupdf fonttools`).

## 1. Conclusões

1. **O PDF é desenhado pelo motor de gravação do MuseScore, com um escritor de
   PDF próprio da UG.** PROVÁVEL, com muitas provas concordantes (secção 3): as
   unidades são as internas do MuseScore (360 por polegada), os tamanhos e
   espessuras são os valores por defeito do MuseScore escritos nessas unidades, e
   as fontes são as do MuseScore 4. A UG e o MuseScore são da mesma empresa (Muse
   Group, CONFIRMADO por fontes públicas). O escritor de PDF não é o do MuseScore
   (Qt) nem o Skia: deixa a pilha `q`/`Q` desequilibrada e a página com 5 vezes o
   tamanho A4.
2. **A tab Official não tem uma fonte de dados pública e documentada.**
   CONFIRMADO que não foi encontrada nenhuma. As tabs Official são conteúdo Pro
   (pago), segundo as páginas de ajuda da UG (PROVÁVEL: só vistas em excertos de
   pesquisa). O único caminho conhecido para dados estruturados é a API privada da
   app móvel. Essa API exige cabeçalhos de assinatura copiados da app
   (`X-UG-API-KEY` = md5(id do dispositivo + data/hora + segredo)), ou seja, fazer
   de conta que se é a app. Isso choca com as regras do projeto: sem contornar
   autenticação, sem login nem cookies.
3. **Daqui não foi possível testar a página da tab 2157405.** A política de rede
   deste ambiente recusa `tabs.ultimate-guitar.com` e `api.ultimate-guitar.com`
   (o proxy responde 403). O que a página pública expõe sem login é, por isso,
   DESCONHECIDO.
4. **Para desenhar o PDF, o candidato mais forte é o próprio MuseScore 4**:
   código aberto, corre em Windows e exporta PDF por linha de comando, com as
   mesmas fontes (Leland, Edwin) e as mesmas regras de gravação. Falta a entrada
   de dados: o MuseScore lê Guitar Pro e MusicXML, não endereços da UG.

## 2. O PDF de referência (medido)

Ficheiro: `Simple Plan - Jet Lag - Pro.pdf`. O "Rhythm Guitar" que já tínhamos da
mesma música tem o mesmo texto e o mesmo número de desenhos em todas as páginas
(CONFIRMADO): é outra exportação do mesmo conteúdo.

| Propriedade | Valor | |
|---|---|---|
| Versão | PDF 1.7, sem encriptação | CONFIRMADO |
| Páginas | 4 | CONFIRMADO |
| Tamanho da página | 2976 × 4209 pt (1050 × 1485 mm), exatamente A4 × 5 | CONFIRMADO |
| Info / metadados | Dicionário Info vazio, sem XMP; o catálogo só tem `/Type` e `/Pages` (sem Producer nem Creator) | CONFIRMADO |
| Imagens / XObjects | Nenhum: tudo é texto e caminhos vetoriais | CONFIRMADO |
| Cor | Só preto (`0 0 0 rg`); nenhum retângulo branco atrás dos números (as linhas da tab são desenhadas em segmentos, com o espaço deixado) | CONFIRMADO |
| Operadores (4 páginas) | `l` 8791, `m` 5202, `rg` 4537, `Tj`/`Td` 3639, `BT`/`Tm`/`ET` 2510, `h` 2251, `w` 1711, `S` 1531, `q` 510, `Q` 396, `c` 360, `f` 316, `Tf` 164, `W*`/`n` 114 | CONFIRMADO |
| Texto | Cada carácter é desenhado à parte (`Tj` de um carácter e `Td` com o avanço); cada bloco tem `BT … Tm … ET` próprio | CONFIRMADO |
| Pilha gráfica | `q`/`Q` desequilibrados: ficam 30, 34, 39 e 11 níveis abertos no fim das páginas | CONFIRMADO |
| Espessuras de linha | 1.5 (702), 2.5 (652), 1.25 (180), 3.75 (132), 2.75, 3.25, 5, 12.5, 17.5 | CONFIRMADO |
| Margens (pág. 1) | Pauta de x = 200 a 2776; conteúdo de y = 198 a 4173 (a contar de cima) | CONFIRMADO |
| Sistemas por página | 7, 8, 8, 2; compassos por sistema: 7,4,4,4,4,4,4 / 5,5,4,4,4,4,4,4 / 5,7,7,6,4,4,4,4 / 5,7 (119 compassos) | CONFIRMADO |
| Pautas | Só tablatura (6 cordas), com o ritmo desenhado por baixo; sem pauta de notação padrão | CONFIRMADO |

### Fontes

Todas são subconjuntos embebidos, com etiquetas sequenciais `AAAAAB+` a `AAAAAH+`,
e todas têm `/ToUnicode`. As fontes musicais usam códigos SMuFL (zona de uso
privado U+E000–U+F8FF).

| Fonte | Tipo no PDF | Glifos no subconjunto | Tamanhos | O que desenha |
|---|---|---|---|---|
| Edwin-Roman | Type1 / CFF (FontFile3 Type1C), WinAnsi | 47 | 90, 54, 40, 37.5 | título (90), artista (54), letra (40) |
| Edwin-Italic | Type1 / CFF, WinAnsi | 11 | 30 | números de compasso |
| Edwin-Bold | Type1 / CFF, WinAnsi | 22 | 45, 50 | secções (Intro, Verse 1…), contagem das pausas de vários compassos, "= 145" |
| Leland | Type1 / CFF, codificação própria | 14 | 100, 85 | clave TAB U+E06D; dígitos de compasso U+E083/E084; ponto U+E1E7; colcheia U+E241; pausas U+E4E4–E4E6; acentos U+E4A0/E4AC; dinâmicas *m*/*f* U+E521/E522; arcada para baixo U+E610 |
| LelandText | Type1 / CFF | 2 | 100 | semínima da marca de tempo U+ECA5 |
| Bravura | Type1 / CFF | 2 | 100 | um só glifo, U+E843 (o "<" sobre o compasso 4, zona de técnicas de guitarra do SMuFL) |
| Roboto-Regular | TrueType (FontFile2), WinAnsi | 30 | 45 | os 1826 números de traste |

- A notação usa glifos SMuFL. CONFIRMADO.
- O Bravura entra só para um símbolo que o Leland não tem. PROVÁVEL (o MuseScore
  usa o Bravura como fonte de recurso).
- As hastes, as barras de colcheias (`f`), as linhas da pauta e as barras de
  compasso são caminhos. As ligaduras e os arcos são curvas (`c`). CONFIRMADO.

## 3. Como o PDF é gerado

| Indício | Medido | Valor por defeito do MuseScore nas unidades de 360/pol. | |
|---|---|---|---|
| Unidades | Página = A4 × 5 | O MuseScore trabalha a 360 pontos por polegada (72 × 5) | PROVÁVEL |
| Fonte musical | Leland a 100 | 20 pt × 5 = 100 | PROVÁVEL |
| Distância entre linhas da tab | ~37,5 | 1,5 espaços de 25 (espaço de 1,764 mm) | PROVÁVEL |
| Espessuras | 1.25 / 1.5 / 2.5 / 2.75 / 3.75 | 0,05 / 0,06 / 0,1 / 0,11 / 0,15 espaços | PROVÁVEL |
| Fontes | Edwin (texto), Leland (música), LelandText (texto musical), Bravura (recurso) | Fontes por defeito do MuseScore 4 | CONFIRMADO que são essas; PROVÁVEL que venham do MuseScore |
| Fonte dos trastes | Roboto | Diferente do MuseScore por defeito: estilo próprio da UG | PROVÁVEL |
| Ordem de desenho | O texto sai agrupado por tipo de elemento, não pela ordem de leitura (os números de compasso saem 23, 15, 1, 8…) | Pintura por elemento | PROVÁVEL |
| Escritor de PDF | `q`/`Q` desequilibrados, um `Tj` por carácter, página não convertida para pontos, sem Producer | Não é o Qt nem o Skia (equilibram sempre a pilha e escrevem o Producer) | PROVÁVEL: escritor próprio da UG |

Hipótese mais provável: a app da UG faz a gravação com o motor do MuseScore (Muse
Group) e passa os desenhos a um escritor de PDF próprio, sem converter as unidades.
DESCONHECIDO:
- se a gravação é feita no telemóvel ou num servidor;
- em que formato a app recebe a tab (o mais provável é um ficheiro do MuseScore
  ou do Guitar Pro, mas não há prova).

Todos os PDFs Pro que o utilizador já enviou (September, Hotel California, Happen
To Me) têm a mesma assinatura: PDF 1.7, A4 × 5, Info vazio, as mesmas fontes
(CONFIRMADO). O gerador é o mesmo.

## 4. Os dados da UG

| Pergunta | Resposta | |
|---|---|---|
| A página pública da tab 2157405 tem os dados da tab? | Não testado: o acesso a `tabs.ultimate-guitar.com` está bloqueado neste ambiente | DESCONHECIDO |
| As páginas da UG têm JSON embebido? | Sim: `.js-store` com `data-content` → `store.page.data.tab` e `tab_view` (`meta`, `wiki_tab.content`). Visto no código do UltimateGuitar2Bandhelper, para tabs de texto/acordes | CONFIRMADO para tabs de texto; DESCONHECIDO para Official |
| As Official têm a notação na página pública? | Sem prova num sentido nem noutro | DESCONHECIDO |
| As Official são pagas? | "Available for Pro users only" e "can be printed", segundo as páginas de ajuda da UG | PROVÁVEL (só excertos de pesquisa; a página está bloqueada aqui) |
| A app recebe outro formato? | A API móvel (`api.ultimate-guitar.com/api/v1`, `GET /tab/info?tab_id=…`) devolve `content` como texto | CONFIRMADO no código do Pilfer/ultimate-guitar-scraper; DESCONHECIDO para Official |
| Acesso à API móvel | Exige `X-UG-CLIENT-ID` e `X-UG-API-KEY`, uma assinatura calculada como a app calcula (obtida por engenharia inversa da app) | CONFIRMADO no código do Pilfer. Usar isto é fazer-se passar pela app: fora das regras do projeto |
| Tabdown | Linguagem aberta da UG para tabs de **texto** e acordes (extensão do Markdown). Só tem documentação, não tem notação | CONFIRMADO (github.com/ultimate-guitar/Tabdown) |
| O PDF é gerado no servidor ou na app? | Sem prova | DESCONHECIDO |
| Termos de utilização | A página está bloqueada aqui; o texto não foi lido | DESCONHECIDO |

Projetos públicos:
- **Pilfer/ultimate-guitar-scraper**: API móvel com assinatura copiada da app.
  Não trata a notação das Official; o autor diz que é "puramente educativo".
- **codekoch/UltimateGuitar2Bandhelper**: a versão atual não faz pedidos à UG. Lê
  PDFs, HTML gravado ou texto que o utilizador fornece, e só trata acordes. A v1
  usava a API interna e o autor diz que "funciona mal".
- **noahmaranesi/Ultimate-Guitar-Hack**: diz descarregar ficheiros Guitar Pro das
  Official mexendo no HTML. É um contorno do controlo de acesso: excluído.

## 5. Modelo de dados necessário (derivado do PDF)

O que a gravação de referência mostra, e por isso o que os dados têm de trazer
(CONFIRMADO no PDF):

- Música: título, artista, afinação (texto "Tuning : E A D G B E"), tempo (♩ = 145).
- Compassos (119): número; compasso (4/4); pausas de vários compassos com contagem;
  barras duplas; mudanças de linha e de página.
- Por compasso, os tempos: duração (colcheias, semínimas, pontos, pausas, barras
  de ligação), as notas (corda, traste), ligaduras e arcos, notas entre parêntesis
  (ghost/ligadas), acentos, arcada, palm mute (com linha), dinâmicas (*mf*, *f*),
  o "<" do compasso 4.
- Texto: secções (Intro, Verse 1, Pre-Chorus, Chorus, Break…), letra por sílaba
  com hífenes.
- Apresentação: 6 cordas, só tablatura com ritmo, A4, margens, sistemas por
  página. O estilo é da UG (trastes em Roboto 45).

O formato do Guitar Pro e o MusicXML cobrem tudo isto. O GP5 que o PDF-to-GP5 já
escreve cobre tudo, menos a apresentação (quebras de linha e de página).

## 6. Motores de gravação

| Motor | Tablatura + ritmo | Fontes SMuFL / mesmo aspeto | PDF vetorial | Windows | Entrada | Avaliação |
|---|---|---|---|---|---|---|
| **MuseScore 4** (CLI `MuseScore4.exe -o saida.pdf entrada`) | Sim | **O mesmo motor e as mesmas fontes** (PROVÁVEL) | Sim | Sim | .gp/.gp5/.gpx, MusicXML, .mscz | **Recomendado**. A paginação depende do estilo (`.mss`); o comportamento sem janela não foi testado aqui |
| Verovio | Sim (tab desde a versão 3/4) | SMuFL (Leland, Bravura) | SVG; PDF por conversão | Sim (Python/JS) | MEI, MusicXML | Alternativa leve. O aspeto e a paginação são diferentes |
| alphaTab (já está na app) | Sim | Bravura | SVG/Canvas; PDF por conversão | Sim (browser) | GP/GP5, MusicXML | Diferente do MuseScore. Já dá a pré-visualização na app |
| LilyPond | Sim | Fontes próprias (Emmentaler) | Sim | Sim | Ficheiro .ly | Aspeto muito diferente |
| VexFlow / OSMD | Parcial | SMuFL | SVG | Browser | MusicXML | Mais trabalho para chegar ao mesmo resultado |
| Escritor de PDF próprio | — | — | — | — | — | Reescrever a gravação: um trabalho enorme |

O MuseScore e o Verovio não foram executados aqui: os downloads do GitHub estão
bloqueados neste ambiente (o PyPI funciona; o Verovio tem pacote Python).

## 7. Arquitetura proposta

```
[entrada legítima]                [dados]                       [gravação]               [comparação]
PDF exportado da app ─┐
ficheiro .gp/.gp5 ────┼─→ modelo da música (GP5/MusicXML) ─→ MuseScore 4 CLI + estilo UG (.mss) ─→ PDF ─→ diff com a referência
(endereço da UG: só se houver uma via legítima — §4)
```

1. **Entrada**: o endereço só é viável se a página pública expuser os dados sem
   login (por verificar, §8). As entradas legítimas já disponíveis são:
   - o PDF exportado pela app, que o PDF-to-GP5 já lê com alta fidelidade;
   - um ficheiro Guitar Pro que o utilizador tenha.
2. **Modelo**: GP5/MusicXML, que o PDF-to-GP5 já produz.
3. **Gravação**: MuseScore 4 por linha de comando, com um estilo afinado para
   imitar o da UG (trastes em Roboto, tamanhos de texto, margens, distância entre
   pautas).
4. **Comparação**: estende-se `tools/ug_pdf_inspect.py` para comparar
   referência e resultado (páginas, caixas de texto, fontes, contagens de
   objetos), mais páginas renderizadas lado a lado e a diferença em imagem.

## 8. Riscos e incógnitas

- **Dados (bloqueante)**: sem uma via legítima para os dados das Official, o
  "endereço → PDF" não é possível dentro das regras do projeto. A app já exporta
  este PDF ao utilizador, que é Pro.
- **Termos da UG**: não foram lidos (página bloqueada). É preciso lê-los antes de
  qualquer acesso automático, mesmo a páginas públicas.
- **Fidelidade**: o mesmo motor não garante a mesma paginação. O estilo da UG e a
  versão do motor que a app usa são desconhecidos.
- **Licença**: o MuseScore é GPL. Usá-lo como programa externo não obriga a
  mudar a licença do projeto, mas não se pode embutir o código dele noutra licença.
- **Ambiente**: para testar a página pública e o MuseScore aqui, é preciso abrir
  na rede do ambiente `tabs.ultimate-guitar.com` e os downloads do GitHub (ou
  testar no PC do utilizador).

## 9. Plano e testes

1. Verificar o que a página pública da tab 2157405 tem sem login (`.js-store`),
   com a rede aberta para esse domínio. Sem notação lá, a entrada fica pelos
   ficheiros do utilizador.
2. Protótipo: o GP5 da Jet Lag (já sai do PDF de referência) → MuseScore 4 CLI →
   PDF da 1.ª linha. Comparar com a página 1 da referência.
3. Estilo UG (.mss) até a 1.ª página coincidir (sistemas, compassos por linha,
   tamanhos). Depois a música toda (4 páginas).
4. Testes:
   - a mesma contagem de páginas, sistemas e compassos por linha;
   - o texto extraído igual (título, letra, secções, números de compasso);
   - as mesmas fontes e tamanhos;
   - a diferença em imagem abaixo de um limite por página;
   - o PDF gerado sem imagens raster.
