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
import datetime
import re
import sys
import subprocess
import json
import random
from tkinter import filedialog
import zipfile
import argparse
import requests
from sqlalchemy import create_engine, Column, String, Text, ForeignKey, func
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase
from bs4 import BeautifulSoup
from tqdm import tqdm  # Progress bar
import threading  # For threading support
import math
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socket
import time  # Add this import if not already present

# For the popup viewer.
def get_ollama_models():
    """
    Get list of available Ollama models
    Returns:
        list: Available model names or default list if Ollama is not accessible
    """
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        if result.returncode == 0:
            # Parse output to extract model names
            models = []
            for line in result.stdout.splitlines()[1:]:  # Skip header line
                if line.strip():
                    model_name = line.split()[0]  # First column is model name
                    models.append(model_name)
            return models if models else ["llama2"]
        return ["llama2"]  # Default if command succeeds but no models found
    except Exception as e:
        print(f"Error getting Ollama models: {e}")
        return ["llama2"]  # Default fallback

def check_ollama_status():
    """
    Check if Ollama service is running and responsive
    Returns:
        bool: True if Ollama is running and responsive
    """
    try:
        response = requests.get('http://localhost:11434/api/version')
        return response.status_code == 200
    except:
        return False

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    tk = None

# ---------------------
# Database Models
# ---------------------
class Base(DeclarativeBase):
    """Base class for all database models"""
    pass

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
    set = relationship('Set', back_populates='cards')  # Changed from 'set' to 'cards'

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
    Session = sessionmaker(bind=engine)
    return Session()  # Return a session instance directly

# ---------------------
# Utility Functions for Download and Extraction
# ---------------------
def check_file_exists(filename):
    """
    Check if a file exists and return its modification time if it does.
    Args:
        filename (str): Name of the file to check
    Returns:
        float or None: Modification time if file exists, None otherwise
    """
    if os.path.exists(filename):
        return os.path.getmtime(filename)
    return None

def download_file(url, dest_path, progress_bar, force_update=False):
    """
    Downloads a file from a URL and saves it to a destination path with progress tracking.
    Args:
        url (str): URL to download.
        dest_path (str): Local file path to save the downloaded file.
        progress_bar: tqdm progress bar instance.
        force_update (bool): If True, download even if file exists
    Returns:
        bool: True if new file was downloaded, False if using existing file
    """
    existing_time = check_file_exists(dest_path)
    
    if existing_time and not force_update:
        # Check if remote file is newer using HEAD request
        try:
            head = requests.head(url)
            remote_modified = head.headers.get('last-modified')
            if remote_modified:
                remote_time = datetime.datetime.strptime(
                    remote_modified, 
                    '%a, %d %b %Y %H:%M:%S %Z'
                ).timestamp()
                if remote_time <= existing_time:
                    print(f"File {dest_path} is up to date. Skipping download.")
                    progress_bar.close()
                    return False
        except Exception as e:
            print(f"Warning: Could not check remote file timestamp: {e}")

    try:
        response = requests.get(url, stream=False)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024  # 1 KB
        
        # If file exists, remove it before downloading new version
        if os.path.exists(dest_path):
            os.remove(dest_path)
            print(f"Removing existing file: {dest_path}")
            
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(block_size):
                f.write(data)
                progress_bar.update(len(data))
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        progress_bar.close()
        return False

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
        # Clear existing data for this category before processing
        session.query(Card).delete()
        session.query(Set).delete()
        session.commit()
        
        process_allprintings(json_path, session)
    else:
        print(f"Processing for category '{category}' is not implemented.")

    # Cleanup: Remove downloaded/extracted files
    try:
        os.remove(file_path)
        if file_path.endswith('.zip'):
            os.remove(json_path)
    except Exception as e:
        print(f"Cleanup error: {e}")

def download_task(url, category):
    """
    Thread task for downloading and processing a file.
    Args:
        url (str): URL to download.
        category (str): Category of the file.
    """
    filename = url.split("/")[-1]
    progress_bar = tqdm(total=1, desc=f"Downloading {filename}", unit="B", unit_scale=True, leave=True)
    
    if download_file(url, filename, progress_bar):
        print(f"Processing new/updated file: {filename}")
        session, _ = init_db()  # Create new session for this thread
        process_file(filename, category, session)
        session.close()
    else:
        print(f"Using existing file: {filename}")

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

def popup_card_viewer(session, initial_search=""):
    """
    Enhanced popup card viewer using Tkinter with MTG-specific styling.
    Args:
        session: SQLAlchemy session.
        initial_search (str): Initial search term to populate the grid.
    """
    if tk is None:
        print("Tkinter is not available on this system.")
        return

    # Import additional required modules
    from PIL import Image, ImageTk
    import requests
    from io import BytesIO
    import re
    import threading

    # MTG-specific styling constants
    RARITY_COLORS = {
        'common': '#000000',
        'uncommon': '#707070',
        'rare': '#A58E4A',
        'mythic': '#BF4427',
        'special': '#6B468B',
        'bonus': '#ff8a00'
    }

    RARITY_BG = {
        'common': '#D3D3D3',
        'uncommon': '#C0C0C0',
        'rare': '#FFD700',
        'mythic': '#FF4500',
        'special': '#DDA0DD',
        'bonus': '#FFA500'
    }

    # MTG mana symbols and their emoji equivalents
    MANA_SYMBOLS = {
        '{W}': '⚪',  # White mana
        '{U}': '🔵',  # Blue mana
        '{B}': '⚫',  # Black mana
        '{R}': '🔴',  # Red mana
        '{G}': '🟢',  # Green mana
        '{T}': '↩️',  # Tap symbol
    }

    def format_mana_text(text):
        """Replace mana symbols with emojis"""
        if not text:
            return text
        formatted = text
        for symbol, emoji in MANA_SYMBOLS.items():
            formatted = formatted.replace(symbol, f" {emoji} ")
        return formatted

    def get_rarity_style(rarity):
        """Get text and background color for rarity"""
        rarity = rarity.lower()
        return (RARITY_COLORS.get(rarity, '#000000'), 
                RARITY_BG.get(rarity, '#FFFFFF'))

    def load_card_image(card_name):
        """Load card image from Scryfall API"""
        try:
            from PIL import Image, ImageTk
            import requests
            from io import BytesIO
            
            response = requests.get(
                f"https://api.scryfall.com/cards/named?fuzzy={card_name}",
                timeout=10
            )
            if response.status_code == 200:
                card_data = response.json()
                image_url = card_data.get('image_uris', {}).get('normal')
                if image_url:
                    img_response = requests.get(image_url, timeout=10)
                    img = Image.open(BytesIO(img_response.content))
                    # Increased image size
                    aspect_ratio = img.width / img.height
                    new_width = 400  # Increased from 300
                    new_height = int(new_width / aspect_ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(img)
            return None
        except Exception as e:
            print(f"Error loading card image: {e}")
            return None

    # Add to imports
    import tkinter.ttk as ttk
    from tkinter import colorchooser
    import time

    # Add card type specific styling and animation constants
    CARD_TYPE_STYLES = {
        'Creature': {
            'bg_color': '#3a2d1f',
            'bg_alpha': 0.85,
            'animation': 'creature',
            'icon': '🐾',
            'border_color': '#8B4513'
        },
        'Instant': {
            'bg_color': '#1f3a3a',
            'bg_alpha': 0.90,
            'animation': 'flash',
            'icon': '⚡',
            'border_color': '#4682B4'
        },
        'Sorcery': {
            'bg_color': '#3a1f3a',
            'bg_alpha': 0.85,
            'animation': 'spiral',
            'icon': '🌀',
            'border_color': '#800080'
        },
        'Enchantment': {
            'bg_color': '#3a3a1f',
            'bg_alpha': 0.80,
            'animation': 'sparkle',
            'icon': '✨',
            'border_color': '#FFD700'
        },
        'Artifact': {
            'bg_color': '#2f2f2f',
            'bg_alpha': 0.95,
            'animation': 'mechanical',
            'icon': '⚙️',
            'border_color': '#A9A9A9'
        },
        'Land': {
            'bg_color': '#1f3a1f',
            'bg_alpha': 0.80,
            'animation': 'nature',
            'icon': '🌳',
            'border_color': '#228B22'
        },
        'Planeswalker': {
            'bg_color': '#3a2d3a',
            'bg_alpha': 0.90,
            'animation': 'planar',
            'icon': '👑',
            'border_color': '#DC143C'
        }
    }

    # Default style for unknown card types
    DEFAULT_STYLE = {
        'bg_color': '#2d2d2d',
        'bg_alpha': 0.85,
        'animation': 'default',
        'icon': '📜',
        'border_color': '#696969'
    }

    class EnhancedCardPopup(tk.Toplevel):
        def __init__(self, parent, card):
            super().__init__(parent)
            self.card = card
            self.style = self._get_card_style()
            
            # Initialize particles list
            self.particles = []
            self.animating = False
            
            # Configure window
            self.title("")  # Remove title bar
            self.attributes('-alpha', self.style['bg_alpha'])
            self.configure(bg=self.style['bg_color'])
            self.overrideredirect(True)  # Remove window decorations
            
            # Store window dimensions - increased size
            self.width = 500  # Increased from 400
            self.height = 800  # Increased from 600
            self._center_window()
            
            # Create main frame with custom border
            self.main_frame = tk.Frame(
                self,
                bg=self.style['bg_color'],
                highlightbackground=self.style['border_color'],
                highlightthickness=2
            )
            self.main_frame.pack(fill='both', expand=True, padx=2, pady=2)
            
            # Add close button
            self.close_button = tk.Button(
                self,
                text="✖",
                command=self.destroy,
                bg=self.style['bg_color'],
                fg='white',
                bd=0,
                font=('Arial', 12)
            )
            self.close_button.place(x=370, y=5)
            
            # Make window draggable
            self.bind('<Button-1>', self.start_move)
            self.bind('<B1-Motion>', self.on_move)
            
            # Create content
            self._create_content()
            
            # Start animation
            self._animate_entrance()

        def _adjust_color(self, color, adjustment):
            """
            Adjust a hex color by adding/subtracting the adjustment value
            Args:
                color (str): Hex color code (e.g., '#123456')
                adjustment (int): Value to add/subtract from each RGB component
            Returns:
                str: Adjusted hex color
            """
            # Remove '#' if present
            color = color.lstrip('#')
            
            # Convert to RGB
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            
            # Adjust values
            r = max(0, min(255, r + adjustment))
            g = max(0, min(255, g + adjustment))
            b = max(0, min(255, b + adjustment))
            
            # Convert back to hex
            return f'#{r:02x}{g:02x}{b:02x}'

        def _get_card_style(self):
            """Determine card style based on rarity and type"""
            rarity = self.card.rarity.lower() if self.card.rarity else 'common'
            
            styles = {
                'common': {
                    'bg_color': '#2D2D2D',
                    'border_color': '#000000',
                    'bg_alpha': 0.95,
                    'icon': '◆'
                },
                'uncommon': {
                    'bg_color': '#3D3D3D',
                    'border_color': '#C0C0C0',
                    'bg_alpha': 0.95,
                    'icon': '◇'
                },
                'rare': {
                    'bg_color': '#4D4D2D',
                    'border_color': '#FFD700',
                    'bg_alpha': 0.95,
                    'icon': '★'
                },
                'mythic': {
                    'bg_color': '#4D2D2D',
                    'border_color': '#FF4500',
                    'bg_alpha': 0.95,
                    'icon': '🔥'
                }
            }
            
            return styles.get(rarity, styles['common'])

        def _center_window(self):
            """Center the window on the screen"""
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            self.x = (screen_width - self.width) // 2
            self.y = (screen_height - self.height) // 2
            
            self.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")

        def start_move(self, event):
            """Start window drag"""
            self.x_offset = event.x
            self.y_offset = event.y

        def on_move(self, event):
            """Handle window drag"""
            x = self.winfo_x() + (event.x - self.x_offset)
            y = self.winfo_y() + (event.y - self.y_offset)
            self.geometry(f"+{x}+{y}")

        def _create_content(self):
            """Create the content widgets for the card popup"""
            # Card Name (at the top)
            name_frame = tk.Frame(
                self.main_frame,
                bg=self._adjust_color(self.style['bg_color'], 20)
            )
            name_frame.pack(fill='x', padx=15, pady=(15, 10))
            
            tk.Label(
                name_frame,
                text=self.card.name,
                font=('Arial', 18, 'bold'),  # Increased font size
                bg=self._adjust_color(self.style['bg_color'], 20),
                fg='white',
                wraplength=450  # Increased wraplength
            ).pack(pady=5)

            # Card Image
            image_frame = tk.Frame(
                self.main_frame,
                bg=self.style['bg_color']
            )
            image_frame.pack(fill='x', padx=15, pady=10)
            
            # Load and display the card image
            self.card_image = load_card_image(self.card.name)
            if self.card_image:
                image_label = tk.Label(
                    image_frame,
                    image=self.card_image,
                    bg=self.style['bg_color']
                )
                image_label.pack(pady=5)
            else:
                tk.Label(
                    image_frame,
                    text="Image not available",
                    font=('Arial', 12, 'italic'),
                    bg=self.style['bg_color'],
                    fg='gray'
                ).pack(pady=5)

            # Type Line
            type_frame = tk.Frame(
                self.main_frame,
                bg=self._adjust_color(self.style['bg_color'], 10)
            )
            type_frame.pack(fill='x', padx=15, pady=10)
            
            tk.Label(
                type_frame,
                text=self.card.type,
                font=('Arial', 14),  # Increased font size
                bg=self._adjust_color(self.style['bg_color'], 10),
                fg='white',
                wraplength=450  # Increased wraplength
            ).pack(pady=5, fill='x')

            # Card Text
            if self.card.text:
                text_frame = tk.Frame(
                    self.main_frame,
                    bg=self.style['bg_color']
                )
                text_frame.pack(fill='both', expand=True, padx=15, pady=10)
                
                text_widget = tk.Text(
                    text_frame,
                    wrap='word',
                    font=('Arial', 12),  # Increased font size
                    bg=self.style['bg_color'],
                    fg='white',
                    height=12,  # Increased height
                    width=45,   # Increased width
                    bd=0
                )
                text_widget.insert('1.0', self.card.text)
                text_widget.config(state='disabled')
                text_widget.pack(fill='both', expand=True)

            # Set and Rarity Info (at the bottom)
            info_frame = tk.Frame(
                self.main_frame,
                bg=self._adjust_color(self.style['bg_color'], -10)
            )
            info_frame.pack(fill='x', padx=15, pady=(10, 15))
            
            set_label = tk.Label(
                info_frame,
                text=f"Set: {self.card.set_code} • Rarity: {self.card.rarity}",
                font=('Arial', 12),  # Increased font size
                bg=self._adjust_color(self.style['bg_color'], -10),
                fg='white'
            )
            set_label.pack(pady=5)

        def _animate_entrance(self):
            """Perform rarity-specific entrance animation"""
            rarity = self.card.rarity.lower() if self.card.rarity else 'common'
            
            if rarity == 'mythic':
                self._animate_mythic()
            elif rarity == 'rare':
                self._animate_rare()
            elif rarity == 'uncommon':
                self._animate_uncommon()
            else:  # common
                self._animate_common()

        def _animate_common(self):
            """Simple fade in with basic particle effect"""
            self.attributes('-alpha', 0.0)
            
            # Create falling dots effect
            self.animating = True
            self.after(0, self._create_common_particles)
            
            for i in range(10):
                self.attributes('-alpha', i/10.0)
                self.update()
                time.sleep(0.05)
            
            time.sleep(1)
            self.animating = False

        def _create_common_particles(self):
            """Create simple black dot particles"""
            if not self.animating:
                return
                
            particle = tk.Label(self, text="•", fg='black', bg=self.style['bg_color'])
            x = random.randint(0, self.width)
            particle.place(x=x, y=0)
            
            self.particles.append({'widget': particle, 'y': 0, 'speed': 5})
            self._animate_particles()
            
            if self.animating:
                self.after(200, self._create_common_particles)

        def _animate_uncommon(self):
            """Silver shimmer effect"""
            self.attributes('-alpha', 0.0)
            self.animating = True
            self.after(0, self._create_uncommon_particles)
            
            # Slide in from left with silver trail
            for i in range(20):
                self.geometry(f"{self.width}x{self.height}+{self.x-(20-i)*20}+{self.y}")
                self.attributes('-alpha', min(i/10.0, 1.0))
                self.update()
                time.sleep(0.03)
                
            time.sleep(1)
            self.animating = False

        def _create_uncommon_particles(self):
            """Create silver sparkle particles"""
            if not self.animating:
                return
                
            particle = tk.Label(self, text="✧", fg='silver', bg=self.style['bg_color'])
            x = random.randint(0, self.width)
            y = random.randint(0, self.height)
            particle.place(x=x, y=y)
            
            self.particles.append({'widget': particle, 'x': x, 'y': y, 'age': 0})
            self._animate_sparkle_particles()
            
            if self.animating:
                self.after(100, self._create_uncommon_particles)

        def _animate_rare(self):
            """Golden spiral effect"""
            self.attributes('-alpha', 0.0)
            self.animating = True
            self.after(0, self._create_rare_particles)
            
            # Spiral entrance
            center_x = self.x + self.width//2
            center_y = self.y + self.height//2
            radius = 200
            
            for i in range(20):
                angle = i * (2 * math.pi / 20)
                x = center_x + int(radius * math.cos(angle) * (20-i)/20)
                y = center_y + int(radius * math.sin(angle) * (20-i)/20)
                self.geometry(f"{self.width}x{self.height}+{x-self.width//2}+{y-self.height//2}")
                self.attributes('-alpha', min(i/10.0, 1.0))
                self.update()
                time.sleep(0.03)
                
            time.sleep(1)
            self.animating = False

        def _create_rare_particles(self):
            """Create golden star particles"""
            if not self.animating:
                return
                
            particles = ["⭐", "✨", "💫"]
            particle = tk.Label(self, text=random.choice(particles), fg='gold', bg=self.style['bg_color'])
            x = random.randint(0, self.width)
            y = random.randint(0, self.height)
            particle.place(x=x, y=y)
            
            self.particles.append({'widget': particle, 'x': x, 'y': y, 'age': 0})
            self._animate_star_particles()
            
            if self.animating:
                self.after(50, self._create_rare_particles)

        def _animate_mythic(self):
            """Epic mythic animation with fire effects"""
            self.attributes('-alpha', 0.0)
            self.animating = True
            self.after(0, self._create_mythic_particles)
            
            # Dramatic entrance with pulsing border
            original_border = self.main_frame.cget('highlightbackground')
            colors = ['#FF4500', '#FF6347', '#FF7F50', '#FF8C00']
            
            for i in range(20):
                # Pulse border
                self.main_frame.configure(highlightbackground=colors[i % len(colors)])
                # Fade in with slight rotation
                self.attributes('-alpha', min(i/10.0, 1.0))
                angle = math.sin(i * math.pi / 10) * 5  # 5 degree maximum rotation
                self.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
                self.update()
                time.sleep(0.05)
                
            self.main_frame.configure(highlightbackground=original_border)
            time.sleep(1)
            self.animating = False

        def _create_mythic_particles(self):
            """Create mythic fire and dragon particles"""
            if not self.animating:
                return
                
            particles = ["🔥", "✨", "💫", "🐉"]
            particle = tk.Label(self, text=random.choice(particles), fg='#FF4500', bg=self.style['bg_color'])
            x = random.randint(0, self.width)
            y = self.height
            particle.place(x=x, y=y)
            
            self.particles.append({
                'widget': particle,
                'x': x,
                'y': y,
                'dx': random.uniform(-2, 2),
                'dy': random.uniform(-5, -3)
            })
            self._animate_fire_particles()
            
            if self.animating:
                self.after(100, self._create_mythic_particles)

        def _animate_particles(self):
            """Animate common particles"""
            for particle in self.particles[:]:
                particle['y'] += particle['speed']
                if particle['y'] > self.height:
                    particle['widget'].destroy()
                    self.particles.remove(particle)
                else:
                    particle['widget'].place(y=particle['y'])
            
            if self.particles:
                self.after(50, self._animate_particles)

        def _animate_sparkle_particles(self):
            """Animate uncommon sparkle particles"""
            for particle in self.particles[:]:
                particle['age'] += 1
                if particle['age'] > 10:
                    particle['widget'].destroy()
                    self.particles.remove(particle)
                else:
                    particle['widget'].configure(fg=f'gray{70 + particle["age"]*3}')
            
            if self.particles:
                self.after(50, self._animate_sparkle_particles)

        def _animate_star_particles(self):
            """Animate rare star particles"""
            for particle in self.particles[:]:
                particle['age'] += 1
                if particle['age'] > 15:
                    particle['widget'].destroy()
                    self.particles.remove(particle)
                else:
                    # Make particles float upward and fade
                    particle['y'] -= 2
                    particle['widget'].place(y=particle['y'])
                    alpha = max(0, 1 - particle['age']/15)
                    particle['widget'].configure(fg=f'#{int(255*alpha):02x}d700')
            
            if self.particles:
                self.after(30, self._animate_star_particles)

        def _animate_fire_particles(self):
            """Animate mythic fire particles"""
            for particle in self.particles[:]:
                # Update position with physics
                particle['x'] += particle['dx']
                particle['y'] += particle['dy']
                particle['dy'] += 0.2  # Gravity
                
                # Remove if out of bounds
                if particle['y'] > self.height or particle['x'] < 0 or particle['x'] > self.width:
                    particle['widget'].destroy()
                    self.particles.remove(particle)
                else:
                    particle['widget'].place(x=particle['x'], y=particle['y'])
            
            if self.particles:
                self.after(20, self._animate_fire_particles)

        def destroy(self):
            """Clean up particles before destroying window"""
            self.animating = False
            for particle in self.particles:
                particle['widget'].destroy()
            super().destroy()

    def create_card_popup(card):
        """Create an enhanced card details popup window"""
        popup = EnhancedCardPopup(root, card)
        popup.focus_set()

    def filter_cards(event=None):
        """Filter cards based on search text and update the grid"""
        def perform_filter():
            search_term = search_var.get().strip().lower()
            cards = session.query(Card).filter(
                Card.name.ilike(f"%{search_term}%")
            ).order_by(Card.name).all()
            return cards

        def update_ui(cards):
            tree.delete(*tree.get_children())  # Clear current items
            for card in cards:
                tree.insert("", "end", values=(
                    card.name, 
                    card.type, 
                    card.rarity, 
                    card.set_code
                ), tags=(card.rarity.lower(),))
            
            progress_window.destroy()
            status_var.set(f"Found {len(cards)} cards")
            search_entry.configure(state='normal')
            tree.update()

        # Create and show progress window
        progress_window = tk.Toplevel(root)
        progress_window.title("Loading...")
        progress_window.geometry("300x100")
        progress_window.transient(root)
        progress_window.grab_set()
        
        # Center the progress window
        x = root.winfo_x() + (root.winfo_width() // 2) - (300 // 2)
        y = root.winfo_y() + (root.winfo_height() // 2) - (100 // 2)
        progress_window.geometry(f"+{x}+{y}")

        # Add progress bar and label
        progress_label = ttk.Label(progress_window, text="Filtering cards...", padding=(20, 10))
        progress_label.pack()
        
        progress_bar = ttk.Progressbar(
            progress_window,
            mode='indeterminate',
            length=200
        )
        progress_bar.pack(pady=10)
        progress_bar.start(10)

        # Disable the search entry while filtering
        search_entry.configure(state='disabled')
        
        def filter_thread():
            try:
                cards = perform_filter()
                root.after(0, lambda: update_ui(cards))
            except Exception as e:
                root.after(0, lambda: [
                    progress_window.destroy(),
                    messagebox.showerror("Error", f"Error filtering cards: {str(e)}"),
                    search_entry.configure(state='normal')
                ])

        # Start filtering thread
        threading.Thread(target=filter_thread, daemon=True).start()

    def sort_column(col):
        """Sort tree contents when header is clicked"""
        items = [(tree.set(child, col), child) for child in tree.get_children('')]
        items.sort()
        for index, (val, child) in enumerate(items):
            tree.move(child, '', index)

    def on_select(event):
        """Handle selection of a card in the grid"""
        selection = tree.selection()
        if not selection:
            return
        
        card_name = tree.item(selection[0])["values"][0]
        card = session.query(Card).filter(Card.name == card_name).first()
        if card:
            create_card_popup(card)

    # Create main window
    root = tk.Tk()
    root.title("MTG Card Viewer")
    root.geometry("1200x800")

    # Create main frame
    main_frame = ttk.Frame(root)
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    # Create search frame
    search_frame = ttk.Frame(main_frame)
    search_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
    main_frame.columnconfigure(0, weight=1)

    # Create status bar
    status_var = tk.StringVar()
    status_bar = ttk.Label(root, textvariable=status_var, relief=tk.SUNKEN)
    status_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))

    # Add search label
    search_label = ttk.Label(search_frame, text="Search:", font=("Arial", 12))
    search_label.grid(row=0, column=0, padx=5)

    # Create search variable and entry
    search_var = tk.StringVar()
    search_entry = ttk.Entry(
        search_frame,
        textvariable=search_var,
        font=("Arial", 12)
    )
    search_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))

    # Define the on_search_change function before using it
    def on_search_change(*args):
        """Debounced search handler"""
        if hasattr(root, '_search_after_id'):
            root.after_cancel(root._search_after_id)
        root._search_after_id = root.after(300, filter_cards)  # 300ms delay

    # Now we can safely add the trace
    search_var.trace_add("write", on_search_change)

    # Create Treeview with custom styling
    tree_frame = ttk.Frame(main_frame)
    tree_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    main_frame.rowconfigure(1, weight=1)

    tree = ttk.Treeview(
        tree_frame,
        columns=("Name", "Type", "Rarity", "Set"),
        show="headings",
        height=20
    )

    # Configure columns with sorting
    for col in ("Name", "Type", "Rarity", "Set"):
        tree.heading(col, text=col, command=lambda c=col: sort_column(c))
        tree.column(col, width=200 if col in ("Name", "Type") else 100)

    # Configure tags for rarity-based styling
    for rarity, bg_color in RARITY_BG.items():
        tree.tag_configure(rarity, background=bg_color)

    # Add scrollbars
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    # Grid the tree and scrollbars
    tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
    vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
    hsb.grid(row=1, column=0, sticky=(tk.E, tk.W))
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)

    # Bind selection event
    tree.bind('<<TreeviewSelect>>', on_select)

    # If initial search term provided, perform search
    if initial_search:
        search_var.set(initial_search)
        filter_cards()
    else:
        # Initial population of the grid
        filter_cards()

    # Start the main loop
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
    mtgjson_base_url = "https://mtgjson.com"
    mtgjson_all_files_url = f"{mtgjson_base_url}/api/v5/Meta.json"
    
    try:
        # First get the meta information which contains all available endpoints
        response = requests.get(mtgjson_all_files_url, timeout=30)
        response.raise_for_status()
        meta_data = response.json()
        
        files = []
        # Process each endpoint in the meta data
        for endpoint in meta_data.get('data', {}).get('paths', []):  # Changed from 'endpoints' to 'paths'
            path = endpoint.get('path')
            if not path:
                continue
                
            url = f"{mtgjson_base_url}{path}"
            name = path.split('/')[-1]  # Get the name from the path
            
            # Create both JSON and ZIP links
            json_link = Link(
                id=f"{path}.json",
                category=name,
                url=f"{url}.json",
                file_type="json",
                description=endpoint.get('description', '')
            )
            
            zip_link = Link(
                id=f"{path}.json.zip",
                category=name,
                url=f"{url}.json.zip",
                file_type="zip",
                description=endpoint.get('description', '')
            )
            
            files.extend([json_link, zip_link])
        
        print(f"Found {len(files)} downloadable files")
        return files
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching MTGJSON files: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing MTGJSON meta data: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error while fetching MTGJSON files: {e}")
        return []

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
# Deck Builder Functions
# ---------------------
class DeckBuilderUtils:
    @staticmethod
    def validate_deck(deck_list, session):
        """Validate the deck against the database and Magic rules."""
        # Placeholder for validation logic
        pass

    @staticmethod
    def save_deck_template(deck_info, filename):
        """Save the deck as a reusable template."""
        # Placeholder for saving logic
        pass

    @staticmethod
    def load_deck_template(filename):
        """Load a deck template."""
        # Placeholder for loading logic
        pass

def get_cards_by_criteria(session, criteria):
    """
    Query cards from database based on various criteria
    Args:
        session: SQLAlchemy session
        criteria: dict with search criteria (type, text, name patterns)
    Returns:
        list: List of matching cards with their details
    """
    query = session.query(Card)
    
    if 'type' in criteria:
        query = query.filter(Card.type.ilike(f"%{criteria['type']}%"))
    if 'text' in criteria:
        query = query.filter(Card.text.ilike(f"%{criteria['text']}%"))
    if 'name' in criteria:
        query = query.filter(Card.name.ilike(f"%{criteria['name']}%"))
        
    return [{
        'name': card.name,
        'type': card.type,
        'text': card.text,
        'rarity': card.rarity,
        'set': card.set_code
    } for card in query.all()]

def generate_deck_with_constraints(session, prompt, selected_cards, model="dorian2b/vera:latest"):
    """Generate a deck using Ollama with user-selected cards and constraints"""
    
    # Parse theme keywords from prompt
    keywords = prompt.lower().split()
    
    # Get relevant cards from database based on theme
    theme_cards = []
    for keyword in keywords:
        # Search for cards matching the keyword in name, type, or text
        matches = get_cards_by_criteria(session, {
            'text': keyword
        })
        theme_cards.extend(matches)
    
    # Remove duplicates and limit to a reasonable number
    theme_cards = list({card['name']: card for card in theme_cards}.values())[:20]
    
    enhanced_prompt = f"""
    Create a Magic: The Gathering deck based on this theme: {prompt}
    
    Here are some relevant cards from the database that match your theme:
    {json.dumps(theme_cards, indent=2)}
    
    Requirements:
    - 60 cards total for main deck
    - Follow standard Magic format rules
    - Include card quantities
    - Use cards from the provided list when relevant
    - Include the selected cards: {', '.join(selected_cards)}
    - Group by card type (Creatures, Spells, Lands)
    - Explain key synergies and strategy
    
    Format the decklist clearly with card quantities like:
    Creatures:
    4x [Card Name]
    3x [Card Name]
    etc.
    """
    return generate_deck_from_prompt(session, enhanced_prompt, model)

def generate_deck_from_prompt(session, prompt, model="llama2"):
    """
    Use Ollama to generate a deck based on a theme/prompt
    Args:
        session: SQLAlchemy session
        prompt: str - Theme and constraints for the deck
        model: str - Ollama model to use
    Returns:
        dict: Deck information and card list
    """
    import requests
    from requests.exceptions import RequestException

    print(f"\nUsing AI model: {model}")
    print("Generating deck suggestion...")

    # Enhance the prompt with specific deck building instructions
    enhanced_prompt = f"""
    Create a Magic: The Gathering deck based on this theme: {prompt}
    Requirements:
    - 60 cards total for main deck
    - Follow standard Magic format rules
    - Include card quantities
    - Group by card type (Creatures, Spells, Lands)
    - Explain key synergies and strategy
    
    Format the decklist clearly with card quantities like:
    Creatures:
    4x Lightning Bolt
    3x Mountain
    etc.
    """

    try:
        # First check if Ollama is running
        print("Checking Ollama service...", end=' ')
        test_response = requests.get('http://localhost:11434/api/tags', timeout=2)
        if test_response.status_code != 200:
            raise Exception("Ollama service is not running")
        print("✓ Connected")

        print("Generating deck suggestion...", end=' ')
        # Call Ollama API
        response = requests.post('http://localhost:11434/api/generate', 
            json={
                "model": model,
                "prompt": enhanced_prompt,
                "stream": True
            },
            stream=True,  # Enable streaming
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama API returned status code {response.status_code}")

        # Handle streaming response
        deck_suggestion = ""
        for line in response.iter_lines():
            if line:
                try:
                    json_response = json.loads(line)
                    if 'response' in json_response:
                        deck_suggestion += json_response['response']
                except json.JSONDecodeError:
                    continue

        print("✓ Done")
        
        print("Parsing deck suggestion...", end=' ')
        # Extract card names and quantities
        deck_list = parse_deck_suggestion(deck_suggestion)
        print("✓ Done")
        
        # Verify cards exist in database
        verified_deck = verify_cards(session, deck_list)
        
        return {
            'theme': prompt,
            'strategy': deck_suggestion,
            'deck_list': verified_deck
        }
        
    except RequestException as e:
        if "Connection refused" in str(e):
            raise Exception("Cannot connect to Ollama. Please ensure Ollama is running (http://localhost:11434)")
        raise Exception(f"Network error while connecting to Ollama: {str(e)}")
    except Exception as e:
        raise Exception(f"Failed to generate deck with Ollama: {str(e)}")

def parse_deck_suggestion(suggestion):
    """Parse the AI's deck suggestion into a structured format"""
    import re
    
    deck_list = {
        'creatures': [],
        'spells': [],
        'lands': []
    }
    
    current_section = None
    quantity_pattern = r'(\d+)x?\s+(.+?)(?=\(|$|\n)'
    
    for line in suggestion.split('\n'):
        line = line.strip()
        
        # Determine section
        lower_line = line.lower()
        if 'creatures' in lower_line or 'creature' in lower_line:
            current_section = 'creatures'
            continue
        elif 'lands' in lower_line or 'land' in lower_line:
            current_section = 'lands'
            continue
        elif any(x in lower_line for x in ['spells', 'instant', 'sorcery', 'enchantment', 'artifact']):
            current_section = 'spells'
            continue
            
        if current_section and line:
            # Try to extract quantity and card name
            matches = re.findall(quantity_pattern, line)
            if matches:
                for match in matches:
                    try:
                        quantity = int(match[0])
                        card_name = match[1].strip()
                        if card_name:  # Only add if we have a card name
                            deck_list[current_section].append({
                                'quantity': quantity,
                                'name': card_name
                            })
                    except ValueError:
                        continue
    
    return deck_list

def verify_cards(session, deck_list):
    """Verify all cards exist in database and get their details"""
    verified_deck = {
        'creatures': [],
        'spells': [],
        'lands': [],
        'missing': [],
        'substitutions': []
    }
    
    def find_alternatives(card_name):
        """Find alternative cards in database"""
        # Remove any text in parentheses or after dashes
        clean_name = re.sub(r'\s*[-\(].*', '', card_name).strip()
        
        # Try exact match first
        card = session.query(Card).filter(func.lower(Card.name) == func.lower(clean_name)).first()
        if card:
            return [card]
            
        # If no exact match, try fuzzy search
        alternatives = session.query(Card).filter(
            Card.name.ilike(f"%{clean_name}%")
        ).order_by(Card.name).limit(5).all()
        
        # If still no matches, try searching by type for similar cards
        if not alternatives and "zombie" in clean_name.lower():
            alternatives = session.query(Card).filter(
                Card.type.ilike("%Zombie%")
            ).order_by(Card.name).limit(5).all()
            
        return alternatives

    # Process each card without GUI
    for category in ['creatures', 'spells', 'lands']:
        for card in deck_list[category]:
            card_name = card['name']
            quantity = card['quantity']
            
            # Try to find the card or alternatives
            db_card = session.query(Card).filter(Card.name == card_name).first()
            
            if db_card:
                # Card found exactly
                verified_deck[category].append({
                    'quantity': quantity,
                    'name': db_card.name,
                    'type': db_card.type,
                    'rarity': db_card.rarity,
                    'set': db_card.set_code,
                    'text': db_card.text
                })
            else:
                # Try to find alternatives
                alternatives = find_alternatives(card_name)
                if alternatives:
                    # Use the first alternative
                    alt_card = alternatives[0]
                    verified_deck[category].append({
                        'quantity': quantity,
                        'name': alt_card.name,
                        'type': alt_card.type,
                        'rarity': alt_card.rarity,
                        'set': alt_card.set_code,
                        'text': alt_card.text
                    })
                    verified_deck['substitutions'].append({
                        'original': card_name,
                        'replacement': alt_card.name,
                        'alternatives': [{
                            'name': alt.name,
                            'type': alt.type,
                            'rarity': alt.rarity,
                            'set': alt.set_code,
                            'text': alt.text
                        } for alt in alternatives]
                    })
                else:
                    # No alternatives found
                    verified_deck['missing'].append(card_name)
    
    # Print verification summary
    print("\nVerification Summary:")
    print(f"  Found: {sum(len(verified_deck[cat]) for cat in ['creatures', 'spells', 'lands'])} cards")
    print(f"  Missing: {len(verified_deck['missing'])} cards")
    print(f"  Substitutions: {len(verified_deck['substitutions'])} cards")
    
    if verified_deck['substitutions']:
        print("\nSubstitutions made:")
        for sub in verified_deck['substitutions']:
            print(f"  {sub['original']} → {sub['replacement']}")
    
    print("-" * 50)
    
    return verified_deck

def display_deck(deck_info, session=None):
    """Display the generated deck in a formatted way"""
    print("\n=== Generated Deck ===")
    print(f"Theme: {deck_info['theme']}")
    print("\nStrategy:")
    print(deck_info['strategy'])
    
    print("\nVerified Deck List:")
    total_cards = 0
    
    for category in ['creatures', 'spells', 'lands']:
        if deck_info['deck_list'][category]:
            print(f"\n{category.title()}:")
            category_total = 0
            for card in deck_info['deck_list'][category]:
                quantity = card['quantity']
                category_total += quantity
                print(f"{quantity}x {card['name']} ({card['set']} - {card['rarity']})")
                print(f"    Type: {card['type']}")
                if card.get('text'):
                    print(f"    Text: {card['text']}")
            print(f"Total {category}: {category_total}")
            total_cards += category_total
    
    print(f"\nTotal cards in deck: {total_cards}")
    
    if deck_info['deck_list']['missing']:
        print("\nWarning: Missing cards:")
        for card in deck_info['deck_list']['missing']:
            print(f"- {card}")
    
    if deck_info['deck_list']['substitutions']:
        print("\nSuggested Substitutions:")
        for sub in deck_info['deck_list']['substitutions']:
            print(f"\nFor {sub['original']}, consider:")
            for alt in sub['alternatives']:
                print(f"- {alt['name']} ({alt['set']} - {alt['rarity']})")
                print(f"  Type: {alt['type']}")
                if alt.get('text'):
                    print(f"  Text: {alt['text']}")

    # Ask if user wants to view cards
    if session:
        view_cards = input("\nWould you like to view these cards in the card viewer? (y/n): ")
        if view_cards.lower() == 'y':
            # Extract all card names from the deck
            card_names = []
            for category in ['creatures', 'spells', 'lands']:
                for card in deck_info['deck_list'][category]:
                    card_names.append(card['name'])
            
            # Open popup viewer with the first card name as initial search
            # The user can then easily search for other cards in the deck
            initial_search = card_names[0] if card_names else ""
            print("\nDeck cards to view:")
            for name in card_names:
                print(f"- {name}")
            print("\nOpening card viewer with first card. You can search for others from the list above.")
            
            popup_card_viewer(session, initial_search)

def save_deck(deck_info, filename):
    """Save deck to a file"""
    import json
    with open(filename, 'w') as f:
        json.dump(deck_info, f, indent=2)
    print(f"\nDeck saved to {filename}")

def show_deck_builder_popup(session):
    """Display a popup window for the deck builder interface"""
    if tk is None:
        print("Tkinter is not available on this system.")
        return

    # Create popup window
    builder_window = tk.Toplevel()
    builder_window.title("MTG Deck Builder")
    builder_window.geometry("600x800")
    
    # Add button frame for tools
    tools_frame = ttk.Frame(builder_window, padding="10")
    tools_frame.pack(fill=tk.X, padx=10, pady=5)
    
    def show_card_grid(session, parent, initial_search="", on_select_callback=None):
        """
        Display a grid of cards with search functionality
        Args:
            session: SQLAlchemy session
            parent: Parent tkinter widget
            initial_search: Initial search term
            on_select_callback: Function to call when a card is selected
        """
        import tkinter as tk
        from tkinter import ttk
        
        # Search frame
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=5)
        
        search_var = tk.StringVar(value=initial_search)
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(fill=tk.X)
        
        # Create Treeview
        tree = ttk.Treeview(
            parent,
            columns=("Name", "Type", "Rarity", "Set"),
            show="headings",
            height=15
        )
        
        # Configure columns
        for col in ("Name", "Type", "Rarity", "Set"):
            tree.heading(col, text=col)
            tree.column(col, width=150 if col in ("Name", "Type") else 100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Grid layout
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def update_grid(event=None):
            """Update grid with search results"""
            search_term = search_var.get().strip()
            tree.delete(*tree.get_children())
            
            cards = session.query(Card).filter(
                Card.name.ilike(f"%{search_term}%")
            ).order_by(Card.name).all()
            
            for card in cards:
                tree.insert("", tk.END, values=(
                    card.name,
                    card.type,
                    card.rarity,
                    card.set_code
                ))
        
        def on_select(event):
            """Handle card selection"""
            if on_select_callback:
                selection = tree.selection()
                if selection:
                    card_name = tree.item(selection[0])["values"][0]
                    on_select_callback(card_name)
        
        # Bind events
        search_entry.bind('<Return>', update_grid)
        search_var.trace_add("write", lambda *args: update_grid())
        tree.bind('<<TreeviewSelect>>', on_select)
        
        # Initial population
        update_grid()
    
    def open_card_search():
        """Opens the card viewer in a new window"""
        # Get the currently selected text in prompt_text if any
        try:
            selected_text = prompt_text.get("sel.first", "sel.last")
        except tk.TclError:
            selected_text = ""  # No selection
        
        # Create a new window for the card viewer
        search_window = tk.Toplevel(builder_window)
        search_window.title("Card Search")
        
        # Create main frame for the card viewer
        main_frame = ttk.Frame(search_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        def on_card_selected(card_name):
            """Callback when a card is selected in the viewer"""
            # Insert the card name at the current cursor position in prompt_text
            prompt_text.insert(tk.INSERT, f"[[{card_name}]] ")
            search_window.focus_set()  # Keep focus on search window
        
        # Initialize the card viewer with the selected text as initial search
        show_card_grid(
            session=session,
            parent=main_frame,
            initial_search=selected_text,
            on_select_callback=on_card_selected
        )
    
    # Add Search Cards button to tools frame
    search_button = ttk.Button(
        tools_frame,
        text="Search Cards",
        command=open_card_search,
        style="Tool.TButton"
    )
    search_button.pack(side=tk.LEFT, padx=5)
    
    # Style configuration
    style = ttk.Style()
    style.configure("Generate.TButton", 
        padding=10, 
        font=('Arial', 12, 'bold')
    )
    style.configure("Tool.TButton",
        padding=5,
        font=('Arial', 10)
    )
    
    # Create frames
    input_frame = ttk.Frame(builder_window, padding="10")
    input_frame.pack(fill=tk.X, padx=10, pady=5)
    
    output_frame = ttk.Frame(builder_window, padding="10")
    output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    # Prompt input
    ttk.Label(input_frame, text="Deck Theme:", font=('Arial', 12)).pack(anchor=tk.W)
    prompt_text = tk.Text(input_frame, height=4, width=50, font=('Arial', 11))
    prompt_text.pack(fill=tk.X, pady=5)

    def check_ollama_connection():
        """Check Ollama connection and update status"""
        if check_ollama_status():
            ollama_status_label.config(text="Ollama Status: Connected", foreground="green")
            generate_button.config(state=tk.NORMAL)
            model_combo.config(state="readonly")
            save_button.config(state=tk.NORMAL)
        else:
            ollama_status_label.config(text="Ollama Status: Not Connected", foreground="red")
            generate_button.config(state=tk.DISABLED)
            model_combo.config(state=tk.DISABLED)
            save_button.config(state=tk.DISABLED)
        builder_window.after(5000, check_ollama_connection)  # Check every 5 seconds

    model_frame = ttk.Frame(input_frame)
    model_frame.pack(fill=tk.X, pady=5)
    ttk.Label(model_frame, text="Model:", font=('Arial', 12)).pack(side=tk.LEFT)
    
    # Get available models
    available_models = get_ollama_models()
    model_var = tk.StringVar(value="llama2")
    model_combo = ttk.Combobox(model_frame, 
        textvariable=model_var,
        values=available_models,
        state="readonly",
        width=20
    )
    model_combo.pack(side=tk.LEFT, padx=5)
    
    # Add Ollama status indicator
    ollama_status_label = ttk.Label(model_frame, text="Checking Ollama...", font=('Arial', 10))
    ollama_status_label.pack(side=tk.LEFT, padx=10)
    
    # Add refresh models button
    def refresh_models():
        available_models = get_ollama_models()
        model_combo['values'] = available_models
        if model_var.get() not in available_models:
            model_var.set(available_models[0])
    
    refresh_button = ttk.Button(model_frame, text="↻", width=3, command=refresh_models)
    refresh_button.pack(side=tk.LEFT)
    
    # Output area
    output_text = tk.Text(output_frame, height=20, width=60, font=('Arial', 11))
    output_text.pack(fill=tk.BOTH, expand=True)
    
    # Progress bar
    progress_var = tk.StringVar(value="Ready")
    progress_label = ttk.Label(output_frame, textvariable=progress_var)
    progress_label.pack(pady=5)
    
    # Save button (initially disabled)
    save_button = ttk.Button(output_frame, text="Save Deck", state=tk.DISABLED)
    save_button.pack(pady=5)
    
    def update_output(message):
        output_text.insert(tk.END, message + "\n")
        output_text.see(tk.END)
        output_text.update()
    
    def save_generated_deck():
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Deck As"
        )
        if file_path and hasattr(builder_window, 'deck_info'):
            save_deck(builder_window.deck_info, file_path)
            update_output(f"\nDeck saved to {file_path}")
    
    def generate_deck():
        prompt = prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showerror("Error", "Please enter a deck theme")
            return

        if not check_ollama_status():
            messagebox.showerror("Error", "Ollama is not connected. Please start Ollama and try again.")
            return

        # Now we can access the Listbox through builder_window
        selected_cards = [builder_window.selected_cards_list.get(i) 
                         for i in range(builder_window.selected_cards_list.size())]

        
        try:
            progress_var.set("Generating deck...")
            deck_info = generate_deck_with_constraints(session, prompt, selected_cards, model_var.get())

            # Update the deck preview
            update_deck_preview(deck_info)

            # Store deck info for saving
            builder_window.deck_info = deck_info

            progress_var.set("Deck generation complete")
        except Exception as e:
            messagebox.showerror("Error", f"Error generating deck: {e}")
            progress_var.set("Generation failed")
            save_button.config(state=tk.DISABLED)
            output_text.delete("1.0", tk.END)
    
    def add_card_selection_panel():
        """Add a panel for selecting cards."""
        card_selection_frame = ttk.Frame(builder_window, padding="10")
        card_selection_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card_selection_frame, text="Select Cards:", font=('Arial', 12)).pack(anchor=tk.W)

        def on_card_selected(card_name):
            """Callback when a card is selected."""
            builder_window.selected_cards_list.insert(tk.END, card_name)

        show_card_grid(session, card_selection_frame, on_select_callback=on_card_selected)

        # Store the Listbox as an attribute of builder_window
        builder_window.selected_cards_list = tk.Listbox(card_selection_frame, height=10)
        builder_window.selected_cards_list.pack(fill=tk.BOTH, expand=True, pady=5)

        def remove_selected_card():
            """Remove the selected card from the list."""
            builder_window.selected_cards_list.delete(tk.ANCHOR)

        remove_button = ttk.Button(card_selection_frame, text="Remove Selected Card", command=remove_selected_card)
        remove_button.pack(pady=5)

    def add_deck_preview():
        """Add a real-time preview of the deck."""
        deck_preview_frame = ttk.Frame(builder_window, padding="10")
        deck_preview_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(deck_preview_frame, text="Deck Preview:", font=('Arial', 12)).pack(anchor=tk.W)

        deck_preview_text = tk.Text(deck_preview_frame, height=15, state=tk.DISABLED)
        deck_preview_text.pack(fill=tk.BOTH, expand=True, pady=5)

        def update_deck_preview(deck_info):
            """Update the deck preview with the generated deck."""
            deck_preview_text.configure(state=tk.NORMAL)
            deck_preview_text.delete("1.0", tk.END)
            for category, cards in deck_info['deck_list'].items():
                deck_preview_text.insert(tk.END, f"\n{category.title()}:\n")
                for card in cards:
                    deck_preview_text.insert(tk.END, f"{card['quantity']}x {card['name']}\n")
            deck_preview_text.configure(state=tk.DISABLED)

        return update_deck_preview

    add_card_selection_panel()
    update_deck_preview = add_deck_preview()

    # Generate button
    generate_button = ttk.Button(
        input_frame,
        text="Generate Deck",
        command=generate_deck,
        style="Generate.TButton"
    )
    generate_button.pack(pady=10)
    
    # Configure save button
    save_button.configure(command=save_generated_deck)
    
    # Center window
    builder_window.update_idletasks()
    width = builder_window.winfo_width()
    height = builder_window.winfo_height()
    x = (builder_window.winfo_screenwidth() // 2) - (width // 2)
    y = (builder_window.winfo_screenheight() // 2) - (height // 2)
    builder_window.geometry(f'{width}x{height}+{x}+{y}')
    
    builder_window.mainloop()

# ---------------------
# Main CLI and Subcommand Handling
# ---------------------
def get_free_port():
    """Get a free port on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

class DownloadHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        """Handle POST requests with selected downloads"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        selections = json.loads(post_data.decode('utf-8'))
        
        # Store selections in class variable
        DownloadHandler.selected_downloads = selections
        
        # Send response
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Downloads received")
        
        # Stop the server
        threading.Thread(target=self.server.shutdown).start()

def show_web_download_selector():
    """Shows MTGJSON downloads page in default web browser"""
    # Start local server to receive selection
    port = get_free_port()
    server = HTTPServer(('localhost', port), DownloadHandler)
    
    # Create and start server thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # Open MTGJSON downloads page
    webbrowser.open('https://mtgjson.com/downloads/all-files/')
    
    # Wait for server to receive selection and shutdown
    server_thread.join()
    
    # Return the selections
    return getattr(DownloadHandler, 'selected_downloads', [])

def countdown_timer(seconds):
    """Display a countdown timer"""
    for remaining in tqdm(range(seconds, 0, -1), desc="Opening file selector in"):
        time.sleep(1)  # Use time.sleep instead of datetime.time.sleep

def show_file_selector():
    """Shows file dialog for selecting ZIP files"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    file_types = [
        ('ZIP files', '*.zip'),
        ('All files', '*.*')
    ]
    
    file_path = filedialog.askopenfilename(
        title='Select MTGJSON ZIP File',
        filetypes=file_types,
        initialdir='.'
    )
    
    if file_path:
        # Extract category from filename
        filename = os.path.basename(file_path)
        category = filename.split('.')[0]  # Remove .json.zip extension
        return category, file_path
    
    return None, None

def download_selected(db_path=None):
    """Handle the file selection and processing"""
    print("MTGJSON File Selector")
    print("-" * 50)
    print("1. The file dialog will open in 5 seconds")
    print("2. Select your downloaded MTGJSON ZIP file")
    print("3. The file will be processed and added to the database")
    print("-" * 50)
    
    # Show countdown timer
    countdown_timer(20)
    
    # Show file selector
    category, file_path = show_file_selector()
    
    if not file_path:
        print("No file selected. Operation cancelled.")
        return

    print(f"\nProcessing file: {os.path.basename(file_path)}")
    print(f"Category: {category}")
    
    # Initialize database session
    session, _ = init_db(db_path) if db_path else init_db()
    
    try:
        # Process the selected file
        process_file(file_path, category, session)
        print("\nFile processing completed successfully.")
        
    except Exception as e:
        print(f"\nError processing file: {e}")
        
    finally:
        session.close()

def add_deckbuilder_subcommand(subparsers):
    """Add the deckbuilder subcommand to the argument parser"""
    deck_parser = subparsers.add_parser("build-deck", 
        help="Generate a deck based on a theme using AI")
    deck_parser.add_argument('--gui', action='store_true',
        help="Launch graphical deck builder interface")
    deck_parser.add_argument('--prompt', type=str,
        help="Description of the desired deck theme")
    deck_parser.add_argument('--model', type=str, default="dorian2b/vera:latest",  # Changed default model
        help="Ollama model to use (default: dorian2b/vera:latest)")
    deck_parser.add_argument('--save', type=str,
        help="Save deck to specified file")
    return deck_parser

def check_dependencies():
    """Check if all required dependencies are installed"""
    missing_deps = []
    
    try:
        import sqlalchemy
    except ImportError:
        missing_deps.append("sqlalchemy")
    
    try:
        import requests
    except ImportError:
        missing_deps.append("requests")
    
    try:
        from tqdm import tqdm
    except ImportError:
        missing_deps.append("tqdm")
    
    if missing_deps:
        print("\n❌ Missing required dependencies:")
        print("Please install them using pip:\n")
        print(f"pip install {' '.join(missing_deps)}")
        print("\nAfter installing, run the tutorial again.")
        return False
    return True

def show_tutorial():
    """Display an interactive tutorial for administrators"""
    # Get the current Python executable path
    python_exe = sys.executable
    
    # Check dependencies first
    if not check_dependencies():
        return

    tutorial_text = """
╔════════════════════════════════════════════════════════════════╗
║                 MTG Database Manager Tutorial                   ║
╚════════════════════════════════════════════════════════════════╝

Welcome! This tutorial will guide you through the main features of the MTG Database Manager.

1️⃣ Initial Setup
----------------
First, you'll need to set up your database:

    python mtgdb_manager.py manage-links fetch
    python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip

2️⃣ Database Management
---------------------
Check your database status:

    python mtgdb_manager.py db-manager stats
    python mtgdb_manager.py db-manager list

3️⃣ Card Viewing Options
---------------------
There are two ways to view cards:

CLI Viewer:
    python mtgdb_manager.py view --search "Lightning Bolt"

Graphical Viewer:
    python mtgdb_manager.py popup --name "Black Lotus"

4️⃣ Deck Building
--------------
Use the AI-powered deck builder:

GUI Mode:
    python mtgdb_manager.py build-deck --gui

CLI Mode:
    python mtgdb_manager.py build-deck --prompt "Aggressive dragon tribal deck"

5️⃣ Common Administrative Tasks
---------------------------
• Reinitialize database:
    python mtgdb_manager.py db-manager init

• Update MTGJSON links:
    python mtgdb_manager.py manage-links fetch

• Select local files:
    python mtgdb_manager.py select-download --new-db custom_db.db

Would you like to:
1. Open the documentation in your browser
2. Run database status check
3. Launch the card viewer
4. Exit tutorial

Enter your choice (1-4): """

    while True:
        print(tutorial_text)
        choice = input().strip()
        
        try:
            if choice == '1':
                webbrowser.open('https://github.com/unaveragetech/Horde/blob/main/MTG_DATABASE_MANAGER_COMMANDS.md')
            elif choice == '2':
                subprocess.run([python_exe, 'mtgdb_manager.py', 'db-manager', 'stats'])
            elif choice == '3':
                subprocess.run([python_exe, 'mtgdb_manager.py', 'popup'])
            elif choice == '4':
                print("\nTutorial completed! You can always access command help using --help")
                print("Example: python mtgdb_manager.py <command> --help")
                break
            else:
                print("\nInvalid choice. Please enter a number between 1 and 4.")
        except Exception as e:
            print(f"\nError: {str(e)}")
            print("Please ensure you're running the script from within the virtual environment:")
            print("1. Activate the virtual environment:")
            print("   Windows: .venv\\Scripts\\activate")
            print("   Unix: source .venv/bin/activate")
            print("2. Run the script again:")
            print("   python mtgdb_manager.py intro")
        
        input("\nPress Enter to continue...")

def main():
    parser = argparse.ArgumentParser(
        description="MTGJSON Database Manager, Downloader, and Card Viewer"
    )
    parser.add_argument('--db', type=str, default="mtg_cards.db", help="Path to the SQLite DB file")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands", required=True)
    
    # Add intro/tutorial subcommand
    intro_parser = subparsers.add_parser("intro", 
        help="Interactive tutorial for administrators",
        description="Displays an interactive tutorial covering main features and common administrative tasks")

    # Select-download subcommand
    select_download_parser = subparsers.add_parser("select-download", 
        help="Select and process a local MTGJSON ZIP file",
        description="Example: python mtgdb_manager.py select-download --new-db my_cards.db")
    select_download_parser.add_argument('--new-db', type=str, 
        help="Create new database at specified path")

    # Download subcommand
    download_parser = subparsers.add_parser("download", 
        help="Download and process MTGJSON files",
        description="""
Examples:
  python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip
  python mtgdb_manager.py download --list-file downloads.txt --category CustomSet
""")
    download_group = download_parser.add_mutually_exclusive_group(required=True)
    download_group.add_argument('--urls', nargs='+', help="One or more file URLs to download")
    download_group.add_argument('--list-file', type=str, help="Path to a file with category,url entries (one per line)")
    download_parser.add_argument('--category', type=str, default="AllPrintings", help="Category of the file(s)")

    # View subcommand
    view_parser = subparsers.add_parser("view", 
        help="CLI card viewer",
        description="Example: python mtgdb_manager.py view --search \"Lightning Bolt\"")
    view_parser.add_argument('--search', type=str, required=True, help="Search term for card names")

    # Popup subcommand
    popup_parser = subparsers.add_parser("popup", 
        help="Popup card viewer with searchable grid",
        description="Example: python mtgdb_manager.py popup --name \"Black Lotus\"")
    popup_parser.add_argument('--name', type=str, required=False, help="Initial search term (optional)")

    # DB Manager subcommand
    db_parser = subparsers.add_parser("db-manager", 
        help="Database management utilities",
        description="""
Examples:
  python mtgdb_manager.py db-manager stats
  python mtgdb_manager.py db-manager list
  python mtgdb_manager.py db-manager init
""")
    db_parser.add_argument("action", choices=["stats", "list", "init"], 
        help="Action: 'stats' to view DB stats, 'list' to list card entries, 'init' to reinitialize the DB")

    # Build-deck subcommand
    deck_parser = subparsers.add_parser("build-deck", 
        help="Generate a deck based on a theme using AI",
        description="""
Examples:
  python mtgdb_manager.py build-deck --gui
  python mtgdb_manager.py build-deck --prompt "Aggressive dragon tribal deck" --model llama2
  python mtgdb_manager.py build-deck --prompt "Blue control deck" --save my_deck.json
""")
    deck_parser.add_argument('--gui', action='store_true', help="Launch graphical deck builder interface")
    deck_parser.add_argument('--prompt', type=str, help="Description of the desired deck theme")
    deck_parser.add_argument('--model', type=str, default="dorian2b/vera:latest", 
        help="Ollama model to use (default: dorian2b/vera:latest)")
    deck_parser.add_argument('--save', type=str, help="Save deck to specified file")

    # Manage-links subcommand
    link_parser = subparsers.add_parser("manage-links", 
        help="Manage MTGJSON download links",
        description="""
Examples:
  python mtgdb_manager.py manage-links fetch
  python mtgdb_manager.py manage-links list
""")
    link_subparsers = link_parser.add_subparsers(dest="link_action", required=True)
    link_fetch = link_subparsers.add_parser("fetch", help="Fetch and store MTGJSON download links")
    link_fetch.add_argument("--db", type=str, default="mtg_links.db", help="Links database path")
    link_list = link_subparsers.add_parser("list", help="List stored MTGJSON download links")
    link_list.add_argument("--db", type=str, default="mtg_links.db", help="Links database path")

    args = parser.parse_args()

    if args.command == "intro":
        show_tutorial()
        return

    if args.command == "select-download":
        download_selected(args.new_db)
    
    # Initialize DB session.
    reset = (args.command == "db-manager" and args.action == "init")
    session, engine = init_db(args.db, reset=reset)

    if args.command == "download":
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
        popup_card_viewer(session, args.name if args.name else "")

    elif args.command == "db-manager":
        if args.action == "stats":
            db_stats(session)
        elif args.action == "list":
            db_list_entries(session)
        elif args.action == "init":
            print("Database reinitialized.")

    elif args.command == "manage-links":
        link_session = init_link_db(args.db)  # Remove the .session() call
        if args.link_action == "fetch":
            links = fetch_mtgjson_files()
            for link in links:
                link_session.merge(link)
            link_session.commit()
            print(f"Stored {len(links)} links")
        elif args.link_action == "list":
            list_stored_links(link_session)

    elif args.command == "build-deck":
        if args.gui:
            show_deck_builder_popup(session)
        else:
            try:
                deck_info = generate_deck_from_prompt(session, args.prompt, args.model)
                display_deck(deck_info, session)  # Pass the session to enable card viewing
                if args.save:
                    save_deck(deck_info, args.save)
            except Exception as e:
                print(f"Error generating deck: {e}")

if __name__ == "__main__":
    main()
