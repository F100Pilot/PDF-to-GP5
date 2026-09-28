# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-PT/1.1.0/);
versões segundo [Semantic Versioning](https://semver.org/lang/pt-BR/).
Enquanto a versão for `0.x`, a API e as heurísticas de leitura podem mudar entre versões menores.
As alterações acumulam-se em `[Unreleased]`; a versão só sobe quando várias são publicadas em conjunto.

## [Unreleased]
### Adicionado
- Banner "Novidades" na entrada da aplicação com as alterações das versões ainda não vistas pelo utilizador.

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
