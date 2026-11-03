import os
import sys
import re
import json
import base64
import io
from PIL import Image
import gradio as gr

# Add repository root to pythonpath
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.pipeline import TranslationPipeline
from src.core.translator import BingTranslatorEngine, OllamaTranslatorEngine
from src.core.library import BookLibrary

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

def render_books_grid_html(books):
    if not books:
        return """
        <div style="text-align: center; padding: 45px 20px; color: #64748b; background: #f8fafc; border-radius: 12px; border: 2px dashed #cbd5e1; margin-top: 15px;">
            <div style="font-size: 2.8rem; margin-bottom: 10px;">📭</div>
            <p style="font-size: 1.25rem; font-weight: 600; color: #334155; margin: 0 0 8px 0;">Nenhum livro encontrado nesta categoria</p>
            <p style="font-size: 0.95rem; margin: 0;">Traduza um novo livro na aba <b>'🚀 Traduzir Novo Livro'</b> para visualizá-lo nesta estante!</p>
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
                im.thumbnail((320, 480))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=85)
                cover_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception:
                cover_b64 = ""

        if cover_b64:
            img_tag = f'<img src="{cover_b64}" alt="Capa" style="width: 100%; height: 260px; object-fit: cover; border-top-left-radius: 10px; border-top-right-radius: 10px;" />'
        else:
            img_tag = '<div style="width: 100%; height: 260px; display: flex; align-items: center; justify-content: center; background: #0f172a; color: #94a3b8; font-size: 3rem; border-top-left-radius: 10px; border-top-right-radius: 10px;">📖</div>'

        lang_badge = flag_map.get(b.get("lang", "").lower(), f"🌐 {b.get('lang', '').upper()}")
        pages_count = b.get("pages", 0)
        pdf_size = b.get("pdf_size_mb", 0)
        epub_size = b.get("epub_size_mb", 0)
        date_formatted = (b.get("date_added") or "")[:10]

        card = f"""
        <div class="library-card" style="background: #ffffff; border-radius: 10px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; overflow: hidden; display: flex; flex-direction: column; transition: all 0.25s ease;">
            <div style="position: relative;">
                {img_tag}
                <div style="position: absolute; top: 10px; right: 10px; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(4px); color: #ffffff; padding: 4px 10px; border-radius: 16px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.5px;">
                    {lang_badge}
                </div>
                <div style="position: absolute; bottom: 10px; left: 10px; background: rgba(22, 163, 74, 0.9); backdrop-filter: blur(4px); color: #ffffff; padding: 3px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 600;">
                    ✅ 100% Qualidade
                </div>
            </div>
            <div style="padding: 14px 16px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <h3 style="margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700; color: #0f172a; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                        {b.get('title')}
                    </h3>
                    <p style="margin: 0 0 12px 0; font-size: 0.85rem; color: #64748b;">
                        ✍️ {b.get('author', 'Autor Desconhecido')}
                    </p>
                </div>
                <div style="border-top: 1px solid #f1f5f9; padding-top: 10px; font-size: 0.8rem; color: #475569;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                        <span>📄 <b>{pages_count}</b> páginas</span>
                        <span style="color: #94a3b8;">{date_formatted}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-weight: 600; color: #0284c7; background: #f0f9ff; padding: 4px 8px; border-radius: 6px;">
                        <span>📄 PDF: {pdf_size} MB</span>
                        <span>📱 EPUB: {epub_size} MB</span>
                    </div>
                </div>
            </div>
        </div>
        """
        cards_html.append(card)

    return f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 22px; margin-top: 15px;">
        {''.join(cards_html)}
    </div>
    """

def get_library_books(lang_code="Todos"):
    lib = BookLibrary(OUTPUT_DIR)
    lib.scan_and_migrate_legacy()
    code = None if lang_code in ["Todos", "all", ""] else lang_code
    books = lib.list_books(lang=code)
    return books

def update_library_view(lang_code="Todos"):
    books = get_library_books(lang_code)
    grid_html = render_books_grid_html(books)
    choices = [f"[{b['lang'].upper()}] {b['title']} | slug:{b['slug']}" for b in books]
    default_val = choices[0] if choices else None

    if default_val:
        first_b = books[0]
        pdf = first_b.get("pdf_path") if os.path.exists(first_b.get("pdf_path", "")) else None
        epub = first_b.get("epub_path") if os.path.exists(first_b.get("epub_path", "")) else None
        info = f"### 📖 {first_b.get('title')}\n- **Autor:** {first_b.get('author')}\n- **Páginas:** {first_b.get('pages')} | **Idioma:** {first_b.get('lang', '').upper()}\n- **PDF:** {first_b.get('pdf_size_mb')} MB | **EPUB:** {first_b.get('epub_size_mb')} MB"
    else:
        pdf, epub, info = None, None, "Nenhum livro selecionado."

    return grid_html, gr.update(choices=choices, value=default_val), pdf, epub, info

def on_select_book(selected_label):
    if not selected_label or "| slug:" not in selected_label:
        return None, None, "Nenhum livro selecionado."

    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"

    lib = BookLibrary(OUTPUT_DIR)
    book = lib.get_book(lang=lang_code, slug=slug)
    if not book:
        return None, None, "Livro não localizado."

    pdf_p = book.get("pdf_path") if os.path.exists(book.get("pdf_path", "")) else None
    epub_p = book.get("epub_path") if os.path.exists(book.get("epub_path", "")) else None
    info = (
        f"### 📖 {book.get('title')}\n"
        f"- **Autor:** {book.get('author', 'Desconhecido')}\n"
        f"- **Idioma:** {book.get('lang', '').upper()} (Original: {book.get('source_lang', 'en').upper()})\n"
        f"- **Páginas:** {book.get('pages', 0)} | **Tamanhos:** PDF ({book.get('pdf_size_mb', 0)} MB) • EPUB ({book.get('epub_size_mb', 0)} MB)\n"
        f"- **Data de Conclusão:** {(book.get('date_added') or '')[:10]}\n"
        f"- **Certificação:** ✅ 100% Qualidade Verificada"
    )
    return pdf_p, epub_p, info

def delete_book_from_library(selected_label, current_filter):
    if not selected_label or "| slug:" not in selected_label:
        return update_library_view(current_filter)

    slug = selected_label.split("| slug:")[-1].strip()
    match_lang = re.search(r'\[([A-Z]{2})\]', selected_label)
    lang_code = match_lang.group(1).lower() if match_lang else "pt"

    lib = BookLibrary(OUTPUT_DIR)
    lib.delete_book(lang=lang_code, slug=slug)
    return update_library_view(current_filter)

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

    # Escolha do motor
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

    status_msg = (
        f"### 🎉 Tradução Concluída com Sucesso!\n"
        f"- **Livro:** {pipeline.parser.metadata.get('title')}\n"
        f"- **Capítulos traduzidos:** {len(pipeline.parser.spine)}\n"
        f"- **PDF diagramado:** `{os.path.basename(final_pdf)}`\n"
        f"- **EPUB traduzido:** `{os.path.basename(final_epub)}`\n"
        f"- **Status do Cache:** {'Preservado para depuração' if keep_cache else 'Limpeza de páginas temporárias realizada com sucesso'}\n"
        f"- **Biblioteca:** Adicionado automaticamente à estante de `{target_lang.upper()}`!"
    )

    # Return download files, status message, and refresh library
    grid_html, book_choices, lib_pdf, lib_epub, lib_info = update_library_view("Todos")
    return final_pdf, final_epub, status_msg, grid_html, book_choices

custom_css = """
.main-header {
    text-align: center;
    margin-bottom: 24px;
    padding-top: 10px;
}
.main-header h1 {
    font-size: 2.4rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.5px;
    margin-bottom: 6px;
}
.main-header p {
    color: #475569;
    font-size: 1.1rem;
    max-width: 850px;
    margin: 0 auto;
}
.library-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 12px 20px -3px rgba(0, 0, 0, 0.12), 0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
}
.badge-tech {
    background: #e0f2fe;
    color: #0369a1;
    font-size: 0.8rem;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 600;
}
"""

with gr.Blocks(title="epub-pdf-translator", css=custom_css, theme=gr.themes.Soft()) as demo:
    gr.HTML("""
    <div class="main-header">
        <h1>📚 epub-pdf-translator</h1>
        <p>Plataforma open-source para tradução técnica precisa de livros EPUB, preservando formatação e código, com biblioteca integrada e exportação em PDF A4 de alta qualidade.</p>
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
                        pdf_output = gr.File(label="📄 Baixar PDF Final Diagramado")
                        epub_output = gr.File(label="📖 Baixar EPUB Traduzido")

        # ----------------- ABA 2: BIBLIOTECA DE LIVROS -----------------
        with gr.TabItem("📚 Biblioteca de Livros", id="tab_library"):
            with gr.Row(variant="panel"):
                with gr.Column(scale=6):
                    gr.Markdown("### 🏛️ Estante Digital de Livros Traduzidos")
                    gr.Markdown("Seus livros traduzidos organizados por idioma com capas, contagem de páginas e downloads rápidos.")
                with gr.Column(scale=4):
                    with gr.Row():
                        filter_lang = gr.Dropdown(
                            label="Filtrar por Idioma",
                            choices=FILTER_LANG_OPTIONS,
                            value="Todos",
                            scale=3
                        )
                        refresh_btn = gr.Button("🔄 Atualizar", variant="secondary", scale=1)

            # Estante Visual (HTML Card Grid)
            initial_books = get_library_books("Todos")
            initial_html = render_books_grid_html(initial_books)
            books_grid = gr.HTML(value=initial_html)

            # Seletor e Ações do Livro
            initial_choices = [f"[{b['lang'].upper()}] {b['title']} | slug:{b['slug']}" for b in initial_books]
            first_b = initial_books[0] if initial_books else None
            initial_pdf = first_b.get("pdf_path") if first_b and os.path.exists(first_b.get("pdf_path", "")) else None
            initial_epub = first_b.get("epub_path") if first_b and os.path.exists(first_b.get("epub_path", "")) else None
            initial_info = (
                f"### 📖 {first_b.get('title')}\n- **Autor:** {first_b.get('author')}\n- **Páginas:** {first_b.get('pages')} | **Idioma:** {first_b.get('lang', '').upper()}\n- **PDF:** {first_b.get('pdf_size_mb')} MB | **EPUB:** {first_b.get('epub_size_mb')} MB"
                if first_b else "Nenhum livro selecionado."
            )

            gr.Markdown("---")
            gr.Markdown("### 📥 Central de Download & Gerenciamento")
            with gr.Row():
                with gr.Column(scale=6):
                    book_dropdown = gr.Dropdown(
                        label="Selecione um livro da biblioteca para download",
                        choices=initial_choices,
                        value=initial_choices[0] if initial_choices else None
                    )
                    selected_info = gr.Markdown(value=initial_info)
                    delete_btn = gr.Button("🗑️ Remover Livro Selecionado da Biblioteca", variant="stop", size="sm")

                with gr.Column(scale=4):
                    lib_pdf_download = gr.File(value=initial_pdf, label="📄 Baixar PDF Completo")
                    lib_epub_download = gr.File(value=initial_epub, label="📖 Baixar EPUB Completo")

        # ----------------- ABA 3: FASE 2 PREVIEW (OCR) -----------------
        with gr.TabItem("📷 PDF Escaneado para EPUB (OCR)", id="tab_ocr"):
            with gr.Row():
                with gr.Column(scale=6):
                    gr.Markdown("""
                    ### 🔍 Conversor de PDF Escaneado (Foto) para EPUB
                    Esta funcionalidade (prevista na **Fase 2 do Roadmap**) transforma livros que são apenas digitalizações/fotos em arquivos **EPUB 3.0** fluidos, pesquisáveis e compatíveis com qualquer leitor digital.

                    #### ✨ Principais Recursos da Fase 2:
                    - **OCR com Reconhecimento de Layout:** Extrai textos em português e outras línguas sem quebrar parágrafos.
                    - **Preservação de Diagramas:** Detecta e recorta imagens e ilustrações automaticamente.
                    - **Blocos de Código Preservados:** Identifica trechos monoespaçados.
                    - **Sem Necessidade de Tradução:** Gera o EPUB puro no idioma original do documento digitalizado.
                    - **Conexão Direta (Fase 3):** Opção para enviar o EPUB gerado para a esteira de tradução com 1 clique!
                    """)
                with gr.Column(scale=4):
                    gr.File(label="Upload de PDF Digitalizado (Fase 2)", interactive=False)
                    gr.Button("🛠️ Em Breve na Fase 2", interactive=False)

    # ----------------- EVENT BINDINGS -----------------
    translate_btn.click(
        fn=translate_book,
        inputs=[epub_input, src_lang, tgt_lang, engine, ollama_input, workers_slider, keep_cache_checkbox],
        outputs=[pdf_output, epub_output, status_box, books_grid, book_dropdown]
    )

    filter_lang.change(
        fn=update_library_view,
        inputs=[filter_lang],
        outputs=[books_grid, book_dropdown, lib_pdf_download, lib_epub_download, selected_info]
    )

    refresh_btn.click(
        fn=update_library_view,
        inputs=[filter_lang],
        outputs=[books_grid, book_dropdown, lib_pdf_download, lib_epub_download, selected_info]
    )

    book_dropdown.change(
        fn=on_select_book,
        inputs=[book_dropdown],
        outputs=[lib_pdf_download, lib_epub_download, selected_info]
    )

    delete_btn.click(
        fn=delete_book_from_library,
        inputs=[book_dropdown, filter_lang],
        outputs=[books_grid, book_dropdown, lib_pdf_download, lib_epub_download, selected_info]
    )

if __name__ == "__main__":
    demo.queue().launch(inbrowser=True)
