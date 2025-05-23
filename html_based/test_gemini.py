import os
import google.generativeai as genai

# Add dotenv support to load .env file
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

# Configure the API
print(f"Configuring Gemini API with key: {GEMINI_API_KEY[:4]}...{GEMINI_API_KEY[-4:]}")
genai.configure(api_key=GEMINI_API_KEY)

# Test the model
model_name = "models/gemini-2.0-flash"
print(f"Testing model: {model_name}")

try:
    # Initialize the model
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "max_output_tokens": 100,
            "temperature": 0.7,
        }
    )
    
    # Test with a simple prompt
    prompt = "Give me 3 suggestions for a weekend activity. Keep it brief."
    print(f"\nSending prompt: {prompt}")
    
    response = model.generate_content(prompt)
    
    print("\nResponse from Gemini:")
    print("-" * 40)
    print(response.text)
    print("-" * 40)
    print("Test successful!")
    
except Exception as e:
    print(f"Error testing Gemini model: {e}")
    import traceback
    traceback.print_exc() 