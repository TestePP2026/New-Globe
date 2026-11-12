# Globo de Notícias

Globo interativo com notícias por país. Um recolector em Python corre de 30 em 30 minutos no GitHub Actions,
grava `site/noticias.json` e publica o site no GitHub Pages.

## Pôr a funcionar (uma vez)
1. Cria um repositório novo no GitHub (público é o mais simples) e carrega para lá **todo o conteúdo desta pasta**
   (inclui a pasta oculta `.github`).
2. No repositório: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Separador **Actions → "Atualizar globo" → Run workflow**. Ao fim de 1–2 minutos o endereço do site aparece no job
   "deploy" e em Settings → Pages.
4. Abre o site e toca num país. Depois disto atualiza sozinho.

## Se algo falhar
- Em **Actions**, abre a última execução e vê o passo `python collector/collect.py`: cada fonte escreve uma linha
  ("RTP Notícias: 20 itens lidos, 3 usados" ou "AVISO ..."). Uma fonte com falha não impede as outras.
- Pontos sem notícias ficam mais apagados. Uma fonte só contribui com notícias que as palavras-chave
  classifiquem como finanças, mercados, economia ou política.

## Personalizar (ficheiro `collector/collect.py`, topo)
- `FEEDS`: acrescenta ou remove feeds RSS (nome, url, país fixo ou None, categoria por defeito).
- `BPSTAT_SERIES`: IDs de séries do Banco de Portugal (procura em bpstat.bportugal.pt) e aparecem no painel de Portugal.
- `CATS` e `ALIASES`: palavras-chave de categorias e de países.

Nota: só são guardados título, ligação, fonte e hora; o texto das notícias fica nos sites originais.
Os repositórios públicos podem ter as execuções agendadas suspensas após meses sem atividade; se acontecer, volta a correr o workflow.
