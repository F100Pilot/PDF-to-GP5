# Registo de notação: notas e técnicas

Lista de tudo o que uma tablatura pode conter e o estado da conversão para GP5.
Serve de plano de implementação: cada música nova com notação diferente atualiza esta tabela.

## Legenda

| Estado | Significado |
|---|---|
| ✅ | Implementado e testado |
| 🟡 | Parcial (ver notas) |
| ⬜ | Por implementar |
| ⛔ | Sem equivalente no formato GP5 |

Colunas:
- **Gravada**: tab exportada de um editor (Songsterr, MuseScore, Guitar Pro, TuxGuitar…).
- **GP5**: o formato GP5 (via PyGuitarPro) consegue guardar a informação.
- **Visto em**: PDF real onde a notação já apareceu (para testes). "—" = ainda sem exemplo, **enviar PDF**.

## Como evoluir

1. Enviar um PDF que contenha a notação em falta, indicando compasso e resultado esperado (imagem de referência ajuda).
2. Analisar como o editor a desenha no PDF (texto, glifo SMuFL, linhas, curvas).
3. Implementar, com teste automático que reproduz a geometria.
4. Atualizar esta tabela e o `CHANGELOG.md`.

---

## 1. Ritmo e duração

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Duração pelo espaçamento das notas | ✅ | ✅ | Happen To Me | Estimativa quando não há notação rítmica |
| Hastes + barras (colcheia, semicolcheia, fusa) | ✅ | ✅ | Happen To Me | Barras = 1/2/3 traços |
| Bandeirola (colcheia isolada ♪) | ✅ | ✅ | Happen To Me (Guitar 2) | Glifos SMuFL `U+E240`–`E245` |
| Semínima (haste sem barra) | ✅ | ✅ | Happen To Me | |
| Mínima (haste curta) | ✅ | ✅ | Happen To Me (Guitar 2) | |
| Semibreve (sem haste) | ✅ | ✅ | Happen To Me | |
| Nota pontuada | ✅ | ✅ | Happen To Me (Guitar 2) | Glifo `U+E1E7` ou ponto desenhado |
| Nota com duplo ponto | ⬜ | ⛔ | — | GP5 só tem ponto simples |
| Tercinas e outras quiálteras (3:2, 5:4, 6:4…) | 🟡 | ✅ | — | Detetadas, mas o compasso cai para estimativa |
| Pausas (semibreve…fusa) | ✅ | ✅ | Happen To Me | Glifos `U+E4E3`–`E4E8` |
| Pausa pontuada | ✅ | ✅ | — | Implementado sem exemplo real |
| Compasso vazio (pausa de compasso) | ✅ | ✅ | Happen To Me | |
| Pausa de vários compassos (barra grossa + número) | ✅ | ✅ | Happen To Me | Pelos números de compasso |
| Ligadura de prolongamento (tie) | ✅ | ✅ | Happen To Me | |
| Nota ligada só com haste (traste oculto) | ✅ | ✅ | Happen To Me (Guitar 2) | |
| Duração fixa (tabs sem ritmo) | ✅ | ✅ | — | Opção "Duração fixa" |
| Grace note (nota de adorno) | ⬜ | ✅ | — | Com transição slide/bend/hammer |
| Swing / triplet feel | ⬜ | ✅ | — | Texto "Swing", "♪♪ = ♪³♪" |
| Anacruse (compasso incompleto no início) | ⬜ | 🟡 | — | GP5 não tem conceito próprio |

## 2. Compasso, tempo e estrutura

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Barras de compasso | ✅ | ✅ | Happen To Me | |
| Números de compasso (alinhamento entre tracks) | ✅ | — | Happen To Me | |
| Indicação de compasso (4/4, 6/8…) | ✅ | ✅ | Happen To Me | Glifos `U+E080`–`E08B` |
| Mudança de compasso a meio | ✅ | ✅ | — | Algarismos SMuFL empilhados (MuseScore); o compasso de aviso no fim da linha e o número das pausas de vários compassos são ignorados |
| Tempo inicial (♩ = 118, "Tempo: 120", "120 bpm") | ✅ | ✅ | Happen To Me | |
| Mudança de tempo a meio | ✅ | ✅ | Happen To Me (`♩ = 118` no c. 1) | "♩ = 90", "= 90", "Tempo 90", "90 bpm" por cima da tab; a marca do c. 1 é o tempo da música. Sem rit./accel. |
| Armação de clave | ⬜ | ✅ | — | |
| Repetições `‖: :‖` e "x3" | ✅ | ✅ | — | Pontos de repetição SMuFL e "x3" por cima. Sem número: 2 vezes. Opção "por extenso" (Rocksmith): compassos copiados pela ordem de reprodução |
| Casas de 1.ª/2.ª vez (voltas) | ✅ | ✅ | — | "1.", "2.", "1., 2." por cima da pauta com a linha do colchete |
| Coda, Segno, D.C., D.S., Fine | ✅ | ✅ | — | Símbolos SMuFL de Segno/Coda e texto ("D.S. al Coda", "To Coda", "Fine"…) por cima da pauta. Ordem de reprodução igual à do alphaTab; o GP5 guarda cada sinal uma vez |
| Secções (Intro, Verse, Chorus…) → marcadores | ✅ | ✅ | Happen To Me | Texto a negrito acima da pauta |

## 3. Notas

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Traste (0–29) e acordes | ✅ | ✅ | Happen To Me | |
| Nota morta `x` | ✅ | ✅ | — | |
| Nota entre parêntesis `(0)` | ✅ | ✅ | Happen To Me | Mesmo traste que a nota anterior → ligadura (sustain; no GP o traste não se repete na tab). Traste diferente → ghost note |
| Nota fantasma (ghost) | ✅ | ✅ | — | Parêntesis com traste diferente do anterior |
| Acento `>` | ⬜ | ✅ | — | |
| Acento forte `^` (marcato) | ⬜ | ✅ | — | |
| Staccato `.` | ⬜ | ✅ | — | |
| Dedilhação (mão esquerda 1–4, mão direita p-i-m-a) | ⬜ | ✅ | — | |
| Dinâmica (ppp … fff) | ✅ | ✅ | Happen To Me (`f`) | Velocidade da nota até à dinâmica seguinte; glifos SMuFL ou letras itálicas |
| Crescendo / decrescendo (hairpins) | ⬜ | ⛔ | Happen To Me | Aproximar por dinâmicas |

## 4. Técnicas da mão esquerda

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Hammer-on | ✅ `H` | ✅ | — | Letra H por cima |
| Pull-off | ✅ `P` | ✅ | Happen To Me | |
| Ligado só com arco (sem H/P) | ⬜ | ✅ | — | Arco entre notas de trastes diferentes |
| Slide legato | ✅ | ✅ | Happen To Me (Guitar 2, 3) | Linha oblíqua entre notas com arco por cima |
| Slide com ataque (shift) | ✅ | ✅ | — | Linha oblíqua entre notas sem arco |
| Slide de entrada (de baixo / de cima) | ✅ | ✅ | — | Traço curto antes da nota |
| Slide de saída (para baixo / para cima) | ✅ | ✅ | Happen To Me (Guitar 2, 3) | Traço curto depois da nota |
| Bend (½, 1, 1½, 2) | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Bend + release | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Pre-bend | ✅ | ✅ | Happen To Me (Guitar 4) | Seta reta |
| Pre-bend + release | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Bend mantido (em nota ligada) | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Bend + release + bend | ⬜ | ✅ | — | |
| Vibrato | ✅ | ✅ | Happen To Me (Guitar 4) | Linha ondulada |
| Vibrato largo (wide / de alavanca) | ⬜ | ✅ | — | Linha ondulada mais grossa |
| Trill | ⬜ | ✅ | — | |
| Tapping da mão esquerda | ⬜ | 🟡 | — | |

## 5. Técnicas da mão direita e da batida

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Palm mute (P.M.) | ✅ | ✅ | Happen To Me | "P.M." com linha tracejada |
| Let ring | ✅ | ✅ | Happen To Me | "let ring" com linha tracejada |
| Rasgueado ↑ ↓ (brush) | ✅ | ✅ | Happen To Me (Acoustic) | Seta para cima = downstroke (a confirmar em GP) |
| Palhetada para baixo ⊓ / para cima V | ⬜ | ✅ | — | |
| Tremolo picking | ⬜ | ✅ | — | Traços na haste |
| Tapping `T` | ⬜ | ✅ | — | |
| Slap `S` / Pop `P` (baixo) | ⬜ | ✅ | — | Atenção: `P` também = pull-off |
| Rasgueado flamenco (rasg.) | ⬜ | ✅ | — | |
| Arpejo (linha ondulada vertical) | ⬜ | 🟡 | — | Aproximar por brush |
| Fade in / volume swell | ⬜ | ✅ | — | |
| Alavanca (dip, dive, release) | ⬜ | ✅ | — | "w/bar" |

## 6. Harmónicos

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Natural `<12>` / N.H. | ⬜ | ✅ | — | |
| Artificial (A.H.) | ⬜ | ✅ | — | |
| Tapped (T.H.) | ⬜ | ✅ | — | |
| Pinch (P.H.) | ⬜ | ✅ | — | |
| Semi-harmónico | ⬜ | ✅ | — | |

## 7. Música, tracks e texto

| Notação | Gravada | GP5 | Visto em | Notas |
|---|---|---|---|---|
| Título, artista | ✅ | ✅ | Happen To Me | |
| Várias tracks (um PDF por track) | ✅ | ✅ | Happen To Me | Até 7 tracks |
| Nome da track / parte | ✅ | ✅ | Happen To Me | Texto do PDF ou nome do ficheiro |
| Afinação por etiquetas (`e B G D A E`) | ✅ | ✅ | — | |
| Afinação escrita ("Tuning: D A D G B E", "Drop D"…) | ✅ | ✅ | Happen To Me | Notas de grave para agudo ou nome; afinações livres com a oitava mais próxima |
| Capo ("Capo 3") | ⬜ | ✅ | — | |
| Guitarra 4–7 cordas / baixo 4–5 cordas | ✅ | ✅ | Happen To Me | |
| 8 cordas ou mais | ⛔ | ⛔ | — | GP5 guarda no máximo 7 cordas (dá erro claro) |
| Letra da música | ✅ | ✅ | Happen To Me | Track "Letra (voz)" silenciada com uma nota por sílaba, no sítio onde está impressa: letra completa no GP5 (o GP5 só tem uma track de letra). Com 7 tracks, vai para a track que toca em mais compassos com letra (aviso dos compassos sem ela). A pista 3D mostra a letra completa |
| Nomes de acordes / diagramas | ⬜ | ✅ | — | |
| Texto livre sobre notas | ⬜ | ✅ | — | |
| Segunda voz | ⬜ | ✅ | — | Hoje: uma voz por track |
| Bateria / percussão | ⬜ | ✅ | — | Fora de âmbito por agora |
| PDF digitalizado (imagem) | ⛔ | — | — | Exige OCR |

---

## Limitações conhecidas do formato GP5

- No máximo 7 cordas por track e 7 tracks nesta aplicação (canais MIDI da porta 1 sem o canal de percussão).
- Sem duplo ponto nem crescendos/decrescendos gráficos.
- Notas ligadas não guardam o traste: o leitor (Guitar Pro, TuxGuitar) deduz o traste da nota anterior.
