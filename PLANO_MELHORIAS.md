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

- [x] `pytest` passa 100% localmente. (295 passed, 1 skipped — Chrome/Edge)
- [x] Cobertura ≥ 80% em `src/core/` e `src/pipeline.py`. (87% em `src/`)
- [x] Nenhum `ModuleNotFoundError` após `pip install -r requirements.txt`.
- [x] Pipeline retoma após simulação de falha (checkpoint).
- [x] Código-fonte (Java/C#/SQL) sai idêntico após ciclo tradução simulada.
- [x] `QualityAuditor` funciona para ≥ 3 pares de idioma (EN→PT, EN→ES, FR→PT).
- [x] Nenhum hardcode de título/autor no `EpubRefiner`.

---

## 7. Plano de Correção — Interface Gradio (`app.py`)

Este plano foi derivado da suíte de QA em `tests/unit/app/test_qa_app.py` (42 testes) e
documenta bugs reais encontrados ao exercer **todas** as funções expostas do `app.py`
com casos extremos, dados ausentes e entradas maliciosas.

### 7.1 Bugs Críticos — Crashes com dados incompletos

| ID | Função | Linha | Problema | Teste que expõe | Esforço |
|----|--------|-------|----------|-----------------|---------|
| C1 | `render_books_grid_html` | 186 | `pages=None` levanta `TypeError` em `{pages_count:,}` | `test_book_with_none_pages_crashes_format` | 15 min |
| C2 | `update_library_view` | 233 | `b['lang']`, `b['title']`, `b['slug']` (colchetes) → `KeyError` se faltar | `test_book_without_lang_key_raises_keyerror` | 15 min |
| C3 | `convert_scanned_pdf` | 426, 428 | `stats['chapters_created']`, `stats['epub_size_mb']` → `KeyError` | `test_stats_missing_chapters_created_keyerror` | 15 min |
| C4 | `convert_pdf_to_epub_flow` | 481–486 | `stats['title']`, `stats['total_pages']`, `stats['chapters_created']`, `stats['epub_size_mb']` → `KeyError` | `test_stats_missing_title_keyerror` | 15 min |
| C5 | `delete_book_from_library` | 334 | `lib.delete_book()` sem try/except → exceção propaga e quebra a UI | `test_delete_book_exception_not_caught` | 20 min |

**Critério de aceitação:** nenhum dos testes acima levanta exceção não capturada; a UI exibe valores seguros (`"—"` ou `"0"`) em vez de crashar.

### 7.2 Bugs de Segurança — XSS e injeção HTML/JS

| ID | Função | Linha | Problema | Teste que expõe | Esforço |
|----|--------|-------|----------|-----------------|---------|
| S1 | `render_books_grid_html` | 177–178 | Título do livro injetado direto em `title=""` e `<h3>` sem escape → quebra de atributo e XSS potencial (`<script>` executado) | `test_book_with_title_containing_angle_brackets`, `test_book_with_title_containing_quote_breaks_html` | 30 min |
| S2 | `render_books_grid_html` | 190–208 | Caminhos (`pdf_path_url`, `epub_path_url`) injetados em `onclick`/`href` sem escape → quebra do JS `fetch()` com aspas no caminho | `test_book_with_path_containing_quote` | 20 min |

**Critério de aceitação:** títulos com `<`, `>`, `"` e `'` são escapados; caminhos com aspas não quebram o `onclick` nem o `download`.

### 7.3 Inconsistências de UX entre telas (Média)

| ID | Função | Linha | Problema | Teste que expõe | Esforço |
|----|--------|-------|----------|-----------------|---------|
| U1 | `trans_open_folder_btn.click` | 933 | Passa `trans_last_pdf` (arquivo) para `open_folder_desktop`; deveria abrir a pasta do livro | inspeção de bindings (test_qa_app) | 20 min |
| U2 | `ocr_open_folder_btn.click` | 943 | Passa `ocr_last_epub` (arquivo EPUB); mesmo problema | — | 20 min |
| U3 | `conv_open_pdf_folder_btn.click` | 953 | Passa `conv_last_pdf`; mesmo problema | — | 20 min |
| U4 | `conv_open_epub_folder_btn.click` | 963 | Passa `conv_last_epub`; mesmo problema | — | 20 min |
| U5 | `on_select_book` | 262 | `source_lang` ausente defaulta hardcoded `"en"`; pode mostrar idioma errado | `test_book_missing_source_lang_defaults_en` | 10 min |
| U6 | `update_library_view` / `on_select_book` | 247, 283 | `date_added=None` → `"Data de Registro: "` vazio; `pdf_size_mb`/`epub_size_mb=None` → `"None MB"` literal | `test_date_added_none_shows_empty_label`, `test_book_with_none_numeric_fields_shows_none` | 20 min |
| U7 | `translate_book` | 380 | `pipeline.parser.metadata.get('title')` → `None` mostra `"None"` literal no status | `test_pipeline_parser_metadata_missing_title_shows_none` | 15 min |

### 7.4 Robustez de Entrada (Baixa)

| ID | Função | Problema | Teste que expõe | Esforço |
|----|--------|----------|-----------------|---------|
| B1 | `convert_pdf_to_epub_flow` | `title=None` pode chegar ao `FormatConverter.pdf_to_epub` sem validação clara | `test_title_and_author_stripped` | 10 min |
| B2 | `format_duration` | Valores negativos retornam `"-5s"` (estranho no contexto de tempo) | `test_negative_seconds` | 5 min |

### 7.5 Soluções propostas por bug

#### C1 — `pages=None` em `render_books_grid_html` (linha 186)
```python
# Antes
pages_count = b.get("pages", 0)
# Depois
pages_count = b.get("pages", 0) or 0
pages_display = f"{pages_count:,}" if isinstance(pages_count, (int, float)) else "—"
```
Usar `pages_display` no template em vez de `{pages_count:,}`.

#### C2 — Acesso direto a chaves em `update_library_view` (linha 233)
```python
# Antes
choices = [f"[{b['lang'].upper()}] {b['title']} | slug:{b['slug']}" for b in books]
# Depois
choices = [
    f"[{b.get('lang', '?').upper()}] {b.get('title', 'Sem título')} | slug:{b.get('slug', '')}"
    for b in books
]
```

#### C3/C4 — Acesso direto a `stats[...]` com colchetes
Substituir todos os `stats['chave']` por `stats.get('chave', valor_padrao)`:
- `title` → `"Título desconhecido"`
- `author` → `"Autor desconhecido"`
- `total_pages` → `0`
- `chapters_created` → `0`
- `epub_size_mb` → `0`
- `is_scanned` → `False`
- `code_blocks_merged` → `0`

#### C5 — try/except em `delete_book_from_library`
```python
try:
    lib.delete_book(lang=lang_code, slug=slug)
except Exception as e:
    return f"❌ Erro ao remover: {e}", *update_library_view(current_lang, current_cat)[:3], ""
return update_library_view(current_lang, current_cat)
```

#### S1/S2 — Escape de HTML
Criar helper `html_escape(s)` e aplicar em:
- `b.get('title')` no `<h3 title=...>` e conteúdo
- `pdf_path_url` / `epub_path_url` nos `onclick` e `href`
- `author`, `lang`, `category`

#### U1–U4 — Botões "Abrir Pasta" abrem arquivo, não pasta
Criar estados de pasta (`trans_last_folder`, `ocr_last_folder`, `conv_last_pdf_folder`, `conv_last_epub_folder`) e passar `os.path.dirname(caminho_arquivo)` para `open_folder_desktop`.

#### U5 — `source_lang` default hardcoded
`b.get('source_lang', 'pt')` em vez de `'en'`.

#### U6 — Campos ausentes na UI
- `date_added` → `"—"`
- `pdf_size_mb`/`epub_size_mb` → `"0 MB"` quando `None`

#### U7 — Título `None` no status
`pipeline.parser.metadata.get('title') or 'Título desconhecido'`

### 7.6 Cronograma sugerido (Sprint QA)

| Sprint | Foco | Entregável |
|--------|------|------------|
| **QA-1** | Críticos C1–C5 | `app.py` não crasha mais com dados ausentes; 5 testes críticos passam |
| **QA-2** | Segurança S1–S2 | HTML escapado; sem injeção via título/caminho |
| **QA-3** | UX U1–U7 | Botões de pasta funcionam; valores ausentes exibem `"—"` ou `"0"` |
| **QA-4** | Robustez B1–B2 + regressão | Suite completa verde; cobertura mantida |

### 7.7 Critério de aceitação final

- [x] `pytest tests/unit/app/test_qa_app.py` → 42/42 passando
- [x] `pytest tests/` → 295+ passando, 0 falhas
- [x] Nenhum `KeyError`/`TypeError` não capturado em `app.py`
- [x] Nenhum HTML não escapado injetado na biblioteca
- [x] Botões "Abrir Pasta" abrem o diretório correto

> **Status final (08/11/2026):** Plano 100% concluído. Sprints 1–8, QA-1 a QA-4,
> Sprint 9 (hardening Bing + fallback Google online/grátis), Sprint 10
> (QualityAuditor multi-idioma + fim do hardcode da biblioteca) e Sprint 11
> (desktop multiplataforma + CLI `--dry-run`/`--version`) mergeados.
> O Sprint 12 (separação UI/lógica do `app.py`) foi deliberadamente adiado:
> risco de regressão sem ganho funcional, conforme code review do PR #7.

---

## 8. Como Executar os Testes

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
