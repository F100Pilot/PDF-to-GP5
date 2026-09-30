# TODO

Ideias por fazer. Cada item diz em que projeto se faz: **PDF-to-GP5** (esta aplicação) ou **RockForge**.

## Conversão PDF → GP5 (PDF-to-GP5)

- [ ] **Nomes dos acordes.** Os símbolos por cima da tab ("Am", "G/B"…) passam a ir para o GP5. O RockForge usa esses nomes nos acordes do Rocksmith; hoje são calculados a partir das notas e podem sair diferentes do PDF.
- [ ] **Quintinas e septinas (5 e 7).** Hoje só as tercinas e as sextinas são exatas; as outras ficam com ritmo estimado pelo espaçamento.
- [ ] **Técnicas em falta:** tremolo picking (traços na haste), trilo (tr~~), alavanca (dip/dive) e volume swell. O RockForge já trata o tremolo e o trilo. Preciso de PDFs que as tenham.
- [ ] **rit. / accel.** como mudanças graduais de andamento.

## Ligação ao RockForge

- [ ] **Comparação RockForge ↔ alphaTab** (skill, como a `gp-alphatab-check`): o que o RockForge lê de um `.gp`/`.gp5` contra o que o alphaTab lê, nota a nota. Teria apanhado a perda dos bends antes de chegar ao Rocksmith.
- [ ] **Teste de ponta a ponta até ao chart do Rocksmith** (RockForge): construir o arranjo de uma música real (ex.: September) e verificar bends, ligaduras e repetições no XML/SNG final. Sem o jogo, que não corre aqui.
- [ ] **Bends de 3–4 pontos: seguir o alphaTab?** (RockForge, decidir com um teste no jogo). O alphaTab simplifica estes bends: "sobe até meio da nota e fica lá" passa a "sobe devagar ao longo da nota toda", e o mesmo em pre-bends e releases. O RockForge usa a curva do ficheiro, por isso o bend no Rocksmith sobe mais depressa do que no alphaTab. Seguir o alphaTab obriga a pôr um ponto do bend no início da nota, e o próprio RockForge avisa que isso é frágil no jogo.

## Aplicação (PDF-to-GP5)

- [ ] **Biblioteca: cópia de segurança.** Exportar e importar a biblioteca inteira num ficheiro, e um botão para abrir a pasta da música.
- [ ] **PDFs com linhas de número de cordas diferente** (7 cordas, baixo): hoje essas linhas são ignoradas, com aviso.
