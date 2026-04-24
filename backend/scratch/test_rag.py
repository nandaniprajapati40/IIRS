import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from rag_kb import get_chat_answer

def test_rag():
    print("Testing LangChain RAG Pipeline...")
    
    queries = [
        "What is SAVI?",
        "SAVI kya hai?",  # Hinglish
        "How is Kc calculated?",
        "Kc kaise calculate karte hain?",  # Hinglish
        "Tell me about IIRS Dehradun"
    ]
    
    live_data = {
        "savi": 0.65,
        "kc": 0.95,
        "cwr": 4.2,
        "iwr": 2.1
    }
    
    for q in queries:
        print(f"\nQuery: {q}")
        try:
            response = get_chat_answer(q, live_data=live_data)
            print(f"Answer: {response['answer']}")
            print(f"Sources: {response['sources']}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_rag()
