# DOTH PROJECT — NEW WEBSITE (V6)

## Preview online

**[Abrir o site DOTH — preview no GitHub Pages](https://francothesir.github.io/DOTH-PROJECT-NEW-WEBSITE/)**

Endereço: https://francothesir.github.io/DOTH-PROJECT-NEW-WEBSITE/

> Para ativar o endereço, configure **Settings → Pages → Build and deployment → Source: GitHub Actions**. A publicação é executada pelo workflow de Pages a cada atualização da branch `main`.


Site estático com provador 3D em GLB e catálogo com renders reais.

## Publicação GitHub Pages

Em **Settings → Pages → Build and deployment**, selecione **GitHub Actions**.
O workflow `.github/workflows/pages.yml` instala dependências, baixa os 8 modelos públicos do Drive oficial, otimiza os GLBs, gera as miniaturas de catálogo e publica a pasta `public` no GitHub Pages. Todos os modelos são convertidos a partir das fontes originais e não dependem de URLs temporários.

Se o Drive limitar downloads, confira as permissões públicas da pasta e execute o workflow novamente em **Actions → Publish DOTH website → Run workflow**. O conteúdo de `sources/` é temporário no runner e não é commitado.

## Executar localmente (com assets já incluídos no ZIP de entrega)

```sh
python3 -m http.server 8000
```

Navegue até http://localhost:8000/ . Não abra o `index.html` diretamente como `file://`, pois os modelos GLB são carregados via `fetch()`.

## Correções V6

- Alternativa visual 2D quando o dispositivo bloqueia WebGL ou o GLB ainda está carregando.
- Compilação 3D via GitHub Pages com fontes públicas e otimizadas.
- Boné oncinha marrom e versão P&B voltados para a frente no catálogo e no visualizador; xadrez mantém direção frontal original.
- Ajuste de suporte a WebGL 2 e índices Uint32, quando disponível.

## Correções V7 — roupas atravessando o manequim

- **Fendas nas peças eliminadas** (`scripts/optimize_models.py`): a simplificação agrupava vértices por posição + UV, então os dois lados de cada costura de UV iam para pontos diferentes e abriam fendas por onde o manequim aparecia. Agora a posição vem só do agrupamento espacial: cada peça passou de 10–23 mil arestas abertas para zero, e os GLBs ficaram ~7% menores.
- **Manequim reposicionado** (`pose_arms` em `optimize_models.py`): os braços pendiam colados ao tronco e atravessavam a lateral da jaqueta em vez de entrar na manga. Como numa armadura do Blender, cada braço gira 15° para fora em torno do ombro, com peso suave entre a axila e o alto do ombro. O peso do braço é gravado no GLB (atributo `_ARM`).
- **Cabeça com proporção humana** (`shrink_head` em `optimize_models.py`): a cabeça ocupava ~15% da altura (≈6,7 cabeças, largura 39% dos ombros) e parecia de boneco. Ela é reduzida 12% em torno do topo do pescoço, com transição suave, e chega a ~13% (≈7,6 cabeças, padrão adulto). O provador ancora a escala na altura original (`SOURCE_MANNEQUIN_HEIGHT`), então a calibração das roupas não muda; o boné usa o topo real da cabeça e acompanha o novo tamanho.
- **Corpo se recolhe sob a roupa** (`fitting-room.html`, `conformBody`): a cada troca de look, cada vértice do manequim é testado ao longo da normal contra as peças vestidas (BVH via `three-mesh-bvh`). Se estiver fora ou rente ao tecido, é empurrado para logo abaixo dele. Invasões fundas, cobertas pela peça, são ocultadas sob ela. As roupas nunca são deformadas.
  - As normais invertidas da malha do manequim são corrigidas antes (direção de escape do raio / paridade).
  - Cada peça só atua nas regiões que veste (`covers` em `garmentFit`): boné → cabeça; jaqueta → tronco e braços; calças e jardineira → tronco/pernas. Assim a borda de uma peça sem manga dentro do braço não abre buracos nele.
  - Partes do corpo apenas ao lado da peça (mão junto ao quadril) não são alteradas.

## Limites## Limites

O ajuste das peças 3D ao manequim ainda é aproximado, pois os GLBs não são peças rigadas para o corpo. Não há simulação física de tecido nem digitalização de todos os modos.
