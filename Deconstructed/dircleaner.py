#!/usr/bin/env python3


#move to the dir you want to clean, or set in command - python dircleaner.py /path/to/1935

from pathlib import Path
import shutil
import sys

def find_items_to_delete(base_dir):
    """Find all files and folders to delete in month directories."""
    to_delete = []
    
    for year_dir in Path(base_dir).iterdir():
        if not year_dir.is_dir() or year_dir.name.startswith('.'):
            continue
            
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or month_dir.name.startswith('.'):
                continue
            
            # Look at everything in the month directory
            for item in month_dir.iterdir():
                # Skip .zip files
                if item.is_file() and item.suffix == '.zip':
                    continue
                
                # Skip SimpleArchiveFormat directory
                if item.is_dir() and item.name == 'SimpleArchiveFormat':
                    continue
                
                # Everything else should be deleted
                to_delete.append(item)
    
    return to_delete

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean month directories, keep only .zip and SimpleArchiveFormat')
    parser.add_argument('path', nargs='?', default='.',
                       help='Base directory (default: current directory)')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    base_dir = Path(args.path)
    
    if not base_dir.exists():
        print(f"Error: Directory '{base_dir}' does not exist")
        sys.exit(1)
    
    print(f"Scanning: {base_dir.absolute()}\n")
    
    to_delete = find_items_to_delete(base_dir)
    
    if not to_delete:
        print("✅ No items to delete - directories are already clean!")
        return
    
    # Show what will be deleted
    print(f"Found {len(to_delete)} items to delete:\n")
    
    files_count = sum(1 for item in to_delete if item.is_file())
    dirs_count = sum(1 for item in to_delete if item.is_dir())
    
    print(f"  📄 Files: {files_count}")
    print(f"  📁 Directories: {dirs_count}")
    print()
    
    # Show first 20 items as examples
    print("Examples of items to delete:")
    for item in to_delete[:20]:
        item_type = "📁" if item.is_dir() else "📄"
        print(f"  {item_type} {item.relative_to(base_dir)}")
    
    if len(to_delete) > 20:
        print(f"  ... and {len(to_delete) - 20} more items")
    
    print()
    
    # Confirm deletion
    if not args.yes:
        response = input("⚠️  Delete these items? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled - no files deleted")
            sys.exit(0)
    
    # Delete items
    print("\nDeleting items...")
    deleted_count = 0
    error_count = 0
    
    for item in to_delete:
        try:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            deleted_count += 1
        except Exception as e:
            print(f"❌ Error deleting {item}: {e}")
            error_count += 1
    
    print(f"\n✅ Deleted {deleted_count} items")
    if error_count > 0:
        print(f"⚠️  {error_count} errors occurred")
    
    print("\nRemaining in each month directory:")
    print("  - *.zip files")
    print("  - SimpleArchiveFormat/ folders")

if __name__ == '__main__':
    main()