# MTG Database Manager System Overview

## System Architecture

The MTG Database Manager is a comprehensive Python application that provides tools for managing Magic: The Gathering card data. It uses SQLAlchemy for database operations and features both CLI and GUI interfaces.

## Core Components

### 1. Database Models
- **Set**: Represents MTG sets with properties like code, name, and release date
- **Card**: Stores individual card details including UUID, name, type, rarity, and text
- **Link**: Manages downloadable MTGJSON file links

### 2. Command-Line Interface Tools

#### Download Command
- Downloads and processes MTGJSON files
- Supports both single and multiple URL downloads
- Features concurrent downloading through threading
- Progress tracking with tqdm
- Automatic file cleanup after processing

#### View Commands
1. **CLI Viewer** (`view`)
   - Text-based card search and display
   - Shows detailed card information including name, type, rarity, and text

2. **Popup Viewer** (`popup`)
   - GUI-based card viewer with advanced features
   - Supports card image loading from Scryfall
   - Interactive search functionality
   - Rarity-based styling and animations
   - Displays comprehensive card details

#### Database Management
- **Stats**: View database statistics (set and card counts)
- **List**: Display card entries with details
- **Init**: Reinitialize the database
- **Link Management**: Fetch and store MTGJSON download links

### 3. Deck Builder System

#### Features
- AI-powered deck generation using Ollama
- GUI interface for deck building
- Card selection and preview
- Support for multiple AI models
- Deck validation and verification
- Export capabilities

#### Components
- Card search and selection
- Theme-based deck generation
- Real-time deck preview
- Card verification against database
- Automatic substitution suggestions

### 4. User Interface Elements

#### Graphical Components
- Card grid with sorting capabilities
- Progress indicators
- Customizable card displays
- Animated card popups based on rarity
- Interactive search functionality

#### Styling Features
- MTG-specific color schemes
- Rarity-based visual effects
- Custom animations for different card types
- Responsive layouts

## Key Features

### 1. Data Management
- Efficient database operations with SQLAlchemy
- Concurrent file downloads
- Automatic file extraction and processing
- Database backup and restoration

### 2. Card Visualization
- Multiple viewing options (CLI/GUI)
- Detailed card information display
- Image integration with Scryfall API
- Custom styling and animations

### 3. Deck Building
- AI-assisted deck generation
- Theme-based deck creation
- Card verification and substitution
- Deck export and saving

### 4. Error Handling
- Comprehensive error catching
- User-friendly error messages
- Graceful failure recovery
- Input validation

### 5. Performance Features
- Threaded downloads
- Progress tracking
- Efficient database queries
- Responsive user interface

## Usage Examples

```bash
# Initialize database and fetch card data
python mtgdb_manager.py manage-links fetch
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip

# View cards using CLI
python mtgdb_manager.py view --search "Lightning Bolt"

# Launch interactive card viewer
python mtgdb_manager.py popup --name "Black Lotus"

# Use AI deck builder
python mtgdb_manager.py build-deck --gui
python mtgdb_manager.py build-deck --prompt "Aggressive dragon tribal deck"

# Database management
python mtgdb_manager.py db-manager stats
python mtgdb_manager.py db-manager list
```

## System Requirements

### Dependencies
- SQLAlchemy for database operations
- Requests for API interactions
- tqdm for progress tracking
- Tkinter for GUI components
- PIL for image processing
- BeautifulSoup for web scraping

### Optional Components
- Ollama for AI deck building
- Scryfall API integration for card images

## Future Improvements

1. **Enhanced Threading**
   - Improved concurrent operations
   - Better thread management
   - Progress synchronization

2. **Advanced UI Features**
   - More customization options
   - Additional animation effects
   - Enhanced card previews

3. **Expanded AI Integration**
   - More sophisticated deck building
   - Card synergy analysis
   - Meta analysis integration

4. **Data Management**
   - Improved caching
   - Better memory management
   - Optimized database queries
