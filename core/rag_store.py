"""
RAG Store Module for Thai NLP-to-SQL Agent (Enhanced)

This module provides dynamic few-shot example retrieval using ChromaDB
with persistence, dialect filtering, and metadata support.
"""

import json
import os
import hashlib
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


class ExampleStore:
    """
    Vector store for Thai-to-SQL examples using ChromaDB (Persistent).
    Retrieves semantically similar examples for few-shot prompting.
    """
    
    # Multilingual model that supports Thai
    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    COLLECTION_NAME = "thai_sql_examples_v2"
    
    def __init__(
        self,
        examples_path: str = "thai_sql_examples.json",
        model_name: str = DEFAULT_MODEL,
        persist_directory: Optional[str] = "rag_db"
    ):
        """
        Initialize the example store.
        
        Args:
            examples_path: Path to JSON file containing examples
            model_name: Sentence transformer model for embeddings
            persist_directory: Directory to persist ChromaDB (default: 'rag_db')
        """
        self.examples_path = examples_path
        self.model_name = model_name
        self.persist_directory = persist_directory
        
        # Initialize embedding model (lazy load if possible, but usually needed immediately)
        print(f"Loading embedding model: {model_name}")
        self.embedder = SentenceTransformer(model_name)
        
        # Initialize ChromaDB
        if self.persist_directory:
            os.makedirs(self.persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.persist_directory)
        else:
            self.client = chromadb.Client(Settings(anonymized_telemetry=False))
        
        # Load or create collection
        self._init_collection()
    
    def _init_collection(self):
        """Initialize or load the vector collection."""
        # Note: In production, we don't delete every time.
        # But for dev consistency when dataset changes, we might want to sync.
        # Here we implement a sync strategy: Upsert based on ID.
        
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Thai to SQL examples for few-shot learning"}
        )
        
        # Sync examples from file
        self._sync_examples()
    
    def _generate_id(self, question: str, sql: str) -> str:
        """Generate a stable ID based on content."""
        content = f"{question.strip()}|{sql.strip()}"
        return hashlib.md5(content.encode()).hexdigest()

    def _sync_examples(self):
        """Load examples from JSON file and upsert them."""
        if not os.path.exists(self.examples_path):
            print(f"Warning: Examples file not found: {self.examples_path}")
            return
        
        with open(self.examples_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        examples = data.get("examples", [])
        if not examples:
            return
            
        print(f"Syncing {len(examples)} examples to RAG store...")
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for ex in examples:
            question = ex.get("question", "")
            sql = ex.get("sql", "")
            category = ex.get("category", "general")
            dialect = ex.get("dialect", "sqlite") # New field
            difficulty = ex.get("difficulty", "medium") # New field
            
            # ID stability
            ex_id = self._generate_id(question, sql)
            
            # Embed question ONLY (notes ไม่รวมเพราะทำให้ similarity ลดลง)
            # notes เก็บไว้ใน metadata สำหรับ reference เท่านั้น
            embedding = self.embedder.encode(question).tolist()
            
            ids.append(ex_id)
            embeddings.append(embedding)
            documents.append(sql)
            metadatas.append({
                "question": question,
                "category": category,
                "dialect": dialect,
                "difficulty": difficulty
            })
        
        # Batch upsert
        if ids:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        print("RAG store sync complete.")

    def get_similar_examples(
        self,
        query: str,
        top_k: int = 3,
        dialect: Optional[str] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, str]]:
        """
        Retrieve semantically similar examples.
        
        Args:
            query: User's question
            top_k: Number of examples
            dialect: If provided, prefers or filters by this dialect (optional future enhancement)
            threshold: Distance threshold for filtering (default: None)
        """
        query_embedding = self.embedder.encode(query).tolist()

        # Query with optional dialect filter
        # ถ้าระบุ dialect จะ filter เฉพาะ examples ที่ตรงกับ dialect นั้น
        where_filter = {"dialect": dialect} if dialect else None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        examples = []
        if results and results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                # Filter by distance if threshold is set
                distance = results['distances'][0][i]
                if threshold is not None and distance > threshold:
                    continue
                    
                sql = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                question = metadata.get('question', '')
                
                examples.append({
                    "question": question,
                    "sql": sql,
                    "dialect": metadata.get("dialect", "any"),
                    "distance": distance
                })
        
        return examples
    
    def format_examples_for_prompt(
        self,
        query: str,
        top_k: int = 3,
        dialect: Optional[str] = None,
        threshold: Optional[float] = None
    ) -> str:
        """Get similar examples formatted as a string."""
        examples = self.get_similar_examples(query, top_k, dialect, threshold)
        
        if not examples:
            return ""
        
        formatted = []
        for ex in examples:
            # We can show dialect in the example if we want
            # formatted.append(f"Question: {ex['question']} ({ex['dialect']})\nSQL: {ex['sql']}")
            formatted.append(f"Question: {ex['question']}\nSQL: {ex['sql']}")
        
        return "\n\n".join(formatted)

def create_example_store(
    examples_path: str = "thai_sql_examples.json",
    persist_directory: Optional[str] = "rag_db"
) -> ExampleStore:
    return ExampleStore(examples_path, persist_directory=persist_directory)

if __name__ == "__main__":
    # Test
    store = create_example_store()
    print("Test retrieve:", store.get_similar_examples("ยอดขายรวม"))
