# 🗺️ Plano de Melhorias — epub-pdf-translator

> Este documento é o **guia de evolução contínua** do projeto. Ele registra a análise do estado atual, o plano de ação por feature e a estratégia de testes automatizados.

---

## 1. Visão Geral do Projeto

**epub-pdf-translator** é um motor de tradução de livros digitais EPUB para PDF estruturado (A4) com foco em:

1. **Preservar diagramação, imagens e fórmulas** (trabalha sobre o formato fluido EPUB, não sobre PDF diretamente).
2. **Blindagem absoluta de código** (`CodeShield`): blocos `<pre>`, `<code>`, anotações Java, scripts shell, YAML/JSON e URLs são protegidos contra tradução.
3. **Resiliência e checkpointing**: tradução capítulo a capítulo com cache em disco; retoma após falhas.
4. **Compilação automática para PDF** via Chromium headless (Chrome/Edge).
5. **Interface Gradio + CLI**.
6. **OCR de PDFs digitalizados** → EPUB reflowável.
7. **Conversor universal EPUB ↔ PDF**.
8. **Biblioteca digital local** (`output/library/`).

**Licença:** MIT  
**Versão:** 1.0.0  
**Remote:** https://github.com/jalawz/epub-pdf-translator.git  
**Branch:** `main`

---

## 2. Estado Atual (Diagnóstico)

### ✅ O que funciona
- Tradução EN → PT via Bing (scraping) ou Ollama local.
- Código protegido por `CodeShield`.
- Cache/checkpoint por capítulo.
- Renderização de capítulos individuais em PDF A4.
- Junção de PDFs com sumário/bookmarks.
- Reempacotamento de EPUB traduzido.
- Biblioteca digital com `metadata.json`, capas, tamanhos e contagem de páginas.
- OCR de PDFs escaneados (RapidOCR + ONNX).
- Conversor EPUB → PDF e PDF → EPUB.
- Ações de desktop (abrir PDF/EPUB/pasta) — Windows.

### ⚠️ Problemas conhecidos
| Área | Problema |
|------|----------|
| **Testes** | Zero testes automatizados. Não existe pasta `tests/`. |
| **Dependências** | `requirements.txt` não lista `PyMuPDF`, `rapidocr-onnxruntime`, `Pillow`, `starlette`. |
| **Bing Translator** | Depende de *scraping* frágil de `www.bing.com/translator` (regex de tokens de sessão). |
| **QualityAuditor** | Só compara stopwords EN vs. PT; não serve para outros pares de idioma. |
| **EpubRefiner** | Hardcodeia título "Código Limpo" / autor "Robert C. Martin" / UUID fixo no `content.opf` reescrito. |
| **Desktop** | `os.startfile` / `explorer` só funcionam no Windows. |
| **Segurança API** | Endpoints `/api/open-file` e `/api/open-folder` expõem caminhos locais sem autenticação nem validação de traversal. |
| **BookLibrary** | `scan_and_migrate_legacy()` tem hardcodes de autor/título. |

---

## 3. Plano de Ação por Feature (1 a 12)

Cada feature tem **problema → melhoria → critério de aceitação → prioridade**.

| # | Feature | Prioridade | Objetivo |
|---|---------|-----------|----------|
| 1 | **Fundação: dependências e ambiente** | Crítica | `requirements.txt` completo; app importa sem `ModuleNotFoundError`. |
| 2 | **CodeShield** | Crítica | Código-fonte entra e sai idêntico após mask → tradução simulada → unmask. |
| 3 | **Motor de tradução (Bing + Ollama)** | Alta | Tradução de texto longo sem perder pedaços; retry com backoff; mockável em testes. |
| 4 | **EpubParser** | Alta | Parsing robusto de EPUB mínimo; validação de estrutura; `extract_assets` seguro. |
| 5 | **TranslationPipeline** | Crítica | Checkpoint testável; retomada após falha simulada; `keep_cache` funcional. |
| 6 | **PdfRenderer** | Alta | Comando de render correto; fallback sem navegador; estilo A4 injetado. |
| 7 | **DocumentMerger** | Média-Alta | Junção de PDFs com bookmarks; reempacotamento EPUB válido (mimetype primeiro). |
| 8 | **QualityAuditor** | Média | Configurável por par de idioma; relatório JSON legível. |
| 9 | **BookLibrary** | Média | Sem hardcodes; listagem/filtro/remoção testáveis; integridade de arquivos. |
| 10 | **OCR Pipeline + EpubRefiner** | Média | Modelos locais opcionais; refiner preserva metadados reais (não hardcodeia "Código Limpo"). |
| 11 | **FormatConverter** | Média | Conversão EPUB ↔ PDF sem vazar cache temporário; idioma preservado. |
| 12 | **Interface (Gradio + CLI)** | Alta | Separação UI/lógica; multiplataforma desktop; endpoints seguros; `--dry-run`/`--version`. |

---

## 4. Estratégia de Testes (Test-First)

### Pilha sugerida
```text
pytest                 # runner
pytest-cov             # cobertura
responses / requests-mock  # mock de HTTP (Bing, Ollama)
PyMuPDF (fitz)         # geração de PDFs de teste
lxml                   # geração/validação de EPUBs e HTML
```

### Piramide
```
        /\
       /E2E\     (opcional, cliente de teste Gradio)
      /----\
     / Integ \   (pipeline com EPUB mínimo real)
    /--------\
   /  Unit    \  (code_shield, translator, quality_auditor, parser)
  /------------\
```

### Regra de ouro
> Toda correção ou nova feature começa com um **teste que falha** (TDD). Não reescrevemos tudo de uma vez; testamos enquanto corrigimos.

### Convenção de pastas
```
tests/
├── conftest.py
├── fixtures/
│   └── mini_book.epub          # gerado dinamicamente nos testes
├── unit/
│   ├── core/
│   │   ├── test_code_shield.py
│   │   ├── test_epub_parser.py
│   │   ├── test_translator.py
│   │   └── test_quality_auditor.py
│   └── pipeline/
│       └── test_checkpoint.py
├── integration/
│   └── test_pipeline_e2e.py
└── contract/
    └── test_cli.py
```

### Metas de cobertura
- **Mínimo aceitável:** 60% em `src/core/` e `src/pipeline.py`.
- **Alvo:** 85% nas funções puras (`code_shield`, `translator`, `quality_auditor`, `epub_parser`).

---

## 5. Cronograma Sugerido

| Sprint | Foco | Entregável |
|--------|------|------------|
| **1** | Fundação + Testes base | `requirements.txt` corrigido, `pytest` rodando, testes de `CodeShield` e `EpubParser` |
| **2** | Core de tradução | Testes de `BingTranslatorEngine` (mock), `OllamaTranslatorEngine`, chunking, `TranslationPipeline` checkpoint |
| **3** | Render e Merger | Testes de `PdfRenderer` (mock), `DocumentMerger`, `QualityAuditor` configurável por idioma |
| **4** | Biblioteca e OCR | Testes de `BookLibrary`, `ScannedPdfDetector`, correção do hardcode no `EpubRefiner` |
| **5** | Conversor e CLI | Testes de `FormatConverter`, CLI `argparse`, separação de camadas em `app.py` |
| **6** | Hardening | Multiplataforma desktop, segurança endpoints, cobertura ≥ 80%, README atualizado |

---

## 6. Métricas de Sucesso

- [ ] `pytest` passa 100% localmente.
- [ ] Cobertura ≥ 80% em `src/core/` e `src/pipeline.py`.
- [ ] Nenhum `ModuleNotFoundError` após `pip install -r requirements.txt`.
- [ ] Pipeline retoma após simulação de falha (checkpoint).
- [ ] Código-fonte (Java/C#/SQL) sai idêntico após ciclo tradução simulada.
- [ ] `QualityAuditor` funciona para ≥ 3 pares de idioma (EN→PT, EN→ES, FR→PT).
- [ ] Nenhum hardcode de título/autor no `EpubRefiner`.

---

## 7. Como Executar os Testes

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar todos os testes
pytest

# Rodar com cobertura
pytest --cov=src --cov-report=term-missing

# Rodar apenas unidade
pytest tests/unit

# Rodar um arquivo específico
pytest tests/unit/core/test_code_shield.py -v
```

---
