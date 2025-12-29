"""
RAG Store Module for Thai NLP-to-SQL Agent

This module provides dynamic few-shot example retrieval using ChromaDB
and sentence-transformers for multilingual (Thai) embedding support.
"""

import json
import os
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class ExampleStore:
    """
    Vector store for Thai-to-SQL examples using ChromaDB.
    Retrieves semantically similar examples for few-shot prompting.
    """
    
    # Multilingual model that supports Thai
    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    COLLECTION_NAME = "thai_sql_examples"
    
    def __init__(
        self,
        examples_path: str = "thai_sql_examples.json",
        model_name: str = DEFAULT_MODEL,
        persist_directory: Optional[str] = None
    ):
        """
        Initialize the example store.
        
        Args:
            examples_path: Path to JSON file containing examples
            model_name: Sentence transformer model for embeddings
            persist_directory: Directory to persist ChromaDB (None for in-memory)
        """
        self.examples_path = examples_path
        self.model_name = model_name
        
        # Initialize embedding model
        print(f"Loading embedding model: {model_name}")
        self.embedder = SentenceTransformer(model_name)
        
        # Initialize ChromaDB
        if persist_directory:
            self.client = chromadb.PersistentClient(path=persist_directory)
        else:
            # In-memory client (faster for development)
            self.client = chromadb.Client(Settings(anonymized_telemetry=False))
        
        # Load or create collection
        self._init_collection()
    
    def _init_collection(self):
        """Initialize or load the vector collection."""
        # Delete existing collection if exists (to refresh on each run)
        try:
            self.client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        
        # Create new collection
        self.collection = self.client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Thai to SQL examples for few-shot learning"}
        )
        
        # Load and index examples
        self._load_examples()
    
    def _load_examples(self):
        """Load examples from JSON file and index them."""
        if not os.path.exists(self.examples_path):
            print(f"Warning: Examples file not found: {self.examples_path}")
            return
        
        with open(self.examples_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        examples = data.get("examples", [])
        
        if not examples:
            print("Warning: No examples found in file")
            return
        
        # Prepare data for ChromaDB
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        print(f"Indexing {len(examples)} examples...")
        
        for i, ex in enumerate(examples):
            question = ex.get("question", "")
            sql = ex.get("sql", "")
            category = ex.get("category", "general")
            
            # Generate embedding for the question
            embedding = self.embedder.encode(question).tolist()
            
            ids.append(f"ex_{i}")
            embeddings.append(embedding)
            documents.append(sql)  # Store SQL as document
            metadatas.append({
                "question": question,
                "category": category
            })
        
        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        print(f"Successfully indexed {len(examples)} examples")
    
    def get_similar_examples(
        self,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, str]]:
        """
        Retrieve semantically similar examples for a given query.
        
        Args:
            query: User's question (in Thai or English)
            top_k: Number of examples to retrieve
            
        Returns:
            List of dicts with 'question' and 'sql' keys
        """
        # Generate embedding for query
        query_embedding = self.embedder.encode(query).tolist()
        
        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        examples = []
        if results and results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                sql = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                question = metadata.get('question', '')
                
                examples.append({
                    "question": question,
                    "sql": sql
                })
        
        return examples
    
    def format_examples_for_prompt(
        self,
        query: str,
        top_k: int = 3
    ) -> str:
        """
        Get similar examples formatted as a string for prompt injection.
        
        Args:
            query: User's question
            top_k: Number of examples to retrieve
            
        Returns:
            Formatted string of examples
        """
        examples = self.get_similar_examples(query, top_k)
        
        if not examples:
            return ""
        
        formatted = []
        for ex in examples:
            formatted.append(f"Question: {ex['question']}\nSQL: {ex['sql']}")
        
        return "\n\n".join(formatted)


def create_example_store(
    examples_path: str = "thai_sql_examples.json",
    persist_directory: Optional[str] = None
) -> ExampleStore:
    """
    Factory function to create an ExampleStore instance.
    
    Args:
        examples_path: Path to examples JSON file
        persist_directory: Optional directory to persist the vector store
        
    Returns:
        ExampleStore instance
    """
    return ExampleStore(
        examples_path=examples_path,
        persist_directory=persist_directory
    )


# Quick test when run directly
if __name__ == "__main__":
    print("Testing RAG Store...")
    
    store = create_example_store()
    
    # Test queries
    test_queries = [
        "ยอดขายของเดือนธันวาคม",
        "ลูกค้าคนไหนซื้อมากที่สุด",
        "จำนวนใบเสร็จทั้งหมด"
    ]
    
    for query in test_queries:
        print(f"\n--- Query: {query} ---")
        examples = store.get_similar_examples(query, top_k=2)
        for ex in examples:
            print(f"  Q: {ex['question']}")
            print(f"  SQL: {ex['sql'][:60]}...")

