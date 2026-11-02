import os
import sys
import argparse

# Add repository root to pythonpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import TranslationPipeline
from src.core.translator import BingTranslatorEngine, OllamaTranslatorEngine

def main():
    parser = argparse.ArgumentParser(
        description="epub-pdf-translator: Translate EPUB books and compile to structured, print-ready PDFs."
    )
    parser.add_argument("epub_file", help="Path to the input .epub file")
    parser.add_argument("-li", "--lang-in", default="en", help="Source language code (default: en)")
    parser.add_argument("-lo", "--lang-out", default="pt", help="Target language code (default: pt)")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory to save output PDF and EPUB")
    parser.add_argument("-w", "--workers", type=int, default=5, help="Number of concurrent translation workers")
    parser.add_argument("--ollama", help="Use local Ollama model instead of default engine (e.g., qwen2.5:latest)")

    args = parser.parse_args()

    if not os.path.exists(args.epub_file):
        print(f"Error: File not found: {args.epub_file}", file=sys.stderr)
        sys.exit(1)

    print("==================================================")
    print("      epub-pdf-translator: Book Translation Engine")
    print("==================================================")
    print(f"Book:   {args.epub_file}")
    print(f"From:   {args.lang_in} -> To: {args.lang_out}")
    print(f"Output: {args.output_dir}")

    if args.ollama:
        print(f"Engine: Ollama (Local AI Model: {args.ollama})")
        translator = OllamaTranslatorEngine(lang_in=args.lang_in, lang_out=args.lang_out, model=args.ollama)
    else:
        print("Engine: Neural Fast Translator (Default)")
        translator = BingTranslatorEngine(lang_in=args.lang_in, lang_out=args.lang_out)

    pipeline = TranslationPipeline(
        epub_path=args.epub_file,
        output_dir=args.output_dir,
        lang_in=args.lang_in,
        lang_out=args.lang_out,
        translator=translator,
        max_workers=args.workers
    )

    def on_progress(percent: float, message: str):
        bar_len = 30
        filled = int(bar_len * percent)
        bar = "=" * filled + "-" * (bar_len - filled)
        print(f"\r[{bar}] {percent*100:5.1f}% | {message}", end="", flush=True)

    print("\nStarting translation...")
    final_pdf, final_epub = pipeline.run(progress_callback=on_progress)
    print("\n")
    print("Translation completed successfully!")
    print(f"  Master PDF:  {final_pdf}")
    print(f"  Master EPUB: {final_epub}")
    print("==================================================")

if __name__ == "__main__":
    main()
