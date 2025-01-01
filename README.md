# Transifex Translation Management Script

A Python-based tool for managing translations through the Transifex API, with support for automated translation and review processes.

## Features

- Fetch untranslated and unreviewed strings from Transifex
- Automated translation processing
- Translation validation and review
- CSV export for translation management
- Support for multiple languages and resources
- Caching mechanism for efficient processing

## Prerequisites

- Python 3.10 or higher
- Transifex API access token
- OpenAI API key (for automated translations)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd transifex-script
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
   - Copy `.env.sample` to `.env`
   - Fill in the required values:
     ```
     TRANSIFEX_API_TOKEN=your_api_token
     TRANSIFEX_ORGANIZATION=your_organization
     TRANSIFEX_PROJECT=your_project
     TARGET_LANGUAGES=ar,fa  # Comma-separated list of language codes
     OPENAI_API_KEY=your_openai_api_key
     ```

## Configuration

The project uses a `transifex.yml` file to configure resource mappings and translation file patterns. Make sure to update this file according to your project structure.

## Usage

The script provides several commands for different translation management tasks:

### Fetch Untranslated Strings
```bash
python main.py fetch-strings --mode untranslated
```

### Fetch Unreviewed Strings
```bash
python main.py fetch-strings --mode unreviewed
```

### Translate Strings
```bash
python main.py translate --mode untranslated
```

### Review Translations
```bash
python main.py translate --mode unreviewed
```

### Update Transifex
To update translations in Transifex:
```bash
python main.py translate --mode untranslated --update-transifex
```

### Force Download
To bypass cache and force new downloads:
```bash
python main.py fetch-strings --mode untranslated --force-download
```

## Output Structure

- `output/`: Contains CSV files with downloaded strings
- `translations/`: Contains processed translations in JSON format
- Logs are printed to the console during execution

## Error Handling

The script includes error handling for:
- API connection issues
- Invalid configurations
- File processing errors
- Translation failures

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
