#!/usr/bin/env python3
"""
DSpace Simple Archive Format (SAF) Builder
Replaces the Java/Maven SAFBuilder with a simple, dependency-free Python script.

Usage:
    python saf_builder.py metadata.csv
    python saf_builder.py metadata.csv --output MyOutputDir

CSV format:
    - Must have a 'filename' column referencing your digital objects
    - Other columns named as DSpace metadata fields, e.g.:
        dc.title
        dc.date.issued
        dc.publisher[en]
        dc.subject.lcsh[en]
"""

import csv
import os
import re
import sys
import shutil
import zipfile
import argparse
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a DSpace Simple Archive Format (SAF) package from a CSV file."
    )
    parser.add_argument("csv_file", help="Path to the metadata CSV file")
    parser.add_argument(
        "--output", "-o",
        default="SimpleArchiveFormat",
        help="Output directory name (default: SimpleArchiveFormat)"
    )
    return parser.parse_args()


def parse_dc_field(header):
    """
    Parse a CSV column header into Dublin Core components.

    Examples:
        'dc.title'              -> element='title', qualifier=None, language=None
        'dc.date.issued'        -> element='date',  qualifier='issued', language=None
        'dc.publisher[en]'      -> element='publisher', qualifier=None, language='en'
        'dc.subject.lcsh[en]'  -> element='subject', qualifier='lcsh', language='en'

    Returns a dict or None if header is not a DC field.
    """
    if not header.startswith("dc."):
        return None

    # Extract language qualifier e.g. [en]
    language = None
    lang_match = re.search(r'\[([^\]]+)\]', header)
    if lang_match:
        language = lang_match.group(1)
        header = header[:lang_match.start()]

    # Strip the 'dc.' prefix and split element/qualifier
    field = header[3:]  # remove 'dc.'
    parts = field.split(".", 1)
    element = parts[0]
    qualifier = parts[1] if len(parts) > 1 else None

    return {"element": element, "qualifier": qualifier, "language": language}


def build_dublin_core_xml(metadata_fields):
    """
    Build a dublin_core.xml ElementTree from a list of field dicts.
    Each dict has keys: element, qualifier, language, value.
    """
    root = Element("dublin_core")
    root.set("schema", "dc")

    for field in metadata_fields:
        dcvalue = SubElement(root, "dcvalue")
        dcvalue.set("element", field["element"])
        if field["qualifier"]:
            dcvalue.set("qualifier", field["qualifier"])
        if field["language"]:
            dcvalue.set("language", field["language"])
        dcvalue.text = field["value"]

    indent(root, space="  ")
    return ElementTree(root)


def validate_row(row_num, record, headers, filename_col, files_dir):
    """Validate a CSV row. Returns a list of error strings."""
    errors = []

    if len(record) != len(headers):
        errors.append(f"Row {row_num}: has {len(record)} columns, expected {len(headers)}")
        return errors  # can't continue validating this row

    filename = record[filename_col].strip()
    if not filename:
        errors.append(f"Row {row_num}: 'filename' column is empty")
    else:
        source = files_dir / filename
        if not source.exists():
            errors.append(f"Row {row_num}: file not found: {source}")

    return errors


def build_saf(csv_path, output_dir, log=print):
    csv_path = Path(csv_path).resolve()
    files_dir = csv_path.parent
    output_dir = Path(output_dir)

    log(f"CSV file  : {csv_path}")
    log(f"Files dir : {files_dir}")
    log(f"Output    : {output_dir.resolve()}")

    # --- Read CSV ---
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        if headers is None:
            raise ValueError("CSV file is empty.")
        rows = list(reader)

    headers = [h.strip() for h in headers]

    # Find filename column
    try:
        filename_col = headers.index("filename")
    except ValueError:
        raise ValueError("CSV must have a 'filename' column.")

    # --- Validate all rows up front ---
    log(f"Validating {len(rows)} rows...")
    all_errors = []
    for i, record in enumerate(rows):
        errors = validate_row(i + 2, record, headers, filename_col, files_dir)
        all_errors.extend(errors)

    if all_errors:
        msg = "Validation failed — fix these issues before building:\n" + \
              "\n".join(f"  ✗ {err}" for err in all_errors)
        raise ValueError(msg)

    log(f"✓ All {len(rows)} rows valid")

    # --- Create output directory ---
    if output_dir.exists():
        log(f"WARNING: Output directory '{output_dir}' already exists. Overwriting.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # --- Build SAF structure ---
    for item_num, record in enumerate(rows):
        item_dir = output_dir / f"item_{item_num:03d}"
        item_dir.mkdir()

        filename = record[filename_col].strip()
        source = files_dir / filename

        # Copy digital object
        shutil.copy2(source, item_dir / filename)

        # Write contents file
        (item_dir / "contents").write_text(filename + "\n", encoding="utf-8")

        # Build metadata fields list
        metadata_fields = []
        for col_idx, header in enumerate(headers):
            if col_idx == filename_col:
                continue
            value = record[col_idx].strip()
            if not value:
                continue
            parsed = parse_dc_field(header)
            if parsed:
                metadata_fields.append({**parsed, "value": value})

        # Write dublin_core.xml
        tree = build_dublin_core_xml(metadata_fields)
        dc_path = item_dir / "dublin_core.xml"
        with open(dc_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(f, encoding="unicode", xml_declaration=False)
            f.write("\n")

        log(f"  ✓ item_{item_num:03d}  {filename}")

    log(f"✓ Done — {len(rows)} items written to '{output_dir}/'")

    # --- Zip the output directory ---
    zip_path = output_dir.parent / (output_dir.name + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in output_dir.rglob("*"):
            zf.write(file, file.relative_to(output_dir.parent))
    log(f"✓ Zipped  → {zip_path.name}")


if __name__ == "__main__":
    args = parse_args()
    try:
        build_saf(args.csv_file, args.output)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
