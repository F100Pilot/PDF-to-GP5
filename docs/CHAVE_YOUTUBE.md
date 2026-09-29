# Criar a chave da API do YouTube (pesquisa automática do vídeo)

A aplicação só precisa desta chave para **encontrar sozinha** o vídeo da música no YouTube.
Sem ela, tudo o resto funciona e pode colar o endereço do vídeo à mão.

É gratuita e não pede cartão de crédito. Use uma conta Google pessoal (Gmail): contas da empresa
podem ter a Google Cloud bloqueada.

## 1. Criar um projeto

1. Abra https://console.cloud.google.com e entre com a sua conta Google.
   Na primeira vez, aceite os termos de serviço.
2. No topo da página, clique no seletor de projetos (ao lado de "Google Cloud") e depois em
   **Novo projeto**.
3. Nome: `PDF-to-GP5` (qualquer nome serve). Clique em **Criar** e espere uns segundos.
4. Confirme que o seletor de projetos, no topo, mostra o projeto novo.

## 2. Ativar a YouTube Data API v3

1. Abra https://console.cloud.google.com/apis/library/youtube.googleapis.com
   (ou menu ☰ → **APIs e serviços** → **Biblioteca** → pesquise "YouTube Data API v3").
2. Clique em **Ativar**.

## 3. Criar a chave

1. Menu ☰ → **APIs e serviços** → **Credenciais**
   (https://console.cloud.google.com/apis/credentials).
2. **+ Criar credenciais** → **Chave de API**. Aparece a chave (começa por `AIza…`).
   Clique no ícone de copiar.
3. Recomendado: clique em **Editar chave de API** (ou no nome da chave) → em
   **Restrições de API** escolha **Restringir chave** → marque só **YouTube Data API v3** →
   **Guardar**. Assim, se a chave for vista por alguém, só serve para pesquisar no YouTube.

## 4. Pôr a chave na aplicação

A chave fica num ficheiro de texto na pasta do projeto (a mesma dos `start-*.bat`).
Esse ficheiro **não vai para o git** (está no `.gitignore`).

**Com o Bloco de Notas**
1. Abra o Bloco de Notas e cole a chave (só a chave, numa linha).
2. **Ficheiro → Guardar como…**, vá à pasta do projeto, por exemplo
   `C:\Users\<utilizador>\…\PDF-to-GP5`.
3. Em **Tipo**, escolha **Todos os ficheiros (\*.\*)** e em **Nome** escreva
   `youtube_api_key.txt`. Guardar.
   (Sem "Todos os ficheiros", o Windows grava `youtube_api_key.txt.txt` e a aplicação não o encontra.)

**Ou numa janela de comandos** (na pasta do projeto; troque `AIza...` pela sua chave, sem espaço antes de `>`):

```bat
echo AIza...> youtube_api_key.txt
```

## 5. Reiniciar

Feche a página da aplicação (o servidor fecha sozinho) e volte a correr o `start-*.bat`.
Depois de converter uma música, o painel do vídeo abre sozinho com o vídeo encontrado.

## Confirmar que ficou ligada

Ao arrancar, a janela do servidor mostra uma destas linhas:

- `Vídeo do YouTube: pesquisa automática ligada.` — está tudo certo.
- `Vídeo do YouTube: pesquisa automática desligada (…)` — entre parênteses está o motivo
  (ficheiro não encontrado, vazio, ou a primeira linha não é uma chave). O painel do vídeo mostra o
  mesmo motivo. O Bloco de Notas pode gravar em UTF-8, UTF-8 com BOM ou "Unicode": todos servem.

## O vídeo aparece como "não disponível"

- Se o dono do vídeo não permitir vê-lo fora do YouTube, a aplicação passa sozinha ao resultado
  seguinte da pesquisa. Se nenhum tocar, aparece "O dono do vídeo não permite vê-lo fora do YouTube":
  escolha outro vídeo na lista, cole outro endereço ou use "Abrir o vídeo no YouTube".
- Se acontecer com todos os vídeos, é o browser a bloquear o leitor do YouTube dentro da página.
  Acontece no **Brave** (no Chrome e no Edge funciona): desligue os Shields para `127.0.0.1`
  (ícone do leão na barra de endereço → Shields em baixo) e recarregue a página, ou use o
  Chrome/Edge. No Brave a própria mensagem do painel lembra isto. A aplicação já tenta o leitor normal do YouTube quando o "nocookie" falha.

## Limites e problemas

- A quota gratuita dá cerca de **100 pesquisas por dia**; cada música é pesquisada no máximo uma
  vez por dia (o servidor guarda o resultado), por isso chega bem.
- "Pesquisa automática desligada" no painel: o ficheiro não foi encontrado ou a chave não tem o
  formato certo. Confirme o nome do ficheiro (sem `.txt.txt`) e que só tem a chave.
- "Não foi possível pesquisar no YouTube": sem internet, a rede da empresa bloqueia
  `googleapis.com`, a API não está ativada no projeto, ou a quota do dia acabou.
- Pode desativar ou apagar a chave a qualquer momento em **Credenciais**.
