#!/usr/bin/env python3
import sys
import os
from html_cleaner import clean_html_tags, clean_html_string

def main():
    """
    Main function to run the HTML cleaner application
    """
    if len(sys.argv) < 2:
        print("Usage: python clean_html_app.py <input_file> [output_file]")
        print("OR")
        print("Usage: python clean_html_app.py --string '<html_content>'")
        sys.exit(1)
    
    # Check if we're processing a string or a file
    if sys.argv[1] == "--string":
        if len(sys.argv) < 3:
            print("Error: HTML content string is required when using --string option")
            sys.exit(1)
        
        # Process HTML string
        html_content = sys.argv[2]
        result = clean_html_string(html_content)
        
        if result:
            print("Cleaned HTML Content:")
            print(result)
        else:
            print("Failed to clean HTML content.")
            sys.exit(1)
    else:
        # Process file
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
        
        if not os.path.exists(input_file):
            print(f"Error: Input file '{input_file}' not found.")
            sys.exit(1)
            
        result = clean_html_tags(input_file, output_file)
        
        if result:
            print(f"Successfully cleaned HTML file. Output saved to: {result}")
        else:
            print("Failed to clean HTML file.")
            sys.exit(1)

if __name__ == "__main__":
    main() 