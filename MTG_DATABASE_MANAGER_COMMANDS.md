# MTG Database Manager - Complete Command Reference

## Table of Contents
1. [Global Options](#global-options)
2. [Download Command](#download)
3. [View Command](#view)
4. [Popup Command](#popup)
5. [Database Manager Command](#database-manager)
6. [Link Manager Command](#link-manager)

## Global Options
Options available for all commands:

```bash
--db <path>    # Specify custom database path (default: mtg_cards.db)
```

## Download
Downloads and processes MTGJSON files.

### Syntax
```bash
python mtgdb_manager.py download [options]
```

### Options
```bash
--urls <url1> [url2...]    # One or more MTGJSON file URLs
--list-file <path>         # File containing category,url pairs
--category <name>          # Category name (default: AllPrintings)
```

### Examples
```bash
# Single file download
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip

# Multiple files from list
python mtgdb_manager.py download --list-file downloads.txt

# Custom category
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/MH2.json.zip --category ModernHorizons2
```

## View
CLI-based card viewer with advanced search capabilities.

### Syntax
```bash
python mtgdb_manager.py view [options]
```

### Options
```bash
--search <term>    # Required: Search term
--field <field>    # Field to search in (default: name)
                   # Valid fields: name, type, rarity, set, text, uuid
```

### Examples
```bash
# Search by name
python mtgdb_manager.py view --search "Lightning Bolt"

# Search by type
python mtgdb_manager.py view --search "Creature Dragon" --field type

# Search by rarity
python mtgdb_manager.py view --search "mythic" --field rarity

# Search by set
python mtgdb_manager.py view --search "CMM" --field set

# Search by card text
python mtgdb_manager.py view --search "flying" --field text

# Search by UUID
python mtgdb_manager.py view --search "b264084b" --field uuid
```

### Output Format
```
----------------------------------------
Name: <card_name>
UUID: <card_uuid>
Type: <card_type>
Rarity: <card_rarity>
Set: <set_code>
Text: <card_text>
----------------------------------------
```

## Popup
Graphical card viewer interface.

### Syntax
```bash
python mtgdb_manager.py popup [options]
```

### Options
```bash
--name <cardname>    # Initial search term (optional)
```

### Examples
```bash
# Open empty viewer
python mtgdb_manager.py popup

# Open with search
python mtgdb_manager.py popup --name "Black Lotus"
```

### GUI Features
- Real-time search filtering
- Sortable columns
- Color-coded rarities
- Detailed card view on selection
- Next/Previous navigation for multiple results

## Database Manager
Database maintenance and information utilities.

### Syntax
```bash
python mtgdb_manager.py db-manager <action>
```

### Actions
```bash
stats    # View database statistics
list     # List all card entries
init     # Reinitialize the database
```

### Examples
```bash
# View statistics
python mtgdb_manager.py db-manager stats

# List entries
python mtgdb_manager.py db-manager list

# Reinitialize
python mtgdb_manager.py db-manager init
```

### Stats Output Format
```
Database Statistics:
Total Cards: <count>
Total Sets: <count>
Cards by Rarity:
  - Common: <count>
  - Uncommon: <count>
  - Rare: <count>
  - Mythic: <count>
```

## Link Manager
MTGJSON download link management.

### Syntax
```bash
python mtgdb_manager.py manage-links <action>
```

### Actions
```bash
fetch    # Fetch and store latest MTGJSON links
list     # Display stored links
```

### Examples
```bash
# Update links
python mtgdb_manager.py manage-links fetch

# View links
python mtgdb_manager.py manage-links list
```

## Common Workflows

### Initial Setup
```bash
# First-time setup
python mtgdb_manager.py manage-links fetch
python mtgdb_manager.py download --urls https://mtgjson.com/api/v5/AllPrintings.json.zip
```

### Database Update
```bash
# Check current status
python mtgdb_manager.py db-manager stats

# Update database
python mtgdb_manager.py manage-links fetch
python mtgdb_manager.py download --list-file updates.txt
```

### Card Research
```bash
# Quick CLI lookup
python mtgdb_manager.py view --search "Dragon" --field name

# Detailed GUI browsing
python mtgdb_manager.py popup
```

## Error Handling

The system provides detailed error messages for common issues:

- Download failures
- Invalid URLs
- Database connection errors
- Invalid search fields
- File permission issues

Example error output:
```
Error downloading file: HTTP Error 404: Not Found
Error connecting to database: Database is locked
Error: Invalid search field 'invalid_field'
```

## Tips and Best Practices

1. **Database Management**
   - Regularly backup your database
   - Use `db-manager stats` to verify updates
   - Run `init` only when necessary

2. **Efficient Searching**
   - Use specific fields for targeted searches
   - Combine searches for complex queries
   - Use GUI for browsing, CLI for specific lookups

3. **Performance**
   - Use list files for bulk downloads
   - Keep database properly indexed
   - Regular maintenance with db-manager

4. **Custom Configurations**
   - Use custom database paths for different sets
   - Create aliases for common commands
   - Set up automated update scripts