#!/usr/bin/env python3
"""
MTGJSON Database Manager, Downloader, and Card Viewer
This script provides multiple subcommands:
  1. download: Download one or more MTGJSON files (via URLs or a list file),
     extract them, and update the SQLite database.
  2. view: CLI-based card viewer for searching and listing card details.
  3. popup: Popup card viewer using Tkinter to display detailed card info.
            If multiple cards match, a "Next" button cycles through them.
  4. db-manager: Database management utilities (e.g., stats, list entries, reinitialize).
  5. manage-links: Manage MTGJSON download links.
Usage Examples:
    # Download a single file:
    python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip --category AllPrintings
    # Download multiple files via a list file (each line: <category>,<url>)
    python mtgdb_manager.py download --list-file urls.txt
    # View cards by searching for a name keyword:
    python mtgdb_manager.py view --search "Goblin"
    # Popup viewer for a specific card (if multiple, cycle through them):
    python mtgdb_manager.py popup --name "Lightning Bolt"
    # Database manager to view stats:
    python mtgdb_manager.py db-manager stats
    # Manage MTGJSON download links:
    python mtgdb_manager.py manage-links fetch
"""
import os
import sys
import json
import zipfile
import argparse
import requests
from sqlalchemy import create_engine, Column, String, Text, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from bs4 import BeautifulSoup
from tqdm import tqdm  # Progress bar
import threading  # For threading support

# For the popup viewer.
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    tk = None

# ---------------------
# Database Models
# ---------------------
Base = declarative_base()

class Set(Base):
    """
    Represents an MTG set.
    """
    __tablename__ = 'sets'
    code = Column(String, primary_key=True)
    name = Column(String)
    release_date = Column(String)
    cards = relationship('Card', back_populates='set', cascade="all, delete-orphan")

class Card(Base):
    """
    Represents an individual MTG card.
    """
    __tablename__ = 'cards'
    uuid = Column(String, primary_key=True)
    name = Column(String)
    type = Column(String)
    rarity = Column(String)
    text = Column(Text)
    set_code = Column(String, ForeignKey('sets.code'))
    set = relationship('Set', back_populates='set')

class Link(Base):
    """
    Represents a downloadable link from MTGJSON.
    """
    __tablename__ = 'links'
    id = Column(String, primary_key=True)
    category = Column(String)
    url = Column(String, unique=True)
    file_type = Column(String)
    description = Column(Text)

def init_db(db_path="mtg_cards.db", reset=False):
    """
    Initializes the SQLite database and returns a session.
    Args:
        db_path (str): Path to the SQLite database file.
        reset (bool): If True, drop all tables and reinitialize.
    """
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session(), engine

def init_link_db(db_path="mtg_links.db", reset=False):
    """
    Initializes the SQLite database for storing links and returns a session.
    Args:
        db_path (str): Path to the links SQLite DB file.
        reset (bool): If True, drop all tables and reinitialize.
    """
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    if reset:
        Link.__table__.drop(engine, checkfirst=True)
    Link.__table__.create(engine, checkfirst=True)
    return sessionmaker(bind=engine)

# ---------------------
# Utility Functions for Download and Extraction
# ---------------------
def download_file(url, dest_path, progress_bar):
    """
    Downloads a file from a URL and saves it to a destination path with progress tracking.
    Args:
        url (str): URL to download.
        dest_path (str): Local file path to save the downloaded file.
        progress_bar: tqdm progress bar instance.
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024  # 1 KB
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(block_size):
                f.write(data)
                progress_bar.update(len(data))
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        progress_bar.close()

def extract_zip(zip_path, extract_to="."):
    """
    Extracts a zip file to the specified directory.
    Args:
        zip_path (str): Path to the zip file.
        extract_to (str): Directory where the files will be extracted.
    Returns:
        List of extracted file names.
    """
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
        extracted = zip_ref.namelist()
    print(f"Extracted files: {extracted}")
    return extracted

# ---------------------
# Data Processing Functions
# ---------------------
def process_allprintings(json_path, session):
    """
    Processes an AllPrintings JSON file, updating the database with set and card data.
    Args:
        json_path (str): Path to the JSON file.
        session: SQLAlchemy session.
    """
    print(f"Processing AllPrintings file: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for set_code, set_data in data.get('data', {}).items():
        set_entry = Set(
            code=set_code,
            name=set_data.get('name'),
            release_date=set_data.get('releaseDate')
        )
        session.merge(set_entry)
        for card_data in set_data.get('cards', []):
            card_entry = Card(
                uuid=card_data.get('uuid'),
                name=card_data.get('name'),
                type=card_data.get('type'),
                rarity=card_data.get('rarity'),
                text=card_data.get('text'),
                set_code=set_code
            )
            session.merge(card_entry)
    session.commit()
    print("Database updated successfully for AllPrintings.")

def process_file(file_path, category, session):
    """
    Processes a downloaded file based on its category.
    Args:
        file_path (str): Path to the downloaded file.
        category (str): Category of the file (e.g., 'AllPrintings').
        session: SQLAlchemy session.
    """
    if file_path.endswith('.zip'):
        extracted_files = extract_zip(file_path)
        json_files = [f for f in extracted_files if f.endswith('.json')]
        if not json_files:
            print("No JSON file found in the archive.")
            return
        json_path = os.path.join(os.path.dirname(file_path), json_files[0])
    else:
        json_path = file_path
    if category.lower() == "allprintings":
        process_allprintings(json_path, session)
    else:
        print(f"Processing for category '{category}' is not implemented.")
    # Cleanup: Remove downloaded/extracted files.
    try:
        os.remove(file_path)
        if file_path.endswith('.zip'):
            os.remove(json_path)
    except Exception as e:
        print(f"Cleanup error: {e}")

# ---------------------
# CLI Card Viewer Functions
# ---------------------
def cli_card_viewer(session, search_term):
    """
    CLI-based card viewer. Lists cards matching the search term.
    Args:
        session: SQLAlchemy session.
        search_term (str): Substring to search in card names.
    """
    print(f"Searching for cards containing '{search_term}'...")
    results = session.query(Card).filter(Card.name.ilike(f"%{search_term}%")).all()
    if not results:
        print("No matching cards found.")
        return
    for card in results:
        print("-" * 40)
        print(f"Name: {card.name}")
        print(f"UUID: {card.uuid}")
        print(f"Type: {card.type}")
        print(f"Rarity: {card.rarity}")
        print(f"Set: {card.set_code}")
        print(f"Text: {card.text}")
    print("-" * 40)

def popup_card_viewer(session, card_name):
    """
    Popup card viewer using Tkinter to display all info for a card.
    If multiple cards match, a "Next" button is provided to cycle through them.
    Args:
        session: SQLAlchemy session.
        card_name (str): Name of the card to display.
    """
    if tk is None:
        print("Tkinter is not available on this system.")
        return
    cards = session.query(Card).filter(Card.name.ilike(f"%{card_name}%")).all()
    if not cards:
        print("No card found with that name.")
        return
    current_index = [0]

    def show_card(index):
        card = cards[index]
        info = (
            f"Name: {card.name}\n"
            f"UUID: {card.uuid}\n"
            f"Type: {card.type}\n"
            f"Rarity: {card.rarity}\n"
            f"Set: {card.set_code}\n"
            f"Text: {card.text}"
        )
        label.config(text=info)
        next_button.config(state=tk.NORMAL if index < len(cards) - 1 else tk.DISABLED)

    def next_card():
        current_index[0] += 1
        show_card(current_index[0])

    root = tk.Tk()
    root.title("Popup Card Viewer")
    frame = ttk.Frame(root, padding="10")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    label = ttk.Label(frame, text="", justify=tk.LEFT)
    label.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
    next_button = ttk.Button(frame, text="Next", command=next_card)
    next_button.grid(row=1, column=1, sticky=tk.E, pady=10)
    ttk.Button(frame, text="Close", command=root.destroy).grid(row=1, column=0, sticky=tk.W, pady=10)
    show_card(current_index[0])
    root.mainloop()

# ---------------------
# Link Management Functions
# ---------------------
def fetch_mtgjson_files():
    """
    Fetches all downloadable file URLs from the MTGJSON all-files page.
    Returns:
        list of Link objects: Each object contains metadata about a file.
    """
    mtgjson_all_files_url = "https://mtgjson.com/downloads/all-files/"
    response = requests.get(mtgjson_all_files_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    files = []
    for link in soup.select('a[href*="/json/"], a[href*="/csv/"]'):
        url = link['href']
        category = url.split('/')[-1].split('.')[0]
        file_type = url.split('.')[-1]
        description = link.text.strip()
        files.append(Link(id=url, category=category, url=url, file_type=file_type, description=description))
    return files

def list_stored_links(session):
    """
    Lists all stored links in the database.
    """
    links = session.query(Link).all()
    if not links:
        print("No links found in the database.")
        return
    for link in links:
        print(f"Category: {link.category} | URL: {link.url} | Type: {link.file_type}")

# ---------------------
# Database Manager Functions
# ---------------------
def db_stats(session):
    """
    Displays simple statistics about the database.
    Args:
        session: SQLAlchemy session.
    """
    set_count = session.query(func.count(Set.code)).scalar()
    card_count = session.query(func.count(Card.uuid)).scalar()
    print("Database Statistics:")
    print(f"  Sets: {set_count}")
    print(f"  Cards: {card_count}")

def db_list_entries(session, limit=50):
    """
    Lists card entries from the database.
    Args:
        session: SQLAlchemy session.
        limit (int): Maximum number of entries to display.
    """
    print(f"Listing up to {limit} card entries:")
    cards = session.query(Card).limit(limit).all()
    if not cards:
        print("No card entries found.")
        return
    for card in cards:
        print("-" * 40)
        print(f"Name: {card.name}")
        print(f"UUID: {card.uuid}")
        print(f"Type: {card.type}")
        print(f"Rarity: {card.rarity}")
        print(f"Set: {card.set_code}")
    print("-" * 40)

# ---------------------
# Main CLI and Subcommand Handling
# ---------------------
def main():
    parser = argparse.ArgumentParser(
        description="MTGJSON Database Manager, Downloader, and Card Viewer"
    )
    parser.add_argument('--db', type=str, default="mtg_cards.db", help="Path to the SQLite DB file")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands", required=True)

    # Download subcommand.
    download_parser = subparsers.add_parser("download", help="Download and process MTGJSON files")
    download_group = download_parser.add_mutually_exclusive_group(required=True)
    download_group.add_argument('--urls', nargs='+', help="One or more file URLs to download")
    download_group.add_argument('--list-file', type=str, help="Path to a file with category,url entries (one per line)")
    download_parser.add_argument('--category', type=str, default="AllPrintings", help="Category of the file(s)")

    # Link management subcommand.
    link_parser = subparsers.add_parser("manage-links", help="Manage MTGJSON download links")
    link_subparsers = link_parser.add_subparsers(dest="link_action", required=True)
    link_fetch = link_subparsers.add_parser("fetch", help="Fetch and store MTGJSON download links")
    link_fetch.add_argument("--db", type=str, default="mtg_links.db", help="Links database path")
    link_list = link_subparsers.add_parser("list", help="List stored MTGJSON download links")
    link_list.add_argument("--db", type=str, default="mtg_links.db", help="Links database path")

    # CLI Card viewer subcommand.
    view_parser = subparsers.add_parser("view", help="CLI card viewer")
    view_parser.add_argument('--search', type=str, required=True, help="Search term for card names")

    # Popup Card viewer subcommand.
    popup_parser = subparsers.add_parser("popup", help="Popup card viewer (requires Tkinter)")
    popup_parser.add_argument('--name', type=str, required=True, help="Name of the card to display")

    # DB Manager subcommand.
    db_parser = subparsers.add_parser("db-manager", help="Database management utilities")
    db_parser.add_argument("action", choices=["stats", "list", "init"], help="Action: 'stats' to view DB stats, 'list' to list card entries, 'init' to reinitialize the DB")

    args = parser.parse_args()

    # Initialize DB session.
    reset = (args.command == "db-manager" and args.action == "init")
    session, engine = init_db(args.db, reset=reset)

    if args.command == "download":
        def download_task(url, category):
            filename = url.split("/")[-1]
            progress_bar = tqdm(total=1, desc=f"Downloading {filename}", unit="B", unit_scale=True, leave=True)
            download_file(url, filename, progress_bar)
            progress_bar.close()
            process_file(filename, category, session)

        threads = []
        if args.urls:
            for url in args.urls:
                thread = threading.Thread(target=download_task, args=(url, args.category))
                threads.append(thread)
                thread.start()
        elif args.list_file:
            if not os.path.exists(args.list_file):
                print(f"List file {args.list_file} not found.")
                sys.exit(1)
            with open(args.list_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        parts = line.split(",", 1)
                        if len(parts) != 2:
                            print(f"Invalid line format: {line}")
                            continue
                        category, url = parts
                        category = category.strip()
                        url = url.strip()
                        thread = threading.Thread(target=download_task, args=(url, category))
                        threads.append(thread)
                        thread.start()
                    except Exception as e:
                        print(f"Error processing line '{line}': {e}")

        for thread in threads:
            thread.join()

    elif args.command == "view":
        cli_card_viewer(session, args.search)

    elif args.command == "popup":
        popup_card_viewer(session, args.name)

    elif args.command == "db-manager":
        if args.action == "stats":
            db_stats(session)
        elif args.action == "list":
            db_list_entries(session)
        elif args.action == "init":
            print("Database reinitialized.")

    elif args.command == "manage-links":
        link_session = init_link_db(args.db).session()
        if args.link_action == "fetch":
            links = fetch_mtgjson_files()
            for link in links:
                link_session.merge(link)
            link_session.commit()
            print(f"Stored {len(links)} links")
        elif args.link_action == "list":
            list_stored_links(link_session)

if __name__ == "__main__":
    main()
```

---

### Key Improvements:

1. **Threading**:
   - Each download runs in its own thread, allowing multiple files to be downloaded concurrently.
   - Threads are joined at the end to ensure all downloads complete before the script exits.

2. **Live Display**:
   - The `tqdm` library provides a live progress bar for each download, showing the progress in real time.

3. **Link Management**:
   - Added functionality to fetch and store MTGJSON links dynamically.

4. **Error Handling**:
   - Improved error handling during downloads and file processing.

5. **Scalability**:
   - The script can handle large downloads efficiently with threading and progress tracking.

---
"""
### Usage Example:

```bash
# Download files with live progress
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip --category AllPrintings

# Fetch and store MTGJSON links
python mtgdb_manager.py manage-links fetch

# View cards
python mtgdb_manager.py view --search "Goblin"

# Popup viewer
python mtgdb_manager.py popup --name "Lightning Bolt"
```
"""
