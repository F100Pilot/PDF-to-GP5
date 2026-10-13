# Contributing · Contribuir

**English** — Bug reports, ideas and pull requests are welcome.

- **Bugs**: open an [issue](https://github.com/F100Pilot/PDF-to-GP5/issues/new/choose) with the app version (Settings → About), your browser and what you did. Only attach a PDF or picture if you have the right to share it. Otherwise, describe it: the editor or site it came from, and what went wrong.
- **Code**: keep each change small and covered by tests. Before opening a pull request, run:
  ```bash
  .venv/bin/pip install -r requirements-dev.txt
  .venv/bin/pip install --no-deps --ignore-requires-python -r requirements-ocr.txt
  .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
  .venv/bin/pytest -q
  ```
- **Two languages**: the app is in Portuguese and English. Every text a user can see, every server message and every CHANGELOG entry ships in both (`app/static/i18n-en.js`, `CHANGELOG.md` + `CHANGELOG.en.md`; `tests/test_i18n.py` checks it). Details in `.claude/skills/pdf-to-gp5-i18n/SKILL.md`.
- **Security**: strict CSP. Scripts are local files listed in `index.html`, with no inline scripts or styles. Report vulnerabilities as described in [SECURITY.md](SECURITY.md).
- By contributing, you agree that your contribution is licensed under the [MIT licence](LICENSE).

**Português** — Relatos de erros, ideias e pull requests são bem-vindos.

- **Erros**: abra uma [issue](https://github.com/F100Pilot/PDF-to-GP5/issues/new/choose) com a versão da aplicação (Definições → Sobre), o browser e o que fez. Só anexe um PDF ou uma imagem se tiver o direito de os partilhar. Caso contrário, descreva-os: o editor ou site de onde vieram e o que correu mal.
- **Código**: alterações pequenas e com testes. Antes de abrir um pull request, corra os comandos acima.
- **Duas línguas**: a aplicação está em português e em inglês. Todo o texto visível, as mensagens do servidor e as entradas do CHANGELOG vão nas duas (`app/static/i18n-en.js`, `CHANGELOG.md` + `CHANGELOG.en.md`; o `tests/test_i18n.py` verifica). Detalhes em `.claude/skills/pdf-to-gp5-i18n/SKILL.md`.
- **Segurança**: CSP estrita. Os scripts são ficheiros locais listados no `index.html`, sem scripts nem estilos inline. Vulnerabilidades: veja o [SECURITY.md](SECURITY.md).
- Ao contribuir, aceita que a sua contribuição fica sob a [licença MIT](LICENSE).
