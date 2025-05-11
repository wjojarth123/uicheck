#!/usr/bin/env python3
"""
Example script demonstrating the use of the HTML cleaner module
"""
from html_cleaner import clean_html_tags, clean_html_string

def file_example():
    """Example of cleaning an HTML file"""
    try:
        input_file = "example.html"
        
        # Create a sample HTML file if it doesn't exist
        with open(input_file, "w") as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Example Page</title>
    <style>
        body { font-family: Arial; color: #333; }
        .container { margin: 0 auto; width: 800px; }
    </style>
    <script>
        function showAlert() {
            alert('Hello, world!');
        }
    </script>
</head>
<body>
    <div class="container" data-test="test" data-value="123">
        <h1 id="title">Example Page</h1>
        <p onclick="showAlert()">Click me to show an alert</p>
        <svg width="100" height="100" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="50" cy="50" r="40" stroke="black" stroke-width="2" fill="red" />
        </svg>
    </div>
    <script>
        console.log('Page loaded');
    </script>
</body>
</html>""")
        
        # Clean the HTML file
        output_file = clean_html_tags(input_file)
        
        print(f"File cleaned successfully! Output saved to: {output_file}")
        
        # Display the content of the cleaned file
        with open(output_file, "r") as f:
            print("\nCleaned HTML content:")
            print("-" * 50)
            print(f.read())
            print("-" * 50)
            
    except Exception as e:
        print(f"Error in file example: {e}")

def string_example():
    """Example of cleaning an HTML string"""
    try:
        # Sample HTML string
        html_string = """
        <div class="container" data-test="test" data-value="123">
            <h1 id="title">Example String</h1>
            <p onclick="showAlert()">This is a test paragraph</p>
            <script>alert('This should be removed');</script>
            <style>.test { color: red; }</style>
        </div>
        """
        
        # Clean the HTML string
        cleaned_html = clean_html_string(html_string)
        
        print("\nCleaned HTML string:")
        print("-" * 50)
        print(cleaned_html)
        print("-" * 50)
        
    except Exception as e:
        print(f"Error in string example: {e}")

if __name__ == "__main__":
    print("HTML Cleaner Module Examples\n")
    file_example()
    string_example() 