# PDF → GP5

[English](README.md) · **Português**

Transforme tablaturas de guitarra e baixo em PDF, ou prints de tabs, em ficheiros **Guitar Pro**. Depois
pratique-as no browser, com:

- uma partitura que toca;
- uma pista 3D ao estilo do Rocksmith;
- o áudio e o vídeo do YouTube da música em sincronia;
- loop A–B e metrónomo;
- uma biblioteca das suas músicas.

[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue)](LICENSE)
[![Última versão](https://img.shields.io/github/v/release/F100Pilot/PDF-to-GP5)](https://github.com/F100Pilot/PDF-to-GP5/releases/latest)
[![CI](https://github.com/F100Pilot/PDF-to-GP5/actions/workflows/ci.yml/badge.svg)](https://github.com/F100Pilot/PDF-to-GP5/actions/workflows/ci.yml)

[![Paga-me um café](https://img.shields.io/badge/Paga--me%20um%20caf%C3%A9-PayPal-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/F100Pilot)

![Demonstração: dois PDFs de tabs convertidos, a partitura e a pista 3D a tocar](docs/media/demo-pt.gif)

## O que faz

- **Lê tabs de várias formas**:
  - tabs em texto (`e|--0--3h5--|`);
  - PDFs exportados pelo Guitar Pro, MuseScore, TuxGuitar ou Songsterr;
  - imagens de tabs (PNG, JPEG, WebP ou PDF digitalizado), lidas por OCR no seu computador.
- **Encontra os dados da música**: título, artista, tempo, compasso, afinação, ritmo, técnicas (bends, slides, hammer-ons, vibrato, palm mute…), repetições e letra.
- **Cria ficheiros Guitar Pro**:
  - `.gp5`, ou `.gp` (Guitar Pro 7/8) com o áudio da música lá dentro;
  - até 7 tracks, de 4 a 8 cordas.
- **Corrige notas na tab**: clique num número errado e escreva o traste certo, ou apague a nota; o download e a biblioteca ficam com o ficheiro corrigido.
- **Abre ficheiros Guitar Pro** (`.gp`, `.gpx`, `.gp5`, `.gp4`, `.gp3`) para os tocar.
- **Leitor para praticar**:
  - pauta e tab, ou pista 3D;
  - velocidade;
  - loop A–B que pode acelerar a cada volta;
  - metrónomo e contagem.
- **Toca com a música verdadeira**: um ficheiro de áudio ou um vídeo do YouTube, acertado com a partitura.
- **Biblioteca** das suas músicas, com capas, que pode levar para outro computador.
- Interface em **português e inglês**.
- **Privado**: corre no seu computador, e os seus ficheiros não são enviados para lado nenhum.

## Que ficheiros funcionam melhor

| Origem | Como é lido | Resultado |
|---|---|---|
| **PDF com texto real**: uma tab em texto, ou um PDF exportado pelo Guitar Pro, MuseScore, TuxGuitar ou impresso do Songsterr | Os números, as linhas e os símbolos estão no próprio ficheiro | **O mais fiável.** Use este sempre que puder |
| **Imagem ou PDF digitalizado**: um print, uma fotografia, um "PDF" que é só uma imagem | Lido por OCR (reconhecimento de caracteres) no seu computador | **Experimental**: bom em imagens nítidas e grandes; confira sempre o resultado |

**Teste rápido:** abra o PDF e tente selecionar um número com o rato. Se conseguir, o PDF tem texto real e vai converter bem. Se a página inteira seleciona como um bloco, ou não seleciona nada, é uma imagem.

**Limitações das imagens e dos PDFs de imagem**
- **A qualidade conta.** Use a página inteira, com pelo menos 1000 px de largura, sem as barras do browser à volta. Imagens pequenas, desfocadas ou muito comprimidas (JPEG) dão números errados, notas a mais ou compassos em falta.
- **Os números podem ser mal lidos** (um 0 a negrito lido como 6 ou 9, por exemplo). O relatório avisa para os conferir, e **Corrigir notas** corrige-os na tab.
- **O ritmo** é lido das hastes, barras e pausas desenhadas quando estão nítidas; senão é estimado pelo espaçamento das notas, compasso a compasso.
- **Ainda não é lido nas imagens:** quiálteras, nomes das secções (Intro, Verse…) e tabs escritas em texto (`e|--0--3--|`) dentro de uma imagem.
- **Uma imagem é uma track.** Para juntar vários prints da mesma parte, ponha-os num só PDF.

## Ainda não suportado

Há notação que ainda não é convertida, ou é só em parte:

- **Quiálteras** (tercinas, quintinas…): são detetadas, mas o ritmo desse compasso é estimado.
- Notas de ornamento (grace notes), só em parte: lidas nos PDFs de editores e nas imagens quando o número pequeno está separado da nota; numa imagem, uma grace note impressa colada à nota sai como notas soltas.
- Swing, compassos de anacruse e armações de clave.
- Acentos, staccato, dedilhação, crescendo/decrescendo (forquilhas) e marcas de palhetada (⊓ / V).
- Trilos, tremolo picking, alavanca (dips e dives), vibrato largo, volume swell e bend + release + bend.
- Slap/pop, rasgueado e harmónicos em PDFs exportados por editores (nas tabs em texto, `<12>` funciona).
- Mudanças graduais de tempo (rit. / accel.).
- Capo, nomes e diagramas de acordes, uma segunda voz na mesma pauta e bateria.

A lista completa, técnica a técnica, está em [NOTACAO.md](docs/NOTACAO.md). Se a sua tab usa algo que falta, abra uma [issue](https://github.com/F100Pilot/PDF-to-GP5/issues) a descrever o compasso e o que devia ser.

## Começar

Precisa do **Python 3.11 ou mais recente** ([python.org](https://www.python.org/downloads/)) e do **Google Chrome** (recomendado) ou do Edge.

**Windows**

1. Descarregue a última versão em [Releases](https://github.com/F100Pilot/PDF-to-GP5/releases/latest) (*Source code (zip)*) e extraia-a.
2. Faça duplo clique em `start.bat`. Num PC de trabalho sem administrador, ou com a pasta no OneDrive, use `start_env.bat`.
3. A primeira vez instala o que é preciso, o que demora alguns minutos. Depois a aplicação abre no Chrome, em `http://127.0.0.1:8021`.

Para sair, feche a janela da aplicação.

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps --ignore-requires-python -r requirements-ocr.txt
.venv/bin/python -m app --port 8021 --close-with-browser
```

Depois abra `http://127.0.0.1:8021`.

## Documentação

| | Português | English |
|---|---|---|
| Manual do utilizador | [MANUAL.md](docs/MANUAL.md) | [MANUAL.en.md](docs/MANUAL.en.md) |
| Documentação técnica (API, configuração, segurança, desenvolvimento) | [TECNICO.md](docs/TECNICO.md) | [TECHNICAL.md](docs/TECHNICAL.md) |
| Notas e técnicas suportadas | [NOTACAO.md](docs/NOTACAO.md) | [NOTATION.md](docs/NOTATION.md) |
| Chave da API do YouTube (opcional) | [CHAVE_YOUTUBE.md](docs/CHAVE_YOUTUBE.md) | [YOUTUBE_KEY.md](docs/YOUTUBE_KEY.md) |
| Novidades | [CHANGELOG.md](CHANGELOG.md) | [CHANGELOG.en.md](CHANGELOG.en.md) |

## Apoiar o projeto

O PDF → GP5 é gratuito. Se lhe poupa tempo, pode pagar-me um café:

[![Paga-me um café](https://img.shields.io/badge/Paga--me%20um%20caf%C3%A9-PayPal-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/F100Pilot)

Erros e ideias são bem-vindos em [Issues](https://github.com/F100Pilot/PDF-to-GP5/issues). Veja o [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença e avisos

- O código está sob a [licença MIT](LICENSE). Os componentes de terceiros incluídos mantêm as suas licenças ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
- Use a aplicação só com tabs e música que tem direito a usar. Os termos do YouTube não permitem descarregar fora das funções do próprio YouTube.
- Guitar Pro é uma marca da Arobas Music e Rocksmith é uma marca da Ubisoft. Este projeto não é afiliado a nenhuma delas nem tem o seu apoio.
