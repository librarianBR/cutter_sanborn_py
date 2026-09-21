# Gerador Cutter-Sanborn (Swanson-Swift, 1969) — interface Flet

## Arquivos
| Arquivo | Função |
|---|---|
| `app_flet.py` | Interface gráfica (Flet 1.0) |
| `cutter_sanborn.py` | Lógica de catalogação (também funciona sozinho, na linha de comando) |
| `tablacutter.json` | Tabela (12.329 entradas), sem alterações |
| `correcoes.json` | Correções que você confirmar na edição impressa (começa vazio) |
| `test_*.py` | Testes automatizados |

Mantenha todos na mesma pasta. Histórico e ajustes ficam em `~/.cutter_sanborn/estado.json`.

## Instalação
Requer Python 3.10 ou superior.

    pip install -r requirements.txt

## Execução
    python app_flet.py          # janela de desktop
    python app_flet.py --web    # abre no navegador local

## Funcionar sem internet

**Modo `--web` (mais simples).** O pacote `flet-web` já traz o cliente completo
(CanvasKit, fontes e ícones) e o app roda com `no_cdn=True`. Depois do `pip install`
não usa mais a internet. Verificado: o servidor entrega todos os arquivos localmente
e o `index.html` não referencia nenhum endereço externo.

**Janela de desktop.** O `flet-desktop` do PyPI tem só 13 KB: o cliente gráfico é
baixado do GitHub **uma única vez**, na primeira execução, e fica em `~/.flet/client`.
Para um computador que nunca terá internet, faça assim:

1. Num computador com internet, baixe o cliente da versão 1.0.0:
   - Windows: https://github.com/flet-dev/flet/releases/download/v1.0.0/flet-windows.zip (40 MB)
   - macOS: `flet-macos.tar.gz`, na mesma página de release
   - Linux: `flet-linux-<distro>-<arquitetura>.tar.gz`, na mesma página de release
2. Baixe também os pacotes Python:

       pip download -r requirements.txt -d pacotes

3. Leve tudo para o computador offline e instale:

       pip install --no-index --find-links pacotes -r requirements.txt

4. Aponte o Flet para o arquivo local (Windows, PowerShell):

       $env:FLET_CLIENT_URL = "file:///C:/caminho/flet-windows.zip"
       python app_flet.py

   Na primeira execução ele extrai o arquivo para `~/.flet/client`, e nas
   seguintes não precisa mais da variável.

Alternativa ao passo 4: extraia o zip e defina `FLET_VIEW_PATH` com a pasta `flet`
que contém o `flet.exe`.

## Testes
    python -m unittest test_cutter_sanborn test_app_flet

## Sobre os dados
Veja as observações sobre defeitos da tabela (`python cutter_sanborn.py --validar`,
ou a aba **Tabela** do app) e sobre direitos autorais no resumo do projeto.
