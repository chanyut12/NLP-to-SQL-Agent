"""
RAG Store Module for Thai NLP-to-SQL Agent (Enhanced)

This module provides dynamic few-shot example retrieval using ChromaDB
with persistence, dialect filtering, and metadata support.
"""

import json
import os
import asyncio
from typing import List, Dict, Optional, Any
import logging
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from core.utils.common import generate_stable_id
from core.utils.embedding import load_sentence_transformer
from core.config import settings


logger = logging.getLogger(__name__)


def _norm_dialect(d: Optional[str]) -> str:
    d = (d or "").lower()
    return "postgresql" if d in ("postgres", "postgresql") else d


class ExampleStore:
    """
    Vector store for Thai-to-SQL examples using ChromaDB (Persistent).
    Retrieves semantically similar examples for few-shot prompting.
    """
    
    def __init__(
        self,
        examples_path: str = "thai_sql_examples.json",
        model_name: str = None,
        persist_directory: Optional[str] = "rag_db",
        profile: str = "default",
    ):
        """
        Initialize the example store.
        """
        self.examples_path = examples_path
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.persist_directory = persist_directory
        # One collection per domain profile so a profile switch never mixes corpora.
        self.collection_name = f"thai_sql_examples_{profile}"

        # Eagerly load embedding model at startup (not on first query)
        logger.info("Loading embedding model: %s", self.model_name)
        self._embedder = load_sentence_transformer(self.model_name)

        # Initialize ChromaDB
        if self.persist_directory:
            os.makedirs(self.persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.persist_directory)
        else:
            self.client = chromadb.Client(Settings(anonymized_telemetry=False))
        
        # Embedding cache: (text,) -> embedding list  (avoids re-encoding same question)
        self._embedding_cache: Dict[str, list] = {}

        # Load or create collection
        self._init_collection()
    
    @property
    def embedder(self):
        return self._embedder

    def _init_collection(self):
        """Initialize or load the vector collection."""
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Thai to SQL examples for few-shot learning"}
        )
        
        # Sync examples from file
        self._sync_examples()

    def _sync_examples(self):
        """Load examples from JSON file and upsert them only if new."""
        if not os.path.exists(self.examples_path):
            logger.warning("Examples file not found: %s", self.examples_path)
            return
        
        with open(self.examples_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        examples = data.get("examples", [])
        if not examples:
            return
            
        # Check existing IDs to avoid re-embedding
        existing_ids = set()
        if self.collection.count() > 0:
            existing = self.collection.get(include=[]) # Get only IDs
            existing_ids = set(existing['ids'])

        new_ids = []
        new_embeddings = []
        new_documents = []
        new_metadatas = []
        
        # Only process examples that are not in DB
        for ex in examples:
            question = ex.get("question", "")
            sql = ex.get("sql", "")
            category = ex.get("category", "general")
            dialect = ex.get("dialect", "sqlite")
            difficulty = ex.get("difficulty", "medium")
            tags = ex.get("retrieval_tags", [])

            ex_id = generate_stable_id(question, sql)

            if ex_id in existing_ids:
                continue

            # E5 models require 'passage: ' prefix for documents being indexed.
            # Curated retrieval_tags (Thai synonyms) are appended so paraphrases hit.
            passage = question if not tags else f"{question} | {' '.join(tags)}"
            embedding = self.embedder.encode(f"passage: {passage}").tolist()

            new_ids.append(ex_id)
            new_embeddings.append(embedding)
            new_documents.append(sql)
            new_metadatas.append({
                "question": question,
                "category": category,
                "dialect": dialect,
                "difficulty": difficulty,
            })
        
        # Batch upsert only new items
        if new_ids:
            logger.info("Syncing %s new examples to RAG store.", len(new_ids))
            self.collection.upsert(
                ids=new_ids,
                embeddings=new_embeddings,
                documents=new_documents,
                metadatas=new_metadatas
            )
        else:
            logger.info("RAG store is up to date. No new examples to sync.")

    def _cached_encode(self, text: str) -> list:
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        emb = self.embedder.encode(text).tolist()
        self._embedding_cache[text] = emb
        if len(self._embedding_cache) > 500:
            keys = list(self._embedding_cache.keys())
            for k in keys[:200]:
                del self._embedding_cache[k]
        return emb

    def get_similar_examples(
        self,
        query: str,
        top_k: int = 3,
        dialect: Optional[str] = None,
        threshold: Optional[float] = None,
        auto_transpile: bool = True
    ) -> List[Dict[str, str]]:
        """
        Retrieve semantically similar examples with automatic dialect conversion.

        Args:
            query: User's question
            top_k: Number of examples
            dialect: If provided, prefers or filters by this dialect
            threshold: Distance threshold for filtering (default: None)
            auto_transpile: If True, automatically convert SQL to target dialect

        Returns:
            List of examples with SQL converted to target dialect
        """
        if top_k <= 0:
            return []

        text_to_embed = f"query: {query}"
        query_embedding = self._cached_encode(text_to_embed)

        # Strategy: fetch 2x results WITHOUT dialect filter, then prioritize
        # dialect-matching ones. This avoids a double-query.
        fetch_k = top_k * 2 if dialect else top_k

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"]
        )

        examples = []
        if results and results['documents'] and results['documents'][0]:
            dialect_matches = []
            other_matches = []

            for i in range(len(results['documents'][0])):
                distance = results['distances'][0][i]
                if threshold is not None and distance > threshold:
                    continue

                sql = results['documents'][0][i]
                metadata = results['metadatas'][0][i]
                question = metadata.get('question', '')
                source_dialect = metadata.get("dialect", "sqlite")

                entry = {
                    "question": question,
                    "sql": sql,
                    "dialect": dialect if auto_transpile else source_dialect,
                    "distance": distance,
                    "_source_dialect": source_dialect,
                }

                if dialect and _norm_dialect(source_dialect) == _norm_dialect(dialect):
                    dialect_matches.append(entry)
                else:
                    other_matches.append(entry)

            # Prioritize dialect-matching, fill remaining with others
            examples = dialect_matches[:top_k]
            remaining = top_k - len(examples)
            if remaining > 0:
                examples.extend(other_matches[:remaining])

        # Auto-transpile non-matching dialects
        if auto_transpile and dialect:
            for ex in examples:
                source_dialect = ex.pop("_source_dialect", None)
                if source_dialect and _norm_dialect(source_dialect) != _norm_dialect(dialect):
                    try:
                        from core.utils.dialect_transpiler import DialectTranspiler

                        dialect_map = {
                            "sqlite": "SQLite",
                            "mysql": "MySQL",
                            "postgresql": "PostgreSQL",
                            "postgres": "PostgreSQL"
                        }
                        source = dialect_map.get(source_dialect.lower(), source_dialect)
                        target = dialect_map.get(dialect.lower(), dialect)

                        transpiled_sql = DialectTranspiler.transpile(
                            ex["sql"], source, target, pretty=True
                        )
                        if transpiled_sql:
                            ex["sql"] = transpiled_sql
                    except Exception as e:
                        logger.warning(
                            "RAG: Transpilation failed (%s -> %s): %s",
                            source_dialect, dialect, e,
                        )

        return examples
    
    def format_examples_for_prompt(
        self,
        query: str,
        top_k: int = 3,
        dialect: Optional[str] = None,
        threshold: Optional[float] = None,
        auto_transpile: bool = True
    ) -> str:
        """
        Get similar examples formatted as a string with automatic dialect conversion.

        Args:
            query: User's question
            top_k: Number of examples to retrieve
            dialect: Target SQL dialect (sqlite, mysql, postgresql)
            threshold: Distance threshold for filtering
            auto_transpile: Auto-convert SQL to target dialect (default: True)

        Returns:
            Formatted examples string for prompt
        """
        examples = self.get_similar_examples(
            query, top_k, dialect, threshold, auto_transpile
        )

        if not examples:
            return ""

        formatted = []
        for ex in examples:
            # We can show dialect in the example if we want
            # formatted.append(f"Question: {ex['question']} ({ex['dialect']})\nSQL: {ex['sql']}")
            formatted.append(f"Question: {ex['question']}\nSQL: {ex['sql']}")

        return "\n\n".join(formatted)

    async def async_format_examples_for_prompt(
        self,
        query: str,
        top_k: int = 3,
        dialect: Optional[str] = None,
        threshold: Optional[float] = None,
        auto_transpile: bool = True
    ) -> str:
        """
        Async version of format_examples_for_prompt with automatic dialect conversion.
        Wraps blocking embedding/query operations in asyncio.to_thread.

        Args:
            query: User's question
            top_k: Number of examples to retrieve
            dialect: Target SQL dialect (sqlite, mysql, postgresql)
            threshold: Distance threshold for filtering
            auto_transpile: Auto-convert SQL to target dialect (default: True)

        Returns:
            Formatted examples string for prompt
        """
        return await asyncio.to_thread(
            self.format_examples_for_prompt,
            query, top_k, dialect, threshold, auto_transpile
        )

    async def async_format_examples_for_prompt_with_count(
        self,
        query: str,
        top_k: int = 3,
        dialect: Optional[str] = None,
        threshold: Optional[float] = None,
        auto_transpile: bool = True
    ) -> tuple:
        """Same as async_format_examples_for_prompt but also returns retrieved count."""
        examples = await asyncio.to_thread(
            self.get_similar_examples, query, top_k, dialect, threshold, auto_transpile
        )
        count = len(examples)
        if not examples:
            return "", 0
        formatted = "\n\n".join(
            f"Question: {ex['question']}\nSQL: {ex['sql']}"
            for ex in examples
        )
        return formatted, count


def create_example_store(
    examples_path: str = "thai_sql_examples.json",
    persist_directory: Optional[str] = "rag_db",
    profile: str = "default",
) -> ExampleStore:
    return ExampleStore(examples_path, persist_directory=persist_directory, profile=profile)

if __name__ == "__main__":
    # Test
    store = create_example_store()
    print("Test retrieve:", store.get_similar_examples("ยอดขายรวม"))
