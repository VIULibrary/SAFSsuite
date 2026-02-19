#!/usr/bin/env python3

#Inverts colors in PDF files - the COW pdfs are white text on black background this scripts reverses that.


#usage: "python re-inverter.py 1935 --recursive"

import fitz  # PyMuPDF
from pathlib import Path
import sys

def invert_pdf(input_path, output_path=None, overwrite=True):
    """Invert colors in a PDF file."""
    if output_path is None:
        if overwrite:
            output_path = input_path
        else:
            # Add _inverted before .pdf extension
            output_path = input_path.parent / f"{input_path.stem}_inverted{input_path.suffix}"
    
    try:
        doc = fitz.open(input_path)
        new_doc = fitz.open()  # Create new empty PDF
        
        for page in doc:
            # Get the page as a pixmap (image)
            pix = page.get_pixmap()
            
            # Invert colors
            pix.invert_irect(pix.irect)
            
            # Create a new page with the same dimensions
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            
            # Insert the inverted image
            new_page.insert_image(new_page.rect, pixmap=pix)
        
        new_doc.save(output_path)
        new_doc.close()
        doc.close()

        return True, f'{input_path.name} → {output_path.name}'

    except Exception as e:
        return False, f'Error processing {input_path.name}: {e}'

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Invert colors in PDF files')
    parser.add_argument('path', help='PDF file or directory to process')
    parser.add_argument('--keep-original', action='store_true', 
                       help='Create new _inverted files instead of overwriting (default: overwrite)')
    parser.add_argument('--recursive', '-r', action='store_true',
                       help='Process directories recursively')
    
    args = parser.parse_args()
    
    path = Path(args.path)
    
    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)
    
    # Collect PDF files
    pdf_files = []
    if path.is_file():
        if path.suffix.lower() == '.pdf':
            pdf_files = [path]
        else:
            print(f"Error: {path} is not a PDF file")
            sys.exit(1)
    else:
        if args.recursive:
            pdf_files = list(path.rglob('*.pdf'))
        else:
            pdf_files = list(path.glob('*.pdf'))
    
    if not pdf_files:
        print("No PDF files found")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF file(s)")
    
    # Determine if we're overwriting (default) or keeping originals
    overwrite = not args.keep_original
    
    if overwrite:
        response = input("⚠️  Hold up! This will OVERWRITE original files. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled")
            sys.exit(0)
    
    success_count = 0
    for pdf_file in pdf_files:
        ok, msg = invert_pdf(pdf_file, overwrite=overwrite)
        print(f"{'✅' if ok else '❌'} {msg}")
        if ok:
            success_count += 1
    
    print(f"\n✅ Successfully inverted {success_count}/{len(pdf_files)} files")

if __name__ == '__main__':
    main()