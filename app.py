import os
import sys
import gradio as gr

# Add repository root to pythonpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import TranslationPipeline
from src.core.translator import BingTranslatorEngine, OllamaTranslatorEngine

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

def translate_book(
    epub_file,
    source_lang,
    target_lang,
    engine_choice,
    ollama_model,
    workers,
    progress=gr.Progress()
):
    if not epub_file:
        raise gr.Error("Por favor, selecione ou envie um arquivo .epub!")

    input_path = epub_file.name if hasattr(epub_file, "name") else epub_file
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    progress(0.0, desc="Inicializando pipeline...")

    # Escolha do motor
    if "Ollama" in engine_choice:
        model_name = ollama_model.strip() or "qwen2.5:latest"
        translator = OllamaTranslatorEngine(lang_in=source_lang, lang_out=target_lang, model=model_name)
    else:
        translator = BingTranslatorEngine(lang_in=source_lang, lang_out=target_lang)

    pipeline = TranslationPipeline(
        epub_path=input_path,
        output_dir=output_dir,
        lang_in=source_lang,
        lang_out=target_lang,
        translator=translator,
        max_workers=int(workers)
    )

    def on_progress(percent: float, message: str):
        progress(percent, desc=message)

    final_pdf, final_epub = pipeline.run(progress_callback=on_progress)

    status_msg = f"### Tradução Concluída com Sucesso!\n- **Livro:** {pipeline.parser.metadata.get('title')}\n- **Capítulos processados:** {len(pipeline.parser.spine)}\n- **PDF gerado:** `{os.path.basename(final_pdf)}`\n- **EPUB gerado:** `{os.path.basename(final_epub)}`"

    return final_pdf, final_epub, status_msg

custom_css = """
.main-header {
    text-align: center;
    margin-bottom: 20px;
}
.main-header h1 {
    font-size: 2.3rem;
    font-weight: 700;
    color: #1e293b;
}
.main-header p {
    color: #64748b;
    font-size: 1.1rem;
}
"""

with gr.Blocks(title="epub-pdf-translator", css=custom_css, theme=gr.themes.Soft()) as demo:
    gr.HTML("""
    <div class="main-header">
        <h1>📚 epub-pdf-translator</h1>
        <p>Traduza livros em formato EPUB preservando blocos de código, formatação e imagens, e gere um PDF diagramado pronto para impressão.</p>
    </div>
    """)

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

            translate_btn = gr.Button("🚀 Iniciar Tradução do Livro", variant="primary", size="lg")

        with gr.Column(scale=5):
            status_box = gr.Markdown("### Status\nEnvie um livro e clique no botão acima para iniciar.")
            pdf_output = gr.File(label="📄 Baixar PDF Final Diagramado")
            epub_output = gr.File(label="📖 Baixar EPUB Traduzido")

    translate_btn.click(
        fn=translate_book,
        inputs=[epub_input, src_lang, tgt_lang, engine, ollama_input, workers_slider],
        outputs=[pdf_output, epub_output, status_box]
    )

if __name__ == "__main__":
    demo.queue().launch(inbrowser=True)
