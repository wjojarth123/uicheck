import os
import google.generativeai as genai

try:
    from dotenv import load_dotenv
    # Load environment variables from .env file
    load_dotenv()
    print("INFO: Loaded environment variables from .env file")
except ImportError:
    print("WARNING: python-dotenv not installed.")

# Configure the Gemini API with your API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# If API key not found in environment, try to read it directly from .env file
if not GEMINI_API_KEY:
    try:
        with open(".env", "r") as env_file:
            for line in env_file:
                if line.strip().startswith("GEMINI_API_KEY"):
                    key_parts = line.strip().split("=", 1)
                    if len(key_parts) == 2:
                        GEMINI_API_KEY = key_parts[1].strip()
                        print("INFO: Loaded Gemini API key directly from .env file")
                        break
    except FileNotFoundError:
        print("WARNING: .env file not found")
    except Exception as e:
        print(f"WARNING: Error reading .env file: {e}")

if not GEMINI_API_KEY:
    GEMINI_API_KEY = input("Please enter your Gemini API key: ")

genai.configure(api_key=GEMINI_API_KEY)

print("\nListing available Gemini models:\n" + "="*30)
try:
    models = genai.list_models()
    for model in models:
        print(f"Name: {model.name}")
        print(f"Display name: {model.display_name}")
        print(f"Description: {model.description}")
        print(f"Supported generation methods: {', '.join(model.supported_generation_methods)}")
        print("-" * 30)
except Exception as e:
    print(f"Error listing models: {e}")
    import traceback
    traceback.print_exc() 