#!/usr/bin/env python
"""
Webpage Summary Demo
This script demonstrates how to use the TaskAutomator class to generate 
webpage summaries using Cohere's language model.
"""

from task_automation import TaskAutomator
import argparse
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Webpage Summary Demo")
    parser.add_argument("--url", type=str, default="https://www.example.com",
                        help="URL to summarize (default: https://www.example.com)")
    parser.add_argument("--output", type=str, default="webpage_summary.json",
                        help="Output file for the summary (default: webpage_summary.json)")
    args = parser.parse_args()
    
    # Create the TaskAutomator instance
    automator = None
    
    try:
        print(f"\n=== Generating summary for {args.url} ===\n")
        
        # Create automator instance with Cohere
        automator = TaskAutomator(use_llama=False)
        
        # Navigate to the website
        automator.navigate_to(args.url)
        
        # Generate and display the webpage summary
        summary = automator.get_webpage_summary()
        
        # Pretty print the summary
        print("\n=== Webpage Summary ===\n")
        print(f"Page Type: {summary.get('page_type', 'Unknown')}")
        print(f"Main Purpose: {summary.get('main_purpose', 'Unknown')}")
        print("\nKey Information:")
        for info in summary.get('key_information', []):
            print(f"- {info}")
        
        print("\nAvailable Actions:")
        for action in summary.get('available_actions', []):
            print(f"- {action}")
        
        print(f"\nSummary: {summary.get('summary', 'No summary available')}")
        
        # Save the summary to a file
        with open(args.output, 'w') as f:
            json.dump(summary, f, indent=2)
            
        print(f"\nSummary saved to {args.output}")
        
        # Now try a functionality that uses chat history to prevent repetitive actions
        print("\n=== Demonstrating Chat History Functionality ===\n")
        print("Attempting to generate summary for the same page again...")
        
        # This should retrieve from history instead of generating a new summary
        second_summary = automator.get_webpage_summary()
        
        # Check if it's the same object (should be reused from history)
        if id(summary) == id(second_summary):
            print("✓ Successfully reused summary from history!")
        else:
            print("Generated new summary instead of reusing from history.")
            
        # Try a different URL to show that a new summary is generated
        print("\nNavigating to a different URL...")
        different_url = "https://www.wikipedia.org"
        automator.navigate_to(different_url)
        
        # This should generate a new summary
        new_summary = automator.get_webpage_summary()
        
        print(f"\n=== Summary for {different_url} ===\n")
        print(f"Page Type: {new_summary.get('page_type', 'Unknown')}")
        print(f"Main Purpose: {new_summary.get('main_purpose', 'Unknown')}")
        print(f"\nSummary: {new_summary.get('summary', 'No summary available')}")
        
    except KeyboardInterrupt:
        print("\n\nSummary generation interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Clean up
        if automator:
            try:
                automator.close()
            except Exception as e:
                print(f"Error during cleanup: {e}")
        print("\nExecution finished.")


if __name__ == "__main__":
    main() 