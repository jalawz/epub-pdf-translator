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
   ├─ [Translator] ──> Traduz em paralelo (Bing Neural ou Ollama Local)
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
git clone https://github.com/seu-usuario/epub-pdf-translator.git
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

---

## 📂 Estrutura do Repositório

```text
epub-pdf-translator/
├── src/
│   ├── core/
│   │   ├── epub_parser.py      # Leitura de container, manifest e spine
│   │   ├── code_shield.py      # Blindagem de código e URLs
│   │   ├── translator.py       # Bing Translator & Ollama Engine
│   │   ├── pdf_renderer.py     # Compilador HTML->PDF via Chromium headless
│   │   └── merger.py           # Concatenação de PDFs e empacotamento EPUB
│   └── pipeline.py             # Orquestrador com sistema de checkpoints
├── app.py                      # Aplicação Web com Gradio
├── cli.py                      # Interface CLI
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para obter mais informações.
