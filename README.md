# 📚 epub-pdf-translator

> **Universal EPUB Translation & Structured PDF Compilation Engine.**
> Traduza livros digitais mantendo 100% da diagramação, imagens, fórmulas e blindando blocos de código de programação.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Interface: Gradio](https://img.shields.io/badge/UI-Gradio-orange.svg)](https://gradio.app)

---

## ✨ Principais Diferenciais

A maioria das ferramentas de tradução de documentos tenta traduzir PDFs diretamente, quebrando fontes, limites de caixas de texto e diagramas. 

O **`epub-pdf-translator`** resolve esse problema na raiz:
1. **Trabalha sobre o formato fluido (EPUB):** Utiliza a estrutura semântica limpa do padrão W3C/IDPF.
2. **Blindagem Absoluta de Código (Code Shield):** Blocos `<pre>`, tags `<code>`, anotações (`@RestController`, `@SpringBootApplication`), scripts shell, arquivos YAML/JSON e URLs são **100% protegidos**. O motor traduz apenas os textos explicativos.
3. **Resiliência e Checkpointing:** Traduz capítulo a capítulo com cache automático em disco. Se a máquina reiniciar ou a internet oscilar, o processo retoma exatamente do capítulo onde parou.
4. **Compilação Automática para PDF:** Utiliza o motor gráfico Chromium headless (compatível com Windows, Linux e macOS) para renderizar um PDF final encadernado, no padrão A4 com sumário, fontes e margens de editora.
5. **Interface Gráfica + CLI:** Use pelo navegador com Drag & Drop ou integre em automações via terminal.

---

## 🏗️ Arquitetura do Sistema

```text
[Arquivo .epub]
      │
      ▼
[EpubParser] ──> Extrai Metadados, Spine (ordem dos capítulos), Estilos (CSS) e Imagens
      │
      ▼
[Loop Capítulo por Capítulo]
   ├─ [CodeShield] ──> Mascara tags <code>, <pre>, URLs com tokens invioláveis
   ├─ [Translator] ──> Traduz em paralelo (Bing Neural com fallback automático
   │                    para o Google Translate online — grátis, sem chave;
   │                    Ollama local disponível como opção manual)
   ├─ [CodeShield] ──> Restaura as tags e códigos originais
   ├─ [Cache/Disk] ──> Salva versão traduzida (resiliência contra falhas)
   └─ [PdfRenderer] ──> Renderiza o PDF individual do capítulo via Chromium headless
      │
      ▼
[DocumentMerger]
   ├─ Gera o Livro Completo em PDF consolidado com marcadores
   └─ Remonta o pacote .epub traduzido completo
```

---

## 🚀 Como Usar

### 1. Instalação

Clone o repositório e instale as dependências:

```bash
git clone https://github.com/jalawz/epub-pdf-translator.git
cd epub-pdf-translator
pip install -r requirements.txt
```

> **Requisito para geração do PDF:** Ter o **Google Chrome** ou **Microsoft Edge** instalado no sistema (detectado automaticamente no Windows, Linux e macOS).

---

### 2. Executando a Interface Gráfica (WebUI)

Inicie a aplicação:

```bash
python app.py
```

O navegador abrirá automaticamente em `http://localhost:7860`.
1. Arraste seu arquivo `.epub` para a tela;
2. Escolha os idiomas (ex: Inglês ➔ Português);
3. Escolha o motor (*Neural Fast Translator* gratuito ou *Ollama* local);
4. Clique em **"Iniciar Tradução do Livro"**;
5. Baixe o **PDF Final** e o **EPUB Traduzido**.

---

### 3. Executando via Linha de Comando (CLI)

Para traduzir diretamente pelo terminal:

```bash
# Tradução padrão para Português (Brasil)
python cli.py "caminho/do/seu_livro.epub" -li en -lo pt

# Usando modelo de IA local via Ollama
python cli.py "caminho/do/seu_livro.epub" -li en -lo pt --ollama qwen2.5:latest
```

Opções disponíveis no CLI:
* `-li`, `--lang-in`: Idioma de origem (padrão: `en`)
* `-lo`, `--lang-out`: Idioma de destino (padrão: `pt`)
* `-o`, `--output-dir`: Diretório de saída (padrão: `output`)
* `-w`, `--workers`: Número de threads simultâneas (padrão: `5`)
* `--ollama`: Nome do modelo local no Ollama (ex: `qwen2.5:latest`, `llama3.1:latest`)
* `--dry-run`: Valida as entradas e imprime o plano sem traduzir
* `--version`: Imprime a versão do pacote e sai

```bash
# Simulação (não traduz nada)
python cli.py "caminho/do/seu_livro.epub" --dry-run

# Versão instalada
python cli.py --version
```

---

## 🧪 Qualidade e Testes

O projeto é desenvolvido com **Test-Driven Development (TDD)** e possui suíte automatizada completa:

```bash
# Rodar todos os testes
pytest

# Rodar com cobertura
pytest --cov=src --cov-report=term
```

- **295 testes** (unitários, de integração e de QA da interface), cobertura de **87%** em `src/`
- Testes de QA exercem todas as funções da interface Gradio com casos extremos, dados ausentes e entradas maliciosas (XSS, path traversal)
- Auditoria de qualidade pós-tradução gera `translation_quality_report.json` (QualityAuditor multi-idioma: EN→PT, EN→ES, FR→PT)

---

## 💻 Compatibilidade

- **Interface desktop:** Windows (`os.startfile`/Explorer), macOS (`open`/`open -R`) e Linux (`xdg-open`) — ações "abrir arquivo/pasta" são multiplataforma
- **Endpoints locais** (`/api/open-file`, `/api/open-folder`) confinados ao diretório `output/` (path traversal rejeitado com HTTP 403)
- **Geração de PDF:** requer Google Chrome ou Microsoft Edge instalado (detecção automática)

---

## ⚠️ Limitações conhecidas

- O motor padrão usa endpoints web não-oficiais do Bing/Google (gratuitos, sem chave). O Bing possui padrões de extração alternativos, backoff exponencial e **fallback automático para o Google Translate online**; uma API oficial (ex.: Azure Translator, com chave) pode ser adicionada como opção futura
- A auditoria de qualidade por stopwords cobre EN/PT/ES/FR; para idiomas sem espaços (ex.: chinês/japonês) o método é menos eficaz
- `app.py` concentra interface, handlers e endpoints em um único módulo Gradio (refatoração de separação UI/lógica deliberadamente adiada — ver `PLANO_MELHORIAS.md`)

---

## 📂 Estrutura do Repositório

```text
epub-pdf-translator/
├── src/
│   ├── core/
│   │   ├── epub_parser.py      # Leitura de container, manifest e spine
│   │   ├── code_shield.py      # Blindagem de código e URLs
│   │   ├── translator.py       # Bing (fallback Google online) & Ollama Engine
│   │   ├── quality_auditor.py  # Auditoria multi-idioma de tradução
│   │   ├── library.py          # Biblioteca digital local (sem hardcodes)
│   │   ├── epub_refiner.py     # Refinamento de EPUB preservando metadados
│   │   ├── layout_ocr.py       # OCR com detecção de layout semântico
│   │   ├── converter.py        # Conversão EPUB <-> PDF
│   │   ├── scanned_detector.py # Detecção de PDF escaneado
│   │   ├── pdf_renderer.py     # Compilador HTML->PDF via Chromium headless
│   │   └── merger.py           # Concatenação de PDFs e empacotamento EPUB
│   ├── pipeline.py             # Orquestrador com sistema de checkpoints
│   └── ocr_pipeline.py         # Pipeline OCR -> EPUB
├── app.py                      # Aplicação Web com Gradio
├── cli.py                      # Interface CLI
├── tests/                      # Suíte de testes (unit, integração, QA de UI)
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para obter mais informações.
