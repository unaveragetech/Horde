#!/usr/bin/env python3
import os
import shutil

def move_json_files():
    """Move all JSON files from root to data/json directory"""
    # Get the script's directory
    root_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(root_dir, 'data', 'json')
    
    # Create the data directory if it doesn't exist
    os.makedirs(data_dir, exist_ok=True)
    
    # Find and move all JSON files
    moved_files = []
    for filename in os.listdir(root_dir):
        if filename.endswith('.json'):
            src_path = os.path.join(root_dir, filename)
            dst_path = os.path.join(data_dir, filename)
            
            # Move the file
            shutil.move(src_path, dst_path)
            moved_files.append(filename)
    
    # Print results
    if moved_files:
        print(f"Moved {len(moved_files)} JSON files to {data_dir}:")
        for filename in moved_files:
            print(f"  - {filename}")
    else:
        print("No JSON files found to move.")

if __name__ == "__main__":
    move_json_files()