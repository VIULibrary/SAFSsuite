#!/usr/bin/env python3

# SAFSuite — CSV Validator and PDF Reverter

import csv
import os
import re
import threading
from pathlib import Path
from collections import defaultdict
import flet as ft
from Deconstructed.reverter import invert_pdf
from Deconstructed.safBuilder import build_saf
from Deconstructed.stackimporter import upload_directory, check_auth


# ── CSV validation logic ──────────────────────────────────────────────────────

def find_csv_and_pdfs(base_dir):
    """Find all directories with CSV files and PDFs at any level."""
    results = []
    base_path = Path(base_dir)
    
    # Check if the selected directory itself contains CSV files
    direct_csvs = list(base_path.glob("*.csv"))
    if direct_csvs:
        pdf_files = set(f.name for f in base_path.glob("*.pdf"))
        results.append({
            'month_dir': base_path,
            'csv_file': direct_csvs[0],
            'pdf_files': pdf_files
        })
    
    # Find all directories that contain CSV files
    processed_dirs = {base_path} if direct_csvs else set()
    
    for csv_file in sorted(base_path.rglob("*.csv")):
        csv_dir = csv_file.parent
        
        # Skip if we already processed this directory
        if csv_dir in processed_dirs:
            continue
            
        processed_dirs.add(csv_dir)
        
        # Get all CSV and PDF files in this directory
        csv_files = list(csv_dir.glob("*.csv"))
        if csv_files:
            pdf_files = set(f.name for f in csv_dir.glob("*.pdf"))
            results.append({
                'month_dir': csv_dir,
                'csv_file': csv_files[0],
                'pdf_files': pdf_files
            })
    
    return results


def validate_csv_against_pdfs(csv_file, pdf_files, month_dir):
    """Validate CSV entries against actual PDF files."""
    errors = []
    csv_filenames = []

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            if 'filename' not in reader.fieldnames:
                return [{
                    'type': 'CRITICAL',
                    'message': f'No "filename" column found in CSV. Columns: {reader.fieldnames}'
                }]

            for row_num, row in enumerate(reader, start=2):
                filename = row.get('filename', '').strip()

                if not filename:
                    errors.append({
                        'type': 'EMPTY',
                        'row': row_num,
                        'message': f'Row {row_num}: Empty filename field'
                    })
                    continue

                csv_filenames.append(filename)

                if filename not in pdf_files:
                    errors.append({
                        'type': 'MISSING_PDF',
                        'row': row_num,
                        'filename': filename,
                        'message': f'Row {row_num}: "{filename}" not found in directory'
                    })

    except Exception as e:
        return [{'type': 'ERROR', 'message': f'Error reading CSV: {str(e)}'}]

    csv_set = set(csv_filenames)
    for pdf in sorted(pdf_files - csv_set):
        errors.append({
            'type': 'UNLISTED_PDF',
            'filename': pdf,
            'message': f'PDF exists but not in CSV: "{pdf}"'
        })

    return errors


# ── CSV Validator tab ─────────────────────────────────────────────────────────

def build_validator_tab(page: ft.Page):
    selected_path = ft.Ref[ft.Text]()
    results_col = ft.Ref[ft.Column]()
    summary_container = ft.Ref[ft.Container]()
    summary_text = ft.Ref[ft.Text]()
    validate_btn = ft.Ref[ft.ElevatedButton]()

    def on_dir_selected(e: ft.FilePickerResultEvent):
        if e.path:
            selected_path.current.value = e.path
            selected_path.current.color = ft.Colors.WHITE
            validate_btn.current.disabled = False
            page.update()

    file_picker = ft.FilePicker(on_result=on_dir_selected)
    page.overlay.append(file_picker)

    def run_validation(e):
        base_dir = selected_path.current.value
        if not base_dir or base_dir == "No directory selected":
            return

        results_col.current.controls.clear()
        summary_container.current.visible = False
        validate_btn.current.disabled = True
        page.update()

        base_path = Path(base_dir)
        if not base_path.exists():
            results_col.current.controls.append(
                ft.Text(f"Error: Directory '{base_dir}' does not exist", color=ft.Colors.RED)
            )
            validate_btn.current.disabled = False
            page.update()
            return

        month_data = find_csv_and_pdfs(base_dir)
        if not month_data:
            results_col.current.controls.append(
                ft.Text("No CSV files found in selected directory or subdirectories.", color=ft.Colors.ORANGE)
            )
            validate_btn.current.disabled = False
            page.update()
            return

        total_errors = 0
        error_summary = defaultdict(int)

        for data in month_data:
            month_dir = data['month_dir']
            csv_file = data['csv_file']
            pdf_files = data['pdf_files']

            errors = validate_csv_against_pdfs(csv_file, pdf_files, month_dir)

            # Create meaningful directory label based on relative path from base
            try:
                rel_path = month_dir.relative_to(base_path)
                if rel_path == Path('.'):
                    # Selected directory itself
                    dir_label_text = f"{base_path.name} (selected directory)"
                else:
                    # Subdirectory - show parent/current structure
                    path_parts = rel_path.parts
                    if len(path_parts) == 1:
                        dir_label_text = f"{base_path.name} / {path_parts[0]}"
                    else:
                        dir_label_text = f"{path_parts[-2]} / {path_parts[-1]}"
            except ValueError:
                # Fallback if path math fails
                dir_label_text = f"{month_dir.parent.name} / {month_dir.name}"
                
            dir_label = ft.Text(
                dir_label_text,
                weight=ft.FontWeight.BOLD,
                size=14,
            )
            meta_row = ft.Row([
                ft.Text(f"CSV: {csv_file.name}", color=ft.Colors.BLUE_200, size=12),
                ft.Text(f"PDFs found: {len(pdf_files)}", color=ft.Colors.BLUE_200, size=12),
            ], spacing=16)

            error_controls = []
            if errors:
                for error in errors:
                    error_type = error['type']
                    error_summary[error_type] += 1
                    total_errors += 1

                    if error_type == 'MISSING_PDF':
                        color, icon = ft.Colors.RED_400, ft.Icons.CANCEL
                    elif error_type == 'CRITICAL':
                        color, icon = ft.Colors.RED_700, ft.Icons.ERROR
                    else:
                        color, icon = ft.Colors.ORANGE_400, ft.Icons.WARNING

                    error_controls.append(
                        ft.Row([
                            ft.Icon(icon, color=color, size=14),
                            ft.Text(error['message'], color=color, size=12),
                        ], spacing=6)
                    )
                border_color = ft.Colors.RED_900
            else:
                error_controls.append(
                    ft.Row([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_400, size=14),
                        ft.Text("All files validated", color=ft.Colors.GREEN_400, size=12),
                    ], spacing=6)
                )
                border_color = ft.Colors.GREEN_900

            results_col.current.controls.append(
                ft.Container(
                    content=ft.Column(
                        [dir_label, meta_row, ft.Divider(height=6, color=ft.Colors.GREY_800)] + error_controls,
                        spacing=4,
                    ),
                    padding=12,
                    margin=ft.margin.only(bottom=8),
                    border=ft.border.all(1, border_color),
                    border_radius=8,
                )
            )

        if total_errors == 0:
            summary_color = ft.Colors.GREEN_400
            summary_bg = ft.Colors.GREEN_900
            summary_msg = f"All {len(month_data)} directories validated successfully — no errors found."
        else:
            summary_color = ft.Colors.ORANGE_400
            summary_bg = ft.Colors.ORANGE_900
            breakdown = "   |   ".join(f"{k}: {v}" for k, v in sorted(error_summary.items()))
            summary_msg = (
                f"{len(month_data)} directories scanned   |   "
                f"{total_errors} total errors   |   {breakdown}"
            )

        summary_text.current.value = summary_msg
        summary_text.current.color = summary_color
        summary_container.current.bgcolor = summary_bg
        summary_container.current.visible = True
        validate_btn.current.disabled = False
        page.update()

    return ft.Container(
        expand=True,
        padding=20,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                ft.Text("CSV Validator", size=22, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Validates CSV filename entries against actual PDF files at any directory level.",
                    color=ft.Colors.GREY_400,
                    size=13,
                ),
                ft.Divider(height=20),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Choose Directory",
                            icon=ft.Icons.FOLDER_OPEN,
                            on_click=lambda _: file_picker.get_directory_path(),
                        ),
                        ft.Text(
                            "No directory selected",
                            ref=selected_path,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.ElevatedButton(
                    "Validate",
                    ref=validate_btn,
                    icon=ft.Icons.PLAY_ARROW,
                    on_click=run_validation,
                    disabled=True,
                ),
                ft.Divider(height=16),
                ft.Container(
                    ref=summary_container,
                    content=ft.Text("", ref=summary_text, size=13, weight=ft.FontWeight.W_500),
                    padding=ft.padding.symmetric(horizontal=14, vertical=10),
                    border_radius=8,
                    visible=False,
                ),
                ft.Column(ref=results_col, spacing=0),
            ],
        ),
    )


# ── PDF Reverter tab ───────────────────────────────────────────────────────

def build_inverter_tab(page: ft.Page):
    selected_path = ft.Ref[ft.Text]()
    pdf_count_text = ft.Ref[ft.Text]()
    overwrite_warning = ft.Ref[ft.Container]()
    invert_btn = ft.Ref[ft.ElevatedButton]()
    progress_col = ft.Ref[ft.Column]()
    summary_container = ft.Ref[ft.Container]()
    summary_text = ft.Ref[ft.Text]()

    recursive_switch = ft.Switch(label="Recursive", value=True)
    keep_original_switch = ft.Switch(label="Keep originals (create _inverted copies)", value=False)

    current_dir = {"path": None, "pdf_files": []}

    def refresh_pdf_count():
        base = current_dir["path"]
        if not base:
            return
        path = Path(base)
        if recursive_switch.value:
            pdfs = list(path.rglob("*.pdf"))
        else:
            pdfs = list(path.glob("*.pdf"))
        current_dir["pdf_files"] = pdfs
        count = len(pdfs)
        if count == 0:
            pdf_count_text.current.value = "No PDF files found in selected directory."
            pdf_count_text.current.color = ft.Colors.ORANGE_400
            invert_btn.current.disabled = True
        else:
            pdf_count_text.current.value = f"{count} PDF file{'s' if count != 1 else ''} found."
            pdf_count_text.current.color = ft.Colors.BLUE_200
            invert_btn.current.disabled = False
        page.update()

    def on_dir_selected(e: ft.FilePickerResultEvent):
        if e.path:
            current_dir["path"] = e.path
            selected_path.current.value = e.path
            selected_path.current.color = ft.Colors.WHITE
            refresh_pdf_count()

    file_picker = ft.FilePicker(on_result=on_dir_selected)
    page.overlay.append(file_picker)

    def on_recursive_change(e):
        refresh_pdf_count()

    def on_keep_original_change(e):
        overwrite_warning.current.visible = not keep_original_switch.value
        page.update()

    recursive_switch.on_change = on_recursive_change
    keep_original_switch.on_change = on_keep_original_change

    def run_inversion(e):
        pdf_files = current_dir["pdf_files"]
        if not pdf_files:
            return

        progress_col.current.controls.clear()
        summary_container.current.visible = False
        invert_btn.current.disabled = True
        page.update()

        overwrite = not keep_original_switch.value

        def worker():
            success_count = 0
            for pdf_path in pdf_files:
                ok, msg = invert_pdf(pdf_path, overwrite=overwrite)
                color = ft.Colors.GREEN_400 if ok else ft.Colors.RED_400
                icon = ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL
                if ok:
                    success_count += 1
                progress_col.current.controls.append(
                    ft.Row([
                        ft.Icon(icon, color=color, size=14),
                        ft.Text(msg, color=color, size=12),
                    ], spacing=6)
                )
                page.update()

            total = len(pdf_files)
            if success_count == total:
                s_color = ft.Colors.GREEN_400
                s_bg = ft.Colors.GREEN_900
                s_msg = f"Done — {success_count}/{total} files inverted successfully."
            else:
                s_color = ft.Colors.ORANGE_400
                s_bg = ft.Colors.ORANGE_900
                s_msg = f"Finished with errors — {success_count}/{total} files succeeded."

            summary_text.current.value = s_msg
            summary_text.current.color = s_color
            summary_container.current.bgcolor = s_bg
            summary_container.current.visible = True
            invert_btn.current.disabled = False
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    return ft.Container(
        expand=True,
        padding=20,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                ft.Text("PDF Reverter", size=22, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Reverts colors in PDF files (white-on-black → black-on-white).",
                    color=ft.Colors.GREY_400,
                    size=13,
                ),
                ft.Divider(height=20),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Choose Directory",
                            icon=ft.Icons.FOLDER_OPEN,
                            on_click=lambda _: file_picker.get_directory_path(),
                        ),
                        ft.Text(
                            "No directory selected",
                            ref=selected_path,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row([recursive_switch, keep_original_switch], spacing=24),
                ft.Text("", ref=pdf_count_text, size=13),
                ft.Container(
                    ref=overwrite_warning,
                    content=ft.Row([
                        ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ORANGE_400, size=16),
                        ft.Text(
                            "Overwrite mode: original files will be replaced.",
                            color=ft.Colors.ORANGE_400,
                            size=13,
                        ),
                    ], spacing=8),
                    padding=ft.padding.symmetric(horizontal=14, vertical=8),
                    bgcolor=ft.Colors.ORANGE_900,
                    border_radius=6,
                    visible=True,
                ),
                ft.ElevatedButton(
                    "Invert PDFs",
                    ref=invert_btn,
                    icon=ft.Icons.INVERT_COLORS,
                    on_click=run_inversion,
                    disabled=True,
                ),
                ft.Divider(height=16),
                ft.Container(
                    ref=summary_container,
                    content=ft.Text("", ref=summary_text, size=13, weight=ft.FontWeight.W_500),
                    padding=ft.padding.symmetric(horizontal=14, vertical=10),
                    border_radius=8,
                    visible=False,
                ),
                ft.Column(ref=progress_col, spacing=2),
            ],
        ),
    )


# ── SAF Builder tab ───────────────────────────────────────────────────────────

def build_saf_tab(page: ft.Page):
    source_path = ft.Ref[ft.Text]()
    output_path = ft.Ref[ft.Text]()
    csv_count_text = ft.Ref[ft.Text]()
    build_btn = ft.Ref[ft.ElevatedButton]()
    progress_col = ft.Ref[ft.Column]()



    state = {"source": None, "output": None, "csv_entries": []}
    output_preview = ft.Ref[ft.Text]()

    def refresh_output_preview():
        if state["source"] and state["output"]:
            source_name = Path(state["source"]).name
            full = Path(state["output"]) / f"{source_name}_SAF_Output"
            output_preview.current.value = f"Output will be written to: {full}"
            output_preview.current.color = ft.Colors.BLUE_200
        else:
            output_preview.current.value = ""

    def refresh_build_btn():
        has_csvs = len(state["csv_entries"]) > 0
        build_btn.current.disabled = not (state["source"] and state["output"] and has_csvs)

    def scan_csvs(base_dir):
        """Return list of (csv_path, parent_name, dir_name) for each directory with a CSV."""
        entries = []
        base_path = Path(base_dir)
        
        # Check if the selected directory itself contains CSV files
        direct_csvs = list(base_path.glob("*.csv"))
        if direct_csvs:
            entries.append((direct_csvs[0], base_path.parent.name, base_path.name))
        
        # Recursively search for CSV files in subdirectories
        for csv_file in sorted(base_path.rglob("*.csv")):
            csv_dir = csv_file.parent
            # Skip if we already found this directory
            if any(entry[0].parent == csv_dir for entry in entries):
                continue
            
            # Create meaningful parent/directory names based on relative path from base
            try:
                rel_path = csv_dir.relative_to(base_path)
                path_parts = rel_path.parts
                
                if len(path_parts) == 1:
                    # Direct subdirectory: base_name / dir_name
                    parent_name = base_path.name
                    dir_name = path_parts[0]
                elif len(path_parts) >= 2:
                    # Nested: parent_dir / current_dir
                    parent_name = path_parts[-2]
                    dir_name = path_parts[-1]
                else:
                    # Shouldn't happen, but fallback
                    parent_name = "unknown"
                    dir_name = csv_dir.name
                    
                entries.append((csv_file, parent_name, dir_name))
                    
            except ValueError:
                # csv_file is not relative to base_path (shouldn't happen with rglob)
                continue
                
        return entries

    def on_source_selected(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        state["source"] = e.path
        source_path.current.value = e.path
        source_path.current.color = ft.Colors.WHITE

        entries = scan_csvs(e.path)
        state["csv_entries"] = entries
        count = len(entries)
        if count == 0:
            csv_count_text.current.value = "No CSVs found in selected directory or subdirectories."
            csv_count_text.current.color = ft.Colors.ORANGE_400
        else:
            dirs = "directory" if count == 1 else "directories"
            csv_count_text.current.value = f"{count} CSV file{'s' if count != 1 else ''} found across {count} {dirs}."
            csv_count_text.current.color = ft.Colors.BLUE_200

        refresh_output_preview()
        refresh_build_btn()
        page.update()

    def on_output_selected(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        state["output"] = e.path
        output_path.current.value = e.path
        output_path.current.color = ft.Colors.WHITE
        refresh_output_preview()
        refresh_build_btn()
        page.update()

    source_picker = ft.FilePicker(on_result=on_source_selected)
    output_picker = ft.FilePicker(on_result=on_output_selected)
    page.overlay.extend([source_picker, output_picker])

    def run_build(e):
        entries = state["csv_entries"]
        if not entries or not state["output"]:
            return

        progress_col.current.controls.clear()
        build_btn.current.disabled = True
        page.update()

        output_base = Path(state["output"]) / f"{Path(state['source']).name}_SAF_Output"
        output_name = "SimpleArchiveFormat"

        def log_line(msg, color=ft.Colors.GREY_300):
            progress_col.current.controls.append(
                ft.Text(msg, size=12, color=color, font_family="monospace")
            )
            page.update()

        def worker():
            # Insert summary placeholder at position 0 so it stays at the top of the log
            summary_label = ft.Text(
                "Building…", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400
            )
            summary_box = ft.Container(
                content=summary_label,
                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                border_radius=8,
                bgcolor=ft.Colors.GREY_900,
                margin=ft.margin.only(bottom=8),
            )
            progress_col.current.controls.insert(0, summary_box)
            page.update()

            success_count = 0
            for csv_path, parent_name, dir_name in entries:
                output_dir = output_base / parent_name / dir_name / output_name
                header = f"{parent_name} / {dir_name}  —  {csv_path.name}"
                progress_col.current.controls.append(
                    ft.Container(
                        content=ft.Text(header, size=13, weight=ft.FontWeight.BOLD),
                        margin=ft.margin.only(top=10, bottom=2),
                    )
                )
                page.update()

                try:
                    build_saf(csv_path, output_dir, log=lambda msg: log_line(msg))
                    success_count += 1
                except ValueError as err:
                    for line in str(err).splitlines():
                        log_line(line, color=ft.Colors.RED_400)
                except Exception as err:
                    log_line(f"Unexpected error: {err}", color=ft.Colors.RED_400)

            total = len(entries)
            if success_count == total:
                s_color = ft.Colors.GREEN_400
                s_bg = ft.Colors.GREEN_900
                s_msg = f"Done — {success_count}/{total} SAF packages built successfully."
            else:
                s_color = ft.Colors.ORANGE_400
                s_bg = ft.Colors.ORANGE_900
                s_msg = f"Finished with errors — {success_count}/{total} packages succeeded."

            summary_label.value = s_msg
            summary_label.color = s_color
            summary_box.bgcolor = s_bg
            build_btn.current.disabled = False
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    return ft.Container(
        expand=True,
        padding=20,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                ft.Text("SAF Builder", size=22, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Builds DSpace Simple Archive Format packages from CSV metadata files at any directory level.",
                    color=ft.Colors.GREY_400,
                    size=13,
                ),
                ft.Divider(height=20),
                ft.Text("Source directory", size=12, color=ft.Colors.GREY_500),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Choose Source",
                            icon=ft.Icons.FOLDER_OPEN,
                            on_click=lambda _: source_picker.get_directory_path(),
                        ),
                        ft.Text(
                            "No directory selected",
                            ref=source_path,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("", ref=csv_count_text, size=13),
                ft.Divider(height=4),
                ft.Text("Output directory", size=12, color=ft.Colors.GREY_500),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Choose Output",
                            icon=ft.Icons.DRIVE_FOLDER_UPLOAD,
                            on_click=lambda _: output_picker.get_directory_path(),
                        ),
                        ft.Text(
                            "No directory selected",
                            ref=output_path,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("", ref=output_preview, size=12),
                ft.Divider(height=4),
                ft.ElevatedButton(
                    "Build SAF",
                    ref=build_btn,
                    icon=ft.Icons.BUILD,
                    on_click=run_build,
                    disabled=True,
                ),
                ft.Divider(height=16),
                ft.Column(ref=progress_col, spacing=0),
            ],
        ),
    )


# ── OpenStack Uploader tab ────────────────────────────────────────────────────


def _parse_openrc(sh_path: str) -> dict:
    """Extract static export VAR=VALUE entries from an openrc shell script."""
    result = {}
    try:
        with open(sh_path) as f:
            for line in f:
                m = re.match(r'^\s*export\s+(\w+)=(.+)$', line.strip())
                if m:
                    key = m.group(1)
                    val = m.group(2).strip().strip('"').strip("'")
                    if key != "OS_PASSWORD":
                        result[key] = val
    except OSError:
        pass
    return result


def build_uploader_tab(page: ft.Page):
    source_path      = ft.Ref[ft.Text]()
    openrc_path_text = ft.Ref[ft.Text]()
    cred_status      = ft.Ref[ft.Text]()
    source_cred_btn  = ft.Ref[ft.ElevatedButton]()
    upload_btn       = ft.Ref[ft.ElevatedButton]()
    progress_col     = ft.Ref[ft.Column]()
    auth_log_col     = ft.Ref[ft.Column]()

    container_field = ft.TextField(
        value="saf-transfer",
        label="Container name",
        width=280,
        text_size=13,
    )

    state = {
        "source":       None,
        "env":          None,   # merged env dict once credentials are loaded
        "rc_path":      None,
        "static_vars":  {},
    }

    # ── openrc file picker ────────────────────────────────────────────────────

    def _on_rc_selected(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        path = e.files[0].path
        state["rc_path"] = path
        state["static_vars"] = _parse_openrc(path)
        openrc_path_text.current.value = path
        openrc_path_text.current.color = ft.Colors.WHITE
        # Pre-fill username from the rc file
        username_field.value = state["static_vars"].get("OS_USERNAME", "")
        source_cred_btn.current.disabled = False
        page.update()

    openrc_picker = ft.FilePicker(on_result=_on_rc_selected)
    page.overlay.append(openrc_picker)

    # ── credential dialog ─────────────────────────────────────────────────────

    username_field = ft.TextField(
        label="Username",
        value="",
        width=300,
        text_size=13,
        autofocus=True,
    )
    password_field = ft.TextField(
        label="Password",
        password=True,
        can_reveal_password=True,
        width=300,
        text_size=13,
    )

    def close_dialog(e=None):
        cred_dialog.open = False
        page.update()

    def on_connect(e):
        username = username_field.value.strip()
        password = password_field.value.strip()
        if not username or not password:
            return

        # Merge: system env + rc file static vars + username/password from dialog
        env = {**os.environ, **state["static_vars"]}
        env["OS_USERNAME"] = username
        env["OS_PASSWORD"] = password

        close_dialog()

        # Verify auth in background — updates status label when done
        def verify():
            auth_log_col.current.controls.clear()

            def log_auth(msg):
                auth_log_col.current.controls.append(
                    ft.Text(msg, size=12, color=ft.Colors.GREY_400, font_family="monospace")
                )
                page.update()

            cred_status.current.value = "Verifying credentials…"
            cred_status.current.color = ft.Colors.GREY_400
            page.update()

            log_auth(f"Loaded {len(state['static_vars'])} vars from {state['rc_path']}")

            ok, msg = check_auth(env, log=log_auth)
            if ok:
                state["env"] = env
                project = env.get("OS_PROJECT_NAME", "")
                cred_status.current.value = f"Connected — {username} @ {project}"
                cred_status.current.color = ft.Colors.GREEN_400
            else:
                state["env"] = None
                cred_status.current.value = f"Auth failed: {msg}"
                cred_status.current.color = ft.Colors.RED_400

            _refresh_upload_btn()
            page.update()

        threading.Thread(target=verify, daemon=True).start()

    cred_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("OpenStack Credentials"),
        content=ft.Column(
            [username_field, password_field],
            spacing=12,
            tight=True,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=close_dialog),
            ft.TextButton("Connect", on_click=on_connect),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(cred_dialog)

    def open_cred_dialog(e):
        password_field.value = ""
        cred_dialog.open = True
        page.update()

    # ── source directory picker ───────────────────────────────────────────────

    source_picker = ft.FilePicker(on_result=lambda e: _on_source_selected(e))
    page.overlay.append(source_picker)

    def _on_source_selected(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        state["source"] = e.path
        source_path.current.value = e.path
        source_path.current.color = ft.Colors.WHITE
        _refresh_upload_btn()
        page.update()

    # ── upload button state ───────────────────────────────────────────────────

    def _refresh_upload_btn():
        ready = bool(state["source"] and state["env"])
        upload_btn.current.disabled = not ready

    # ── upload worker ─────────────────────────────────────────────────────────

    def run_upload(e):
        if not state["source"] or not state["env"]:
            return

        container = container_field.value.strip() or "saf-transfer"
        progress_col.current.controls.clear()
        upload_btn.current.disabled = True
        page.update()

        def log_line(msg, color=ft.Colors.GREY_300):
            progress_col.current.controls.append(
                ft.Text(msg, size=12, color=color, font_family="monospace")
            )
            page.update()

        def worker():
            summary_label = ft.Text(
                "Uploading…", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400
            )
            summary_box = ft.Container(
                content=summary_label,
                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                border_radius=8,
                bgcolor=ft.Colors.GREY_900,
                margin=ft.margin.only(bottom=8),
            )
            progress_col.current.controls.insert(0, summary_box)
            page.update()

            try:
                success, total = upload_directory(
                    source_dir=state["source"],
                    container=container,
                    env=state["env"],
                    log=log_line,
                )
                if total == 0:
                    s_msg   = "No files found in the selected directory."
                    s_color = ft.Colors.ORANGE_400
                    s_bg    = ft.Colors.ORANGE_900
                elif success == total:
                    s_msg   = f"Done — {success}/{total} files uploaded successfully."
                    s_color = ft.Colors.GREEN_400
                    s_bg    = ft.Colors.GREEN_900
                else:
                    s_msg   = f"Finished with errors — {success}/{total} files succeeded."
                    s_color = ft.Colors.ORANGE_400
                    s_bg    = ft.Colors.ORANGE_900
            except Exception as err:
                s_msg   = f"Upload failed: {err}"
                s_color = ft.Colors.RED_400
                s_bg    = ft.Colors.RED_900

            summary_label.value  = s_msg
            summary_label.color  = s_color
            summary_box.bgcolor  = s_bg
            upload_btn.current.disabled = False
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    # ── layout ────────────────────────────────────────────────────────────────

    return ft.Container(
        expand=True,
        padding=20,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                ft.Text("OpenStack Uploader", size=22, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Upload SAF packages to an OpenStack Swift container, preserving folder structure.",
                    color=ft.Colors.GREY_400,
                    size=13,
                ),
                ft.Divider(height=20),

                # ── credentials ──────────────────────────────────────────────
                ft.Text("Credentials", size=12, color=ft.Colors.GREY_500),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Choose RC File",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=lambda _: openrc_picker.pick_files(
                                allowed_extensions=["sh"],
                                dialog_title="Select OpenStack RC file",
                            ),
                        ),
                        ft.Text(
                            "No file selected",
                            ref=openrc_path_text,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Source Credentials",
                            ref=source_cred_btn,
                            icon=ft.Icons.LOCK,
                            on_click=open_cred_dialog,
                            disabled=True,
                        ),
                        ft.Text(
                            "Not connected",
                            ref=cred_status,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Column(ref=auth_log_col, spacing=1),
                ft.Divider(height=4),

                # ── source directory ──────────────────────────────────────────
                ft.Text("Source directory", size=12, color=ft.Colors.GREY_500),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Choose Directory",
                            icon=ft.Icons.FOLDER_OPEN,
                            on_click=lambda _: source_picker.get_directory_path(),
                        ),
                        ft.Text(
                            "No directory selected",
                            ref=source_path,
                            color=ft.Colors.GREY_500,
                            size=13,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=4),

                # ── container + upload ────────────────────────────────────────
                container_field,
                ft.ElevatedButton(
                    "Upload",
                    ref=upload_btn,
                    icon=ft.Icons.CLOUD_UPLOAD,
                    on_click=run_upload,
                    disabled=True,
                ),
                ft.Divider(height=16),
                ft.Column(ref=progress_col, spacing=0),
            ],
        ),
    )


# ── App entry point ───────────────────────────────────────────────────────────

def main(page: ft.Page):
    page.title = "SAFSuite"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.window.width = 860
    page.window.min_width = 600

    page.add(
        ft.Tabs(
            tabs=[
                ft.Tab(
                    text="CSV Validator",
                    icon=ft.Icons.FACT_CHECK,
                    content=build_validator_tab(page),
                ),
                ft.Tab(
                    text="PDF Reverter",
                    icon=ft.Icons.INVERT_COLORS,
                    content=build_inverter_tab(page),
                ),
                ft.Tab(
                    text="SAF Builder",
                    icon=ft.Icons.BUILD,
                    content=build_saf_tab(page),
                ),
                ft.Tab(
                    text="OpenStack Uploader",
                    icon=ft.Icons.CLOUD_UPLOAD,
                    content=build_uploader_tab(page),
                ),
            ],
            expand=True,
        )
    )


if __name__ == '__main__':
    ft.app(target=main)
