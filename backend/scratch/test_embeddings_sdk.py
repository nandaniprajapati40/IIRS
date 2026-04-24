import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

try:
    print("Testing models/text-embedding-004...")
    result = genai.embed_content(
        model="models/text-embedding-004",
        content="Hello world",
        task_type="retrieval_query"
    )
    print("Success with text-embedding-004!")
except Exception as e:
    print(f"Failed text-embedding-004: {e}")

try:
    print("\nTesting models/gemini-embedding-001...")
    result = genai.embed_content(
        model="models/gemini-embedding-001",
        content="Hello world",
        task_type="retrieval_query"
    )
    print("Success with gemini-embedding-001!")
except Exception as e:
    print(f"Failed gemini-embedding-001: {e}")
