# PDF → GP5

Aplicação web que converte tablaturas em PDF para ficheiros **Guitar Pro 5** (`.gp5`).

## Formatos suportados

| Tipo de PDF | Exemplo | Suporte |
|---|---|---|
| Tab em texto (monoespaçado) | `e|--0--3h5--|` impresso de um `.txt` / site | ✅ |
| Tab gravada por editor | Exportação PDF do Guitar Pro, MuseScore, TuxGuitar | ⚠️ experimental |
| PDF digitalizado (imagem) | Scan / fotografia | ❌ requer OCR |

- 4–8 cordas (baixo, guitarra 6/7/8 cordas); afinação lida das etiquetas (`e B G D A D` → Drop D) ou escolhida manualmente.
- Técnicas: hammer-on/pull-off (`h`/`p`), slides (`/`, `\`, `s`), bend (`b`, `7b9`, `7b9r7`), vibrato (`~`), nota abafada (`x`), ghost note (`(5)`).
- Tabs gravadas: notas entre parêntesis (ligadura se repetem o traste anterior na corda, senão ghost note), `H`/`P` sobre a pauta (hammer-on/pull-off), `let ring` e `P.M.` com linha tracejada, pausas de vários compassos (pelos números de compasso).
- Vários sistemas e páginas são concatenados numa única pista.

### Metadados

Título, artista, BPM e compasso são detetados automaticamente quando os campos ficam vazios (texto em destaque no topo da página, linhas `Title:`/`Artist:`/`Tempo:`, indicação de metrónomo `♩ = 118`, glifos de compasso, metadados do PDF). Valores preenchidos pelo utilizador têm prioridade.

### Ritmo

Se a tab gravada tiver notação rítmica (hastes, barras, pausas — "tab com hastes" do MuseScore/Guitar Pro), as durações são lidas diretamente. Compassos com tercinas, ou cuja notação não some a métrica, usam a estimativa abaixo. Sem notação, há dois modos:

- **Pelo espaçamento** (por defeito quando há barras de compasso): as posições das notas dentro de cada compasso são quantizadas para a grelha (colcheias → semicolcheias → fusas) que melhor encaixa. Durações não representáveis numa só figura são divididas com ligaduras.
- **Duração fixa**: todas as notas têm a mesma figura e os compassos são refeitos a partir da métrica.

Todos os compassos gerados somam exatamente a métrica escolhida. Reveja sempre a pré-visualização: o ritmo é uma estimativa.

## Executar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000 --workers 1
# http://localhost:8000
```

Usar um único worker: o rate limiting e o limite de conversões simultâneas são por processo.

## API

| Método | Rota | Resposta |
|---|---|---|
| `GET` | `/api/health` | estado |
| `GET` | `/api/options` | afinações, instrumentos, limites |
| `POST` | `/api/convert` | JSON: `filename`, `gp5_base64`, `report` (avisos, pré-visualização) |
| `POST` | `/api/convert/gp5` | ficheiro `.gp5` |

Campos (multipart): `file` (obrigatório), `title`, `artist`, `tempo` (20–400), `time_signature` (`auto` ou `N/D`, ex. `6/8`), `tuning`, `instrument`, `rhythm_mode` (`auto`/`spacing`/`fixed`), `fixed_value` (4/8/16). Campos omitidos ou `auto` são detetados no PDF.

```bash
curl -F file=@tab.pdf -F tuning=drop_d -o tab.gp5 http://localhost:8000/api/convert/gp5
```

## Segurança

- Ficheiros processados só em memória; nada é gravado em disco pela aplicação.
- Validação: tamanho máximo (cabeçalho `Content-Length` **e** contagem em streaming), assinatura `%PDF-`, limite de páginas e de notas, campos validados.
- Cada conversão corre num processo filho com **timeout** (processo morto) e **limite de memória** (`RLIMIT_AS`); o resultado volta em JSON (nunca `pickle`) com tamanho máximo.
- Concorrência limitada (HTTP 503) e rate limiting por IP (HTTP 429).
- Cabeçalhos: CSP estrita sem scripts inline, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` na API; HSTS opcional.
- Erros internos nunca são expostos ao cliente; nomes de ficheiro e metadados GP5 são sanitizados.
- Documentação OpenAPI desativada por defeito. `pip-audit` no CI.

Atrás de um reverse proxy, o rate limiting usa o IP do proxy a menos que se configure `uvicorn --proxy-headers --forwarded-allow-ips=<ip do proxy>`.

### Configuração (variáveis de ambiente)

| Variável | Por defeito |
|---|---|
| `MAX_UPLOAD_MB` | 10 |
| `MAX_PAGES` | 40 |
| `MAX_EVENTS` | 50000 |
| `CONVERSION_TIMEOUT_S` | 30 |
| `WORKER_MEMORY_MB` | 1024 |
| `MAX_CONCURRENT_CONVERSIONS` | 2 |
| `RATE_LIMIT_PER_MINUTE` | 20 |
| `ENABLE_DOCS` | desligado |
| `ENABLE_HSTS` | desligado |

## Limitações conhecidas

- Tabs em texto com fonte proporcional desalinham as colunas; acordes podem ser separados.
- Em tabs gravadas, hastes/figuras rítmicas, técnicas desenhadas como curvas e a pauta de notação não são interpretadas.
- Uma única pista por ficheiro (sistemas com número de cordas diferente do maioritário são ignorados, com aviso).
- Repetições, letras, acordes por extenso e marcações de palm-mute não são convertidos.

## Versões

[Semantic Versioning](https://semver.org/lang/pt-BR/): `MAJOR.MINOR.PATCH`, definida em `app/__init__.py`, visível na interface e em `/api/health`, com tag git `vX.Y.Z` por versão. Alterações em `CHANGELOG.md`.

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
