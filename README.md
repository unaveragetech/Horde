
```markdown
# MTGJSON Database Manager, Downloader, and Card Viewer

This Python script provides tools for managing, downloading, and viewing Magic: The Gathering JSON data from [MTGJSON](https://mtgjson.com/). It offers multiple subcommands for different functionalities, such as downloading data, viewing card details in the command line or a popup window, and managing the SQLite database.

## Features

- **Download MTGJSON Files**: Download one or more files from MTGJSON, extract them, and update the SQLite database.
- **CLI Card Viewer**: Search and list card details directly from the command line.
- **Popup Card Viewer**: Display detailed card information using a Tkinter popup window.
- **Database Management**: Utilities for viewing database stats, listing entries, and reinitializing the database.
- **Manage MTGJSON Links**: Fetch and store MTGJSON download links dynamically.

## Installation

1. **Clone the repository**:
    ```bash
    git clone https://github.com/unaveragetech/Horde.git
    cd Horde
    ```

2. **Install the required dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Download MTGJSON Files
Download and process MTGJSON files:
```bash
# Download a single file
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip --category AllPrintings

# Download multiple files via a list file (each line: <category>,<url>)
python mtgdb_manager.py download --list-file urls.txt
```

### CLI Card Viewer
View cards by searching for a name keyword:
```bash
python mtgdb_manager.py view --search "Goblin"
```

### Popup Card Viewer
Popup viewer for a specific card (if multiple, cycle through them):
```bash
python mtgdb_manager.py popup --name "Lightning Bolt"
```

### Database Manager
Utilities for managing the SQLite database:
```bash
# View database stats
python mtgdb_manager.py db-manager stats

# List card entries
python mtgdb_manager.py db-manager list

# Reinitialize the database
python mtgdb_manager.py db-manager init
```

### Manage MTGJSON Links
Fetch and store MTGJSON download links:
```bash
# Fetch and store links
python mtgdb_manager.py manage-links fetch

# List stored links
python mtgdb_manager.py manage-links list
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you have any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements

- [MTGJSON](https://mtgjson.com/) for providing comprehensive Magic: The Gathering data.
- [SQLAlchemy](https://www.sqlalchemy.org/) for ORM support.
- [Tkinter](https://docs.python.org/3/library/tkinter.html) for GUI support.
- [tqdm](https://github.com/tqdm/tqdm) for progress bars.
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing.
- [requests](https://docs.python-requests.org/en/master/) for HTTP requests.

## Contact

For any questions or feedback, please reach out via the repository's issue tracker or contact the maintainer directly.
```

