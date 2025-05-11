# HTML Cleaner

A Python tool to clean HTML by removing script and style tags completely, as well as stripping unwanted attributes while preserving SVG content.

## Features

- Removes all script and style tags completely (not just their contents)
- Preserves SVG content
- Keeps only specific HTML attributes (title, href, class, id)
- Can process both files and HTML strings
- Simple command-line interface

## Requirements

- Python 3.6+
- BeautifulSoup4

## Installation

1. Clone or download this repository
2. Install the required dependencies:

```bash
pip install beautifulsoup4
```

## Usage

### As a Command-Line Tool

To clean an HTML file:

```bash
python clean_html_app.py input.html [output.html]
```

If no output file is specified, the result will be saved to `input_cleaned.html`.

To clean an HTML string:

```bash
python clean_html_app.py --string "<html><script>alert('hello');</script><div class='keep' data-remove='true'>Content</div></html>"
```

### As a Module in Your Project

Import the functions to use in your Python code:

```python
from html_cleaner import clean_html_tags, clean_html_string

# Clean a file
clean_html_tags('input.html', 'output.html')

# Clean a string
html_content = "<html><script>alert('hello');</script><div>Content</div></html>"
cleaned_html = clean_html_string(html_content)
print(cleaned_html)
```

## Functions

- `clean_html_tags(input_file, output_file=None)`: Cleans HTML from a file and saves to another file
- `clean_html_string(html_content)`: Cleans HTML content provided as a string

## License

MIT 