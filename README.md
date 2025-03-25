
<div align="center">

# 🎴 MTG Database Manager

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-green.svg)](https://www.sqlalchemy.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

*A powerful toolkit for managing, downloading, and viewing Magic: The Gathering card data with advanced features and AI-powered deck building.*

[Features](#✨-features) • [Installation](#🚀-installation) • [Usage](#💫-usage) • [Documentation](#📖-documentation) • [Contributing](#🤝-contributing)

![MTG Database Manager Demo](assets/demo.gif)

</div>

## ✨ Features

### 🔄 Data Management
- **Multi-threaded Downloads**: Efficiently download MTGJSON files with concurrent processing
- **Smart Caching**: Intelligent caching system for improved performance
- **Version Control**: Track and manage database versions
- **Automatic Updates**: Stay current with the latest MTGJSON releases

### 🔍 Card Viewing
- **Dual Interface System**:
  - 📝 CLI viewer for quick searches and scripting
  - 🖼️ GUI popup viewer with rich card details
- **Advanced Search**:
  - Filter by name, type, rarity, set, and more
  - Regular expression support
  - Color combination filtering

### 🎮 Interactive Features
- **Real-time Card Preview**:
  - Dynamic mana symbol rendering
  - Particle effects for mythic rares
  - Smooth animations and transitions
- **Keyboard Shortcuts**:
  - Quick navigation
  - Custom keybindings
  - Clipboard integration

### 🤖 AI-Powered Tools
- **Deck Building Assistant**:
  - Theme-based deck generation
  - Card synergy analysis
  - Format-specific recommendations
- **Collection Management**:
  - Inventory tracking
  - Price monitoring
  - Trade suggestions

## 🚀 Installation

### Prerequisites
- Python 3.9 or higher
- pip package manager
- Git (for cloning)

### Quick Start
```bash
# Clone the repository
git clone https://github.com/unaveragetech/Horde.git
cd Horde

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Unix
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize database
python mtgdb_manager.py manage-links fetch
python mtgdb_manager.py db-manager init
```

## 💫 Usage

### 📥 Download Manager
```bash
# Download specific set
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/DOM.json.zip --category Dominaria

# Batch download from list
python mtgdb_manager.py download --list-file sets.txt
```

### 🔎 Card Search
```bash
# CLI search
python mtgdb_manager.py view --search "Dragon" --field type

# Launch GUI viewer
python mtgdb_manager.py popup --name "Black Lotus"
```

### 🎲 Deck Building
```bash
# GUI deck builder
python mtgdb_manager.py build-deck --gui

# AI-powered deck generation
python mtgdb_manager.py build-deck --prompt "Modern Goblin tribal deck"
```

## 📖 Documentation

### 📚 Command Reference
| Command | Description | Example |
|---------|-------------|---------|
| `download` | Download MTGJSON files | `download --urls URL` |
| `view` | CLI card viewer | `view --search "Bolt"` |
| `popup` | GUI card viewer | `popup --name "Lotus"` |
| `build-deck` | Deck builder | `build-deck --gui` |

### 🎯 Advanced Usage
- [Detailed Commands Guide](docs/COMMANDS.md)
- [API Documentation](docs/API.md)
- [Configuration Guide](docs/CONFIG.md)

## 🛠️ Development

### Project Structure
```
mtg-db-manager/
├── src/
│   ├── database/      # Database models and operations
│   ├── downloaders/   # File download management
│   ├── viewers/       # Card viewing interfaces
│   └── utils/         # Helper functions
├── tests/             # Test suite
├── docs/              # Documentation
└── assets/            # Images and resources
```

### Running Tests
```bash
pytest tests/
```

## 🤝 Contributing

We welcome contributions! See our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

- [MTGJSON](https://mtgjson.com/) - Comprehensive MTG data
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [Tkinter](https://docs.python.org/3/library/tkinter.html) - GUI framework
- [tqdm](https://github.com/tqdm/tqdm) - Progress bars
- [requests](https://docs.python-requests.org/) - HTTP client

## 📬 Contact

- **Issues**: [GitHub Issues](https://github.com/unaveragetech/Horde/issues)
- **Email**: maintainer@example.com
- **Twitter**: [@MTGDBManager](https://twitter.com/MTGDBManager)

---

<div align="center">

Made with ❤️ by [UnavergeTech](https://github.com/unaveragetech)

</div>
