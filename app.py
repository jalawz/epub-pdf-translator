import os
import sys
import re
import json
import base64
import io
import time
import urllib.parse
import subprocess
from PIL import Image
import gradio as gr
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, JSONResponse

class CleanPathMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Redirect consecutive slashes (e.g. // or http://localhost:7860//) to single slash
        if request.url.path.endswith("//") or "//" in request.url.path:
            clean = re.sub(r"/+", "/", request.url.path)
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(url=(clean or "/") + query, status_code=302)
        return await call_next(request)

# Add repository root to pythonpath
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.pipeline import TranslationPipeline
from src.core.translator import BingTranslatorEngine, OllamaTranslatorEngine
from src.core.library import BookLibrary
from src.ocr_pipeline import OcrToEpubPipeline
from src.core.converter import FormatConverter

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LANGUAGE_OPTIONS = [
    ("Português (Brasil)", "pt"),
    ("English", "en"),
    ("Español", "es"),
    ("Français", "fr"),
    ("Deutsch", "de"),
    ("Italiano", "it"),
    ("中文 (Chinese)", "zh"),
    ("日本語 (Japanese)", "ja"),
]

FILTER_LANG_OPTIONS = [
    ("Todos os Idiomas", "Todos"),
    ("🇧🇷 Português (pt)", "pt"),
    ("🇺🇸 English (en)", "en"),
    ("🇪🇸 Español (es)", "es"),
    ("🇫🇷 Français (fr)", "fr"),
    ("🇩🇪 Deutsch (de)", "de"),
    ("🇮🇹 Italiano (it)", "it"),
    ("🇨🇳 中文 (zh)", "zh"),
    ("🇯🇵 日本語 (ja)", "ja"),
]

FILTER_CATEGORY_OPTIONS = [
    ("Todas as Categorias", "Todos"),
    ("🌐 Livros Traduzidos", "translation"),
    ("📷 Livros Digitalizados (OCR)", "ocr"),
]

def format_duration(seconds: float) -> str:
    secs = int(round(seconds))
    if secs < 60:
        return f"{secs}s"
    mins, remainder_secs = divmod(secs, 60)
    if mins < 60:
        return f"{mins} min {remainder_secs:02d} s"
    hours, remainder_mins = divmod(mins, 60)
    return f"{hours} h {remainder_mins:02d} min {remainder_secs:02d} s"

def open_file_desktop(file_path: str) -> str:
    if not file_path or not os.path.exists(file_path):
        return "⚠️ Arquivo não encontrado no disco local."
    try:
        norm_path = os.path.normpath(file_path)
        os.startfile(norm_path)
        return f"🚀 **Arquivo aberto no leitor do Windows:** `{os.path.basename(norm_path)}`"
    except Exception as e:
        return f"❌ Erro ao abrir arquivo: {str(e)}"

def open_folder_desktop(target_path: str) -> str:
    if not target_path or not os.path.exists(target_path):
        return "⚠️ Caminho não encontrado no disco local."
    try:
        norm_path = os.path.normpath(target_path)
        if os.path.isdir(norm_path):
            os.startfile(norm_path)
        else:
            subprocess.Popen(["explorer", f"/select,{norm_path}"])
        return f"📂 **Pasta aberta no Windows Explorer:** `{os.path.dirname(norm_path) if not os.path.isdir(norm_path) else norm_path}`"
    except Exception as e:
        return f"❌ Erro ao abrir pasta: {str(e)}"

def render_books_grid_html(books):
    if not books:
        return """
        <div style="text-align: center; padding: 45px 20px; color: #64748b; background: #f8fafc; border-radius: 12px; border: 2px dashed #cbd5e1; margin-top: 15px;">
            <div style="font-size: 2.8rem; margin-bottom: 10px;">📭</div>
            <p style="font-size: 1.25rem; font-weight: 600; color: #334155; margin: 0 0 8px 0;">Nenhum livro encontrado nesta seleção</p>
            <p style="font-size: 0.95rem; margin: 0;">Traduza ou digitalize uma obra nas abas superiores para visualizá-la nesta estante!</p>
        </div>
        """

    flag_map = {
        "pt": "🇧🇷 PT", "en": "🇺🇸 EN", "es": "🇪🇸 ES",
        "fr": "🇫🇷 FR", "de": "🇩🇪 DE", "it": "🇮🇹 IT",
        "zh": "🇨🇳 ZH", "ja": "🇯🇵 JA"
    }

    cards_html = []
    for b in books:
        cover_b64 = ""
        cover_path = b.get("cover_path")
        if cover_path and os.path.exists(cover_path):
            try:
                im = Image.open(cover_path)
                im.thumbnail((360, 540))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=88)
                cover_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception:
                cover_b64 = ""

        if cover_b64:
            img_tag = f'<img src="{cover_b64}" alt="Capa" />'
        else:
            img_tag = '<div style="font-size: 3.5rem; color: #94a3b8;">📖</div>'

        lang_badge = flag_map.get(b.get("lang", "").lower(), f"🌐 {b.get('lang', '').upper()}")
        pages_count = b.get("pages", 0)
        pdf_size = b.get("pdf_size_mb", 0)
        epub_size = b.get("epub_size_mb", 0)
        date_formatted = (b.get("date_added") or "")[:10]
        
        pdf_path = b.get("pdf_path") or ""
        epub_path = b.get("epub_path") or ""
        book_dir = b.get("book_dir") or (os.path.dirname(pdf_path) if pdf_path else "")

        pdf_filename = os.path.basename(pdf_path or f"{b.get('slug', 'book')}.pdf")
        epub_filename = os.path.basename(epub_path or f"{b.get('slug', 'book')}.epub")

        pdf_path_url = pdf_path.replace("\\", "/")
        epub_path_url = epub_path.replace("\\", "/")

        category = b.get("category", "translation")
        if category == "ocr":
            cat_badge_class = "card-badge-ocr"
            cat_badge_text = "📷 Digitalizado (OCR)"
        else:
            cat_badge_class = "card-badge-trans"
            src_l = b.get("source_lang", "EN").upper()
            tgt_l = b.get("lang", "PT").upper()
            cat_badge_text = f"🌐 Traduzido ({src_l} ➔ {tgt_l})"

        card = f"""
        <div class="library-card">
            <div class="card-cover-stage">
                {img_tag}
                <div class="card-badge-category {cat_badge_class}">
                    {cat_badge_text}
                </div>
                <div class="card-badge-lang">
                    {lang_badge}
                </div>
                <div class="card-badge-quality">
                    ✅ 100% Qualidade
                </div>
            </div>
            <div class="card-content">
                <div>
                    <h3 class="card-title" title="{b.get('title')}">
                        {b.get('title')}
                    </h3>
                    <p class="card-author">
                        ✍️ {b.get('author', 'Autor Desconhecido')}
                    </p>
                </div>
                <div>
                    <div class="card-meta-bar">
                        <span class="card-pages-text">📄 <b>{pages_count:,}</b> páginas</span>
                        <span class="card-date-text">🗓️ {date_formatted}</span>
                    </div>
                    <div class="card-btn-grid">
                        <button class="card-btn card-btn-pdf" onclick="fetch('/api/open-file?path=' + encodeURIComponent('{pdf_path_url}')).catch(console.error); return false;" title="Abrir PDF no aplicativo padrão do Windows">
                            <span>📄 Abrir PDF</span>
                            <span class="card-btn-sub">({pdf_size} MB)</span>
                        </button>
                        <button class="card-btn card-btn-epub" onclick="fetch('/api/open-file?path=' + encodeURIComponent('{epub_path_url}')).catch(console.error); return false;" title="Abrir EPUB no aplicativo padrão do Windows">
                            <span>📱 Abrir EPUB</span>
                            <span class="card-btn-sub">({epub_size} MB)</span>
                        </button>
                    </div>
                    <div class="card-actions-sub">
                        <button class="card-sub-btn" onclick="fetch('/api/open-folder?path=' + encodeURIComponent('{pdf_path_url}')).catch(console.error); return false;" title="Abrir pasta no Windows Explorer">
                            📂 Abrir Pasta
                        </button>
                        <a href="/gradio_api/file={pdf_path_url}" target="_blank" download="{pdf_filename}" class="card-sub-link" title="Baixar arquivo PDF">
                            ⬇️ PDF
                        </a>
                        <a href="/gradio_api/file={epub_path_url}" target="_blank" download="{epub_filename}" class="card-sub-link" title="Baixar arquivo EPUB">
                            ⬇️ EPUB
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """
        cards_html.append(card)

    return f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(285px, 1fr)); gap: 24px; margin-top: 15px;">
        {''.join(cards_html)}
    </div>
    """

def get_library_books(lang_code="Todos", category="Todos"):
    lib = BookLibrary(OUTPUT_DIR)
    lib.scan_and_migrate_legacy()
    code = None if lang_code in ["Todos", "all", ""] else lang_code
    cat = None if category in ["Todos", "all", ""] else category
    books = lib.list_books(lang=code, category=cat)
    return books

def update_library_view(lang_code="Todos", category="Todos"):
    books = get_library_books(lang_code, category)
    grid_html = render_books_grid_html(books)
    choices = [f"[{b['lang'].upper()}] {b['title']} | slug:{b['slug']}" for b in books]
    default_val = choices[0] if choices else None

    if default_val:
        first_b = books[0]
        pdf = first_b.get("pdf_path") if os.path.exists(first_b.get("pdf_path", "")) else None
        epub = first_b.get("epub_path") if os.path.exists(first_b.get("epub_path", "")) else None
        pdf_name = os.path.basename(pdf) if pdf else ""
        epub_name = os.path.basename(epub) if epub else ""
        cat_badge = "📷 Digitalizado (OCR)" if first_b.get("category") == "ocr" else "🌐 Traduzido"
        info = (
            f"### 📖 {first_b.get('title')}\n"
            f"- **Categoria:** `{cat_badge}` | **Autor:** {first_b.get('author')}\n"
            f"- **Páginas:** {first_b.get('pages')} | **Idioma:** {first_b.get('lang', '').upper()}\n"
            f"- **Arquivo PDF:** `{pdf_name}` ({first_b.get('pdf_size_mb')} MB)\n"
            f"- **Arquivo EPUB:** `{epub_name}` ({first_b.get('epub_size_mb')} MB)\n"
            f"- **Local no Disco:** `{first_b.get('book_dir') or os.path.dirname(pdf or '')}`"
        )
    else:
        info = "Nenhum livro encontrado com os filtros selecionados."

    return grid_html, gr.update(choices=choices, value=default_val), info, ""

def on_select_book(selected_label):
    if not selected_label or "| slug:" not in selected_label:
        return "Nenhum livro selecionado.", ""

    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"

    lib = BookLibrary(OUTPUT_DIR)
    book = lib.get_book(lang=lang_code, slug=slug)
    if not book:
        return "Livro não localizado.", ""

    pdf_p = book.get("pdf_path") if os.path.exists(book.get("pdf_path", "")) else None
    epub_p = book.get("epub_path") if os.path.exists(book.get("epub_path", "")) else None
    pdf_name = os.path.basename(pdf_p) if pdf_p else ""
    epub_name = os.path.basename(epub_p) if epub_p else ""
    cat_badge = "📷 Digitalizado (OCR)" if book.get("category") == "ocr" else "🌐 Traduzido"

    info = (
        f"### 📖 {book.get('title')}\n"
        f"- **Categoria:** `{cat_badge}` | **Autor:** {book.get('author', 'Desconhecido')}\n"
        f"- **Idioma:** {book.get('lang', '').upper()} (Original: {book.get('source_lang', 'en').upper()})\n"
        f"- **Páginas:** {book.get('pages', 0)} | **Tamanhos:** PDF ({book.get('pdf_size_mb', 0)} MB) • EPUB ({book.get('epub_size_mb', 0)} MB)\n"
        f"- **Arquivo PDF:** `{pdf_name}`\n"
        f"- **Arquivo EPUB:** `{epub_name}`\n"
        f"- **Local no Disco:** `{book.get('book_dir') or os.path.dirname(pdf_p or '')}`\n"
        f"- **Data de Registro:** {(book.get('date_added') or '')[:10]}\n"
        f"- **Certificação:** ✅ 100% Qualidade Verificada"
    )
    return info, ""

def action_open_selected_pdf(selected_label):
    if not selected_label or "| slug:" not in selected_label:
        return "⚠️ Selecione um livro na lista primeiro."
    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"
    lib = BookLibrary(OUTPUT_DIR)
    book = lib.get_book(lang=lang_code, slug=slug)
    if not book or not book.get("pdf_path"):
        return "⚠️ Arquivo PDF não encontrado."
    return open_file_desktop(book["pdf_path"])

def action_open_selected_epub(selected_label):
    if not selected_label or "| slug:" not in selected_label:
        return "⚠️ Selecione um livro na lista primeiro."
    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"
    lib = BookLibrary(OUTPUT_DIR)
    book = lib.get_book(lang=lang_code, slug=slug)
    if not book or not book.get("epub_path"):
        return "⚠️ Arquivo EPUB não encontrado."
    return open_file_desktop(book["epub_path"])

def action_open_selected_folder(selected_label):
    if not selected_label or "| slug:" not in selected_label:
        return "⚠️ Selecione um livro na lista primeiro."
    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"
    lib = BookLibrary(OUTPUT_DIR)
    book = lib.get_book(lang=lang_code, slug=slug)
    if not book:
        return "⚠️ Pasta do livro não encontrada."
    target = book.get("pdf_path") or book.get("epub_path") or book.get("book_dir")
    return open_folder_desktop(target)

def delete_book_from_library(selected_label, current_lang, current_cat):
    if not selected_label or "| slug:" not in selected_label:
        return update_library_view(current_lang, current_cat)

    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"

    lib = BookLibrary(OUTPUT_DIR)
    lib.delete_book(lang=lang_code, slug=slug)
    return update_library_view(current_lang, current_cat)

def translate_book(
    epub_file,
    source_lang,
    target_lang,
    engine_choice,
    ollama_model,
    workers,
    keep_cache,
    progress=gr.Progress()
):
    if not epub_file:
        raise gr.Error("Por favor, selecione ou envie um arquivo .epub!")

    input_path = epub_file.name if hasattr(epub_file, "name") else epub_file
    progress(0.0, desc="Inicializando pipeline...")
    t0 = time.time()

    if "Ollama" in engine_choice:
        model_name = ollama_model.strip() or "qwen2.5:latest"
        translator = OllamaTranslatorEngine(lang_in=source_lang, lang_out=target_lang, model=model_name)
    else:
        translator = BingTranslatorEngine(lang_in=source_lang, lang_out=target_lang)

    pipeline = TranslationPipeline(
        epub_path=input_path,
        output_dir=OUTPUT_DIR,
        lang_in=source_lang,
        lang_out=target_lang,
        translator=translator,
        max_workers=int(workers)
    )

    def on_progress(percent: float, message: str):
        progress(percent, desc=message)

    final_pdf, final_epub = pipeline.run(
        progress_callback=on_progress,
        keep_cache=bool(keep_cache)
    )
    elapsed_time = format_duration(time.time() - t0)

    status_msg = (
        f"### 🎉 Tradução Concluída com Sucesso!\n"
        f"- **Livro:** {pipeline.parser.metadata.get('title')}\n"
        f"- **Tempo Total:** `{elapsed_time}`\n"
        f"- **Capítulos traduzidos:** {len(pipeline.parser.spine)}\n"
        f"- **PDF diagramado:** `{os.path.basename(final_pdf)}`\n"
        f"- **EPUB traduzido:** `{os.path.basename(final_epub)}`\n"
        f"- **Biblioteca:** Adicionado automaticamente à estante de `{target_lang.upper()}`!"
    )

    grid_html, book_choices, info, _ = update_library_view("Todos", "Todos")
    return final_pdf, final_epub, status_msg, final_pdf, final_epub, grid_html, book_choices

def convert_scanned_pdf(
    pdf_file,
    book_title,
    book_author,
    ocr_lang,
    progress=gr.Progress()
):
    if not pdf_file:
        raise gr.Error("Por favor, selecione ou envie um arquivo PDF escaneado!")

    input_path = pdf_file.name if hasattr(pdf_file, "name") else pdf_file
    progress(0.0, desc="Iniciando motor de OCR...")
    t0 = time.time()

    pipeline = OcrToEpubPipeline(
        pdf_path=input_path,
        output_dir=OUTPUT_DIR,
        lang=ocr_lang,
        title=book_title,
        author=book_author
    )

    def on_progress(percent: float, message: str):
        progress(percent, desc=message)

    final_epub, stats = pipeline.run(progress_callback=on_progress)
    elapsed_time = format_duration(time.time() - t0)

    code_merged_text = f"- **Blocos de Código Unificados:** {stats.get('code_blocks_merged', 0)}\n" if stats.get('code_blocks_merged') else ""
    status_msg = (
        f"### 🎉 Conversão OCR Concluída com Sucesso!\n"
        f"- **Título:** {stats['title']}\n"
        f"- **Autor:** {stats['author']}\n"
        f"- **Tempo Total:** `{elapsed_time}`\n"
        f"- **Páginas Processadas:** {stats['total_pages']}\n"
        f"- **Capítulos Consolidados:** {stats['chapters_created']}\n"
        f"{code_merged_text}"
        f"- **Tamanho do EPUB:** {stats['epub_size_mb']} MB\n"
        f"- **Biblioteca:** Obra indexada na categoria de livros digitalizados!"
    )

    grid_html, book_choices, info, _ = update_library_view("Todos", "Todos")
    return final_epub, status_msg, final_epub, grid_html, book_choices

def convert_epub_to_pdf_flow(epub_file, progress=gr.Progress()):
    if not epub_file:
        raise gr.Error("Por favor, envie um arquivo EPUB para conversão!")
    input_path = epub_file.name if hasattr(epub_file, "name") else epub_file
    progress(0.0, desc="Iniciando diagramação em PDF...")
    t0 = time.time()

    def on_progress(percent: float, message: str):
        progress(percent, desc=message)

    final_pdf = FormatConverter.epub_to_pdf(input_path, OUTPUT_DIR, progress_callback=on_progress)
    elapsed_time = format_duration(time.time() - t0)
    pdf_size_mb = round(os.path.getsize(final_pdf) / (1024 * 1024), 2)

    status_msg = (
        f"### 🎉 Conversão EPUB ➔ PDF Concluída!\n"
        f"- **Arquivo:** `{os.path.basename(final_pdf)}`\n"
        f"- **Tamanho:** {pdf_size_mb} MB\n"
        f"- **Tempo Total:** `{elapsed_time}`\n"
        f"- **Local:** `{final_pdf}`"
    )
    return final_pdf, status_msg, final_pdf

def convert_pdf_to_epub_flow(pdf_file, title, author, lang, progress=gr.Progress()):
    if not pdf_file:
        raise gr.Error("Por favor, envie um arquivo PDF para conversão!")
    input_path = pdf_file.name if hasattr(pdf_file, "name") else pdf_file
    progress(0.0, desc="Analisando documento PDF...")
    t0 = time.time()

    def on_progress(percent: float, message: str):
        progress(percent, desc=message)

    final_epub, stats = FormatConverter.pdf_to_epub(
        pdf_path=input_path,
        output_dir=OUTPUT_DIR,
        title=title.strip() if title else None,
        author=author.strip() if author else None,
        lang=lang,
        progress_callback=on_progress
    )
    elapsed_time = format_duration(time.time() - t0)

    pdf_type_desc = "Escaneado / Foto (Processado via Motor OCR de Alta Resolução)" if stats.get("is_scanned") else "Vetorial Digital Nativo"
    status_msg = (
        f"### 🎉 Conversão PDF ➔ EPUB Concluída!\n"
        f"- **Título:** {stats['title']}\n"
        f"- **Tipo de PDF Detectado:** `{pdf_type_desc}`\n"
        f"- **Páginas Processadas:** {stats['total_pages']}\n"
        f"- **Capítulos Gerados:** {stats['chapters_created']}\n"
        f"- **Tamanho do EPUB:** {stats['epub_size_mb']} MB\n"
        f"- **Tempo Total:** `{elapsed_time}`\n"
        f"- **Local:** `{final_epub}`"
    )
    return final_epub, status_msg, final_epub

custom_css = """
.main-header {
    text-align: center;
    margin-bottom: 24px;
    padding-top: 10px;
}
.main-header h1 {
    font-size: 2.3rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.5px;
    margin-bottom: 6px;
}
.main-header p {
    color: #475569;
    font-size: 1.05rem;
    max-width: 850px;
    margin: 0 auto;
}
.library-card {
    background: #1e293b !important;
    border-radius: 12px !important;
    border: 1px solid #334155 !important;
    overflow: hidden !important;
    display: flex !important;
    flex-direction: column !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.2) !important;
}
.library-card:hover {
    transform: translateY(-5px) !important;
    border-color: #38bdf8 !important;
    box-shadow: 0 16px 24px -4px rgba(0, 0, 0, 0.4), 0 6px 10px -3px rgba(0, 0, 0, 0.3) !important;
}
.card-cover-stage {
    height: 300px !important;
    background: #090d16 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 14px !important;
    position: relative !important;
}
.card-cover-stage img {
    max-height: 272px !important;
    max-width: 100% !important;
    object-fit: contain !important;
    border-radius: 6px !important;
    box-shadow: 0 10px 20px -3px rgba(0, 0, 0, 0.7), 0 4px 6px -2px rgba(0, 0, 0, 0.4) !important;
}
.card-badge-category {
    position: absolute !important;
    top: 12px !important;
    left: 12px !important;
    color: #ffffff !important;
    padding: 4px 10px !important;
    border-radius: 14px !important;
    font-size: 0.74rem !important;
    font-weight: 700 !important;
    backdrop-filter: blur(4px) !important;
    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
}
.card-badge-trans {
    background: rgba(3, 105, 161, 0.92) !important;
    border: 1px solid rgba(56, 189, 248, 0.4) !important;
}
.card-badge-ocr {
    background: rgba(124, 58, 237, 0.92) !important;
    border: 1px solid rgba(192, 132, 252, 0.4) !important;
}
.card-badge-lang {
    position: absolute !important;
    top: 12px !important;
    right: 12px !important;
    background: rgba(15, 23, 42, 0.9) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    color: #ffffff !important;
    padding: 4px 10px !important;
    border-radius: 14px !important;
    font-size: 0.76rem !important;
    font-weight: 700 !important;
    backdrop-filter: blur(4px) !important;
}
.card-badge-quality {
    position: absolute !important;
    bottom: 12px !important;
    left: 12px !important;
    background: rgba(22, 163, 74, 0.95) !important;
    color: #ffffff !important;
    padding: 3px 10px !important;
    border-radius: 12px !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 5px rgba(0,0,0,0.4) !important;
}
.card-content {
    padding: 16px !important;
    background: #1e293b !important;
    flex-grow: 1 !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
}
.card-title {
    margin: 0 0 6px 0 !important;
    font-size: 1.12rem !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    line-height: 1.35 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
}
.card-author {
    margin: 0 0 12px 0 !important;
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    color: #cbd5e1 !important;
}
.card-meta-bar {
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
    margin-bottom: 10px !important;
    padding: 8px 12px !important;
    background: #0f172a !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
}
.card-pages-text {
    color: #38bdf8 !important;
    font-weight: 700 !important;
    font-size: 0.86rem !important;
}
.card-date-text {
    color: #94a3b8 !important;
    font-size: 0.80rem !important;
    font-weight: 500 !important;
}
.card-btn-grid {
    display: grid !important;
    grid-template-columns: 1fr 1fr !important;
    gap: 8px !important;
    margin-bottom: 8px !important;
}
.card-btn {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    padding: 9px 8px !important;
    border-radius: 6px !important;
    text-decoration: none !important;
    font-size: 0.84rem !important;
    font-weight: 700 !important;
    transition: all 0.2s ease !important;
    color: #ffffff !important;
    border: none !important;
    cursor: pointer !important;
}
.card-btn-pdf {
    background: #0284c7 !important;
}
.card-btn-pdf:hover {
    background: #0369a1 !important;
    transform: scale(1.02) !important;
}
.card-btn-epub {
    background: #0d9488 !important;
}
.card-btn-epub:hover {
    background: #0f766e !important;
    transform: scale(1.02) !important;
}
.card-btn-sub {
    font-size: 0.72rem !important;
    opacity: 0.85 !important;
    font-weight: 500 !important;
}
.card-actions-sub {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 6px !important;
    margin-top: 4px !important;
}
.card-sub-btn {
    flex: 1.5 !important;
    background: #334155 !important;
    color: #f1f5f9 !important;
    border: 1px solid #475569 !important;
    border-radius: 5px !important;
    padding: 5px 8px !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    text-align: center !important;
    transition: all 0.2s ease !important;
}
.card-sub-btn:hover {
    background: #475569 !important;
    color: #ffffff !important;
}
.card-sub-link {
    flex: 1 !important;
    background: #0f172a !important;
    color: #94a3b8 !important;
    border: 1px solid #334155 !important;
    border-radius: 5px !important;
    padding: 5px 4px !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-decoration: none !important;
    text-align: center !important;
    transition: all 0.2s ease !important;
}
.card-sub-link:hover {
    color: #ffffff !important;
    border-color: #64748b !important;
}
"""

with gr.Blocks(title="epub-pdf-translator", css=custom_css, theme=gr.themes.Soft()) as demo:
    gr.HTML("""
    <div class="main-header">
        <h1>📚 epub-pdf-translator</h1>
        <p>Plataforma local open-source para tradução técnica de alta fidelidade, digitalização OCR de livros escaneados, conversão universal EPUB ⟷ PDF e estante digital integrada.</p>
    </div>
    """)

    with gr.Tabs() as tabs:
        # ----------------- ABA 1: TRADUÇÃO -----------------
        with gr.TabItem("🚀 Traduzir Novo Livro", id="tab_translate"):
            with gr.Row():
                with gr.Column(scale=5):
                    epub_input = gr.File(
                        label="Envie seu arquivo .epub",
                        file_types=[".epub"],
                        type="filepath"
                    )

                    with gr.Row():
                        src_lang = gr.Dropdown(
                            label="Idioma de Origem",
                            choices=LANGUAGE_OPTIONS,
                            value="en"
                        )
                        tgt_lang = gr.Dropdown(
                            label="Idioma de Destino",
                            choices=LANGUAGE_OPTIONS,
                            value="pt"
                        )

                    with gr.Row():
                        engine = gr.Radio(
                            label="Motor de Tradução",
                            choices=["Neural Fast Translator (Padrão, Gratuito)", "Ollama (IA Local Offline)"],
                            value="Neural Fast Translator (Padrão, Gratuito)"
                        )
                        workers_slider = gr.Slider(
                            label="Trabalhadores simultâneos (Workers)",
                            minimum=1,
                            maximum=10,
                            value=5,
                            step=1
                        )

                    ollama_input = gr.Textbox(
                        label="Nome do Modelo no Ollama (apenas se selecionado IA Local)",
                        value="qwen2.5:latest",
                        placeholder="Ex: qwen2.5:latest, llama3.1:latest",
                        visible=False
                    )

                    def toggle_ollama(choice):
                        return gr.update(visible="Ollama" in choice)

                    engine.change(fn=toggle_ollama, inputs=[engine], outputs=[ollama_input])

                    keep_cache_checkbox = gr.Checkbox(
                        label="Manter cache de PDFs intermediários por capítulo (Modo Depuração)",
                        value=False
                    )

                    translate_btn = gr.Button("🚀 Iniciar Tradução do Livro", variant="primary", size="lg")

                with gr.Column(scale=5):
                    status_box = gr.Markdown("### ℹ️ Status\nSelecione um arquivo `.epub` ao lado e clique em **Iniciar Tradução**.")
                    with gr.Row():
                        pdf_output = gr.File(label="📄 PDF Final Diagramado")
                        epub_output = gr.File(label="📖 EPUB Traduzido")
                    
                    with gr.Row():
                        trans_open_pdf_btn = gr.Button("📄 Abrir PDF no Leitor", variant="secondary")
                        trans_open_epub_btn = gr.Button("📱 Abrir EPUB no Leitor", variant="secondary")
                        trans_open_folder_btn = gr.Button("📂 Abrir na Pasta", variant="secondary")

                    trans_last_pdf = gr.State("")
                    trans_last_epub = gr.State("")

        # ----------------- ABA 2: PDF ESCANEADO (OCR) -----------------
        with gr.TabItem("📷 Digitalizar PDF Escaneado (OCR)", id="tab_ocr"):
            with gr.Row():
                with gr.Column(scale=5):
                    scanned_pdf_input = gr.File(
                        label="Envie o PDF Digitalizado (Foto / Escaneado)",
                        file_types=[".pdf"],
                        type="filepath"
                    )

                    with gr.Row():
                        ocr_title_input = gr.Textbox(
                            label="Título do Livro",
                            placeholder="Ex: Código Limpo (ou vazio para nome do arquivo)"
                        )
                        ocr_author_input = gr.Textbox(
                            label="Autor(a)",
                            placeholder="Ex: Robert C. Martin"
                        )

                    ocr_lang_dropdown = gr.Dropdown(
                        label="Idioma do Documento Escaneado",
                        choices=LANGUAGE_OPTIONS,
                        value="pt"
                    )

                    convert_ocr_btn = gr.Button("⚡ Digitalizar PDF para EPUB Refluxável", variant="primary", size="lg")

                with gr.Column(scale=5):
                    with gr.Group():
                        ocr_status_box = gr.Markdown("### ℹ️ Status do OCR\nEnvie um PDF digitalizado por scanner ou foto e clique em **Digitalizar** para gerar um EPUB com formatação preservada, código consolidado e diagramas recortados.")
                        ocr_epub_output = gr.File(label="📖 EPUB Refluxável Gerado")
                        with gr.Row():
                            ocr_open_epub_btn = gr.Button("📱 Abrir EPUB no Leitor", variant="secondary")
                            ocr_open_folder_btn = gr.Button("📂 Abrir na Pasta", variant="secondary")
                        ocr_last_epub = gr.State("")

        # ----------------- ABA 3: CONVERSOR DE FORMATOS (EPUB <-> PDF) -----------------
        with gr.TabItem("🔄 Conversor de Formatos (EPUB ⟷ PDF)", id="tab_converter"):
            with gr.Tabs():
                # Sub-Aba: EPUB -> PDF
                with gr.TabItem("📱 EPUB ➔ 📄 PDF (A4 Diagramado)"):
                    gr.Markdown("Transforme qualquer livro `.epub` em um PDF diagramado no padrão A4 pronto para leitura e impressão.")
                    with gr.Row():
                        with gr.Column(scale=5):
                            conv_epub_in = gr.File(label="Envie o arquivo .epub", file_types=[".epub"], type="filepath")
                            conv_epub_to_pdf_btn = gr.Button("🚀 Converter EPUB para PDF A4", variant="primary", size="lg")
                        with gr.Column(scale=5):
                            conv_pdf_status = gr.Markdown("### ℹ️ Status\nSelecione um arquivo `.epub` e clique em **Converter**.")
                            conv_pdf_out = gr.File(label="📄 PDF Gerado")
                            with gr.Row():
                                conv_open_pdf_btn = gr.Button("📄 Abrir PDF no Leitor", variant="secondary")
                                conv_open_pdf_folder_btn = gr.Button("📂 Abrir na Pasta", variant="secondary")
                            conv_last_pdf = gr.State("")

                # Sub-Aba: PDF -> EPUB
                with gr.TabItem("📄 PDF ➔ 📱 EPUB (Refluxável Limpo)"):
                    gr.Markdown("Transforme arquivos `.pdf` em formato `.epub` limpo. O sistema detecta automaticamente se o PDF é texto digital ou escaneado (acionando OCR com refino).")
                    with gr.Row():
                        with gr.Column(scale=5):
                            conv_pdf_in = gr.File(label="Envie o arquivo .pdf", file_types=[".pdf"], type="filepath")
                            with gr.Row():
                                conv_title_in = gr.Textbox(label="Título (Opcional)", placeholder="Título da obra")
                                conv_author_in = gr.Textbox(label="Autor (Opcional)", placeholder="Nome do autor")
                            conv_lang_in = gr.Dropdown(label="Idioma", choices=LANGUAGE_OPTIONS, value="pt")
                            conv_pdf_to_epub_btn = gr.Button("⚡ Converter PDF para EPUB", variant="primary", size="lg")
                        with gr.Column(scale=5):
                            conv_epub_status = gr.Markdown("### ℹ️ Status\nSelecione um arquivo `.pdf` e clique em **Converter**.")
                            conv_epub_out = gr.File(label="📱 EPUB Gerado")
                            with gr.Row():
                                conv_open_epub_btn = gr.Button("📱 Abrir EPUB no Leitor", variant="secondary")
                                conv_open_epub_folder_btn = gr.Button("📂 Abrir na Pasta", variant="secondary")
                            conv_last_epub = gr.State("")

        # ----------------- ABA 4: BIBLIOTECA DIGITAL -----------------
        with gr.TabItem("🏛️ Biblioteca Digital", id="tab_library"):
            with gr.Row(variant="panel"):
                with gr.Column(scale=5):
                    gr.Markdown("### 🏛️ Estante Digital Local")
                    gr.Markdown("Seus livros organizados por idioma e categoria com abertura nativa direta no Windows sem duplicar downloads.")
                with gr.Column(scale=7):
                    with gr.Row():
                        filter_cat = gr.Dropdown(
                            label="Filtrar por Categoria",
                            choices=FILTER_CATEGORY_OPTIONS,
                            value="Todos",
                            scale=3
                        )
                        filter_lang = gr.Dropdown(
                            label="Filtrar por Idioma",
                            choices=FILTER_LANG_OPTIONS,
                            value="Todos",
                            scale=3
                        )
                        refresh_btn = gr.Button("🔄 Atualizar Estante", variant="secondary", scale=2)

            # Estante Visual (HTML Card Grid)
            initial_books = get_library_books("Todos", "Todos")
            initial_html = render_books_grid_html(initial_books)
            books_grid = gr.HTML(value=initial_html)

            # Central de Ações Locais Desktop
            initial_choices = [f"[{b['lang'].upper()}] {b['title']} | slug:{b['slug']}" for b in initial_books]
            first_b = initial_books[0] if initial_books else None
            initial_pdf = first_b.get("pdf_path") if first_b and os.path.exists(first_b.get("pdf_path", "")) else None
            initial_epub = first_b.get("epub_path") if first_b and os.path.exists(first_b.get("epub_path", "")) else None
            initial_cat = "📷 Digitalizado (OCR)" if first_b and first_b.get("category") == "ocr" else "🌐 Traduzido"
            initial_info = (
                f"### 📖 {first_b.get('title')}\n- **Categoria:** `{initial_cat}` | **Autor:** {first_b.get('author')}\n- **Páginas:** {first_b.get('pages')} | **Idioma:** {first_b.get('lang', '').upper()}\n- **PDF:** {first_b.get('pdf_size_mb')} MB | **EPUB:** {first_b.get('epub_size_mb')} MB"
                if first_b else "Nenhum livro selecionado."
            )

            gr.Markdown("---")
            gr.Markdown("### ⚡ Central de Ações Locais (Desktop)")
            with gr.Row():
                with gr.Column(scale=6):
                    book_dropdown = gr.Dropdown(
                        label="Selecione uma obra da estante",
                        choices=initial_choices,
                        value=initial_choices[0] if initial_choices else None
                    )
                    selected_info = gr.Markdown(value=initial_info)

                with gr.Column(scale=4):
                    action_pdf_btn = gr.Button("📄 Abrir PDF no Leitor do Windows", variant="primary", size="lg")
                    action_epub_btn = gr.Button("📱 Abrir EPUB no Leitor do Windows", variant="secondary", size="lg")
                    action_folder_btn = gr.Button("📂 Revelar no Windows Explorer", variant="secondary")
                    delete_btn = gr.Button("🗑️ Remover Obra da Estante", variant="stop", size="sm")
                    desktop_feedback = gr.Markdown("")

    # ----------------- EVENT BINDINGS -----------------
    # Aba 1: Tradução
    translate_btn.click(
        fn=translate_book,
        inputs=[epub_input, src_lang, tgt_lang, engine, ollama_input, workers_slider, keep_cache_checkbox],
        outputs=[pdf_output, epub_output, status_box, trans_last_pdf, trans_last_epub, books_grid, book_dropdown],
        show_progress="minimal"
    )
    trans_open_pdf_btn.click(fn=open_file_desktop, inputs=[trans_last_pdf], outputs=[status_box])
    trans_open_epub_btn.click(fn=open_file_desktop, inputs=[trans_last_epub], outputs=[status_box])
    trans_open_folder_btn.click(fn=open_folder_desktop, inputs=[trans_last_pdf], outputs=[status_box])

    # Aba 2: OCR
    convert_ocr_btn.click(
        fn=convert_scanned_pdf,
        inputs=[scanned_pdf_input, ocr_title_input, ocr_author_input, ocr_lang_dropdown],
        outputs=[ocr_epub_output, ocr_status_box, ocr_last_epub, books_grid, book_dropdown],
        show_progress="minimal"
    )
    ocr_open_epub_btn.click(fn=open_file_desktop, inputs=[ocr_last_epub], outputs=[ocr_status_box])
    ocr_open_folder_btn.click(fn=open_folder_desktop, inputs=[ocr_last_epub], outputs=[ocr_status_box])

    # Aba 3: Conversor EPUB -> PDF
    conv_epub_to_pdf_btn.click(
        fn=convert_epub_to_pdf_flow,
        inputs=[conv_epub_in],
        outputs=[conv_pdf_out, conv_pdf_status, conv_last_pdf],
        show_progress="minimal"
    )
    conv_open_pdf_btn.click(fn=open_file_desktop, inputs=[conv_last_pdf], outputs=[conv_pdf_status])
    conv_open_pdf_folder_btn.click(fn=open_folder_desktop, inputs=[conv_last_pdf], outputs=[conv_pdf_status])

    # Aba 3: Conversor PDF -> EPUB
    conv_pdf_to_epub_btn.click(
        fn=convert_pdf_to_epub_flow,
        inputs=[conv_pdf_in, conv_title_in, conv_author_in, conv_lang_in],
        outputs=[conv_epub_out, conv_epub_status, conv_last_epub],
        show_progress="minimal"
    )
    conv_open_epub_btn.click(fn=open_file_desktop, inputs=[conv_last_epub], outputs=[conv_epub_status])
    conv_open_epub_folder_btn.click(fn=open_folder_desktop, inputs=[conv_last_epub], outputs=[conv_epub_status])

    # Aba 4: Biblioteca
    filter_lang.change(
        fn=update_library_view,
        inputs=[filter_lang, filter_cat],
        outputs=[books_grid, book_dropdown, selected_info, desktop_feedback]
    )

    filter_cat.change(
        fn=update_library_view,
        inputs=[filter_lang, filter_cat],
        outputs=[books_grid, book_dropdown, selected_info, desktop_feedback]
    )

    refresh_btn.click(
        fn=update_library_view,
        inputs=[filter_lang, filter_cat],
        outputs=[books_grid, book_dropdown, selected_info, desktop_feedback]
    )

    book_dropdown.change(
        fn=on_select_book,
        inputs=[book_dropdown],
        outputs=[selected_info, desktop_feedback]
    )

    action_pdf_btn.click(
        fn=action_open_selected_pdf,
        inputs=[book_dropdown],
        outputs=[desktop_feedback]
    )

    action_epub_btn.click(
        fn=action_open_selected_epub,
        inputs=[book_dropdown],
        outputs=[desktop_feedback]
    )

    action_folder_btn.click(
        fn=action_open_selected_folder,
        inputs=[book_dropdown],
        outputs=[desktop_feedback]
    )

    delete_btn.click(
        fn=delete_book_from_library,
        inputs=[book_dropdown, filter_lang, filter_cat],
        outputs=[books_grid, book_dropdown, selected_info, desktop_feedback]
    )

if __name__ == "__main__":
    demo.queue()
    app, local_url, _ = demo.launch(
        prevent_thread_lock=True,
        inbrowser=True,
        allowed_paths=[OUTPUT_DIR],
        app_kwargs={"middleware": [Middleware(CleanPathMiddleware)]}
    )

    @app.get("/api/open-file")
    async def api_open_file(path: str):
        try:
            decoded = urllib.parse.unquote(path)
            norm = os.path.normpath(decoded)
            if os.path.exists(norm):
                os.startfile(norm)
                return JSONResponse({"status": "success", "opened": norm})
            return JSONResponse({"status": "error", "message": f"Arquivo não encontrado: {norm}"}, status_code=404)
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    @app.get("/api/open-folder")
    async def api_open_folder(path: str):
        try:
            decoded = urllib.parse.unquote(path)
            norm = os.path.normpath(decoded)
            if os.path.exists(norm):
                if os.path.isdir(norm):
                    os.startfile(norm)
                else:
                    subprocess.Popen(["explorer", f"/select,{norm}"])
                return JSONResponse({"status": "success", "folder": norm})
            return JSONResponse({"status": "error", "message": f"Caminho não encontrado: {norm}"}, status_code=404)
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    demo.block_thread()
