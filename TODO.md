# TODO

Ideias por fazer. Cada item diz em que projeto se faz: **PDF-to-GP5** (esta aplicação) ou **RockForge**.

## Conversão PDF → GP5 (PDF-to-GP5)

- [ ] **Nomes dos acordes** (PDF-to-GP5 + RockForge). Os símbolos por cima da tab ("Am", "G/B"…) iriam para o GP5. Os PDFs que tenho aqui (Songsterr) não têm nenhum, portanto faltam PDFs para testar. Do lado do RockForge também há trabalho: hoje descarta os nomes do GP e grava o `chordName` do Rocksmith vazio (`domain/chords.py`); os nomes que mostra são calculados a partir das notas.
- [ ] **Quintinas e septinas (5 e 7).** Hoje só as tercinas e as sextinas são exatas; as outras ficam com ritmo estimado pelo espaçamento.
- [ ] **Técnicas em falta:** tremolo picking (traços na haste), trilo (tr~~), alavanca (dip/dive) e volume swell. O RockForge já trata o tremolo e o trilo. Preciso de PDFs que as tenham.
- [ ] **rit. / accel.** como mudanças graduais de andamento.

## Ligação ao RockForge

- [x] **Comparação RockForge ↔ alphaTab:** skill `rockforge-alphatab-check`. Encontrou o let ring perdido nos `.gp` (RockForge a566e91).
- [x] **Teste de ponta a ponta até ao chart do Rocksmith:** RockForge `tests/test_gp_to_chart.py`, de GP5 até XML e SNG, verificado também com o September. Encontrou o bend comprimido quando a nota é encurtada e a curva perdida ao reler o XML (RockForge cdbdd97). Sem o jogo, que não corre aqui.
- [ ] **Bends de 3–4 pontos: seguir o alphaTab?** (RockForge, decidir com um teste no jogo). O alphaTab simplifica estes bends: "sobe até meio da nota e fica lá" passa a "sobe devagar ao longo da nota toda", e o mesmo em pre-bends e releases. O RockForge usa a curva do ficheiro, por isso o bend no Rocksmith sobe mais depressa do que no alphaTab. Seguir o alphaTab obriga a pôr um ponto do bend no início da nota, e o próprio RockForge avisa que isso é frágil no jogo.

## Aplicação (PDF-to-GP5)

- [ ] **Biblioteca: cópia de segurança.** Exportar e importar a biblioteca inteira num ficheiro, e um botão para abrir a pasta da música.
- [ ] **PDFs com linhas de número de cordas diferente** (7 cordas, baixo): hoje essas linhas são ignoradas, com aviso.
