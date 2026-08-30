"""
Schema RAG Module for Smart Schema Retrieval

This module provides semantic search for database schema,
with Thai-English mapping support for improved Local LLM accuracy.
"""

import asyncio
import threading
from typing import List, Dict, Optional, Any, Set
import logging
from sentence_transformers import SentenceTransformer
import chromadb
from sqlalchemy import Engine, inspect

from core.utils.common import generate_stable_id
from core.utils.embedding import load_sentence_transformer
from core.profiles import load_schema_mappings


logger = logging.getLogger(__name__)



class SchemaRAG:
    """
    Vector store for database schema with Thai-English mapping support.
    Uses ChromaDB for semantic search of relevant tables/columns.
    """
    
    def __init__(
        self,
        model_name: str = None,
        persist_directory: Optional[str] = "schema_rag_db",
        embedder: Optional[SentenceTransformer] = None,
        embedding_cache: Optional[Dict[str, list]] = None,
        embedding_lock: Optional[threading.Lock] = None,
        profile: str = "default",
    ):
        """
        Initialize the Schema RAG store.
        
        Args:
            model_name: Sentence transformer model for embeddings
            persist_directory: Directory to persist ChromaDB
            embedder: Optional shared SentenceTransformer instance
            embedding_cache: Optional shared embedding cache dict
        """
        from core.config import settings
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.persist_directory = persist_directory
        self.collection_name = f"schema_metadata_{profile}"
        # Thai-term -> table/column name fragments, per domain profile.
        self.thai_mappings = load_schema_mappings(profile)
        self._embedder = embedder
        self._embedding_cache = embedding_cache if embedding_cache is not None else {}
        self._embedding_cache_lock = embedding_lock or threading.Lock()
        self._client = None
        self._collection = None
        self._indexed_tables: Set[str] = set()
        
    def _get_embedder(self) -> SentenceTransformer:
        """Get or lazy load the embedding model."""
        if self._embedder is None:
            logger.info("Loading schema embedding model: %s", self.model_name)
            self._embedder = load_sentence_transformer(self.model_name)
        return self._embedder

    def _cached_encode(self, text: str) -> list:
        with self._embedding_cache_lock:
            hit = self._embedding_cache.get(text)
        if hit is not None:
            return hit
        emb = self._get_embedder().encode(text).tolist()
        with self._embedding_cache_lock:
            self._embedding_cache[text] = emb
            if len(self._embedding_cache) > 500:
                for k in list(self._embedding_cache.keys())[:200]:
                    self._embedding_cache.pop(k, None)
        return emb
    
    def _get_collection(self):
        """Get or create the ChromaDB collection."""
        if self._collection is None:
            import os
            if self.persist_directory:
                os.makedirs(self.persist_directory, exist_ok=True)
                self._client = chromadb.PersistentClient(path=self.persist_directory)
            else:
                self._client = chromadb.Client()
            
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Database schema for semantic retrieval"}
            )
        return self._collection
    
    def _create_thai_description(self, table_name: str, columns: List[str]) -> str:
        """
        Create Thai-enhanced description for a table.
        This helps the embedding model understand Thai queries.
        """
        # Find Thai terms that map to this table or its columns
        thai_terms = []
        
        table_lower = table_name.lower()
        cols_lower = [c.lower() for c in columns]
        
        for thai_word, english_terms in self.thai_mappings.items():
            for eng_term in english_terms:
                eng_lower = eng_term.lower()
                # Check if mapping matches table name
                if eng_lower in table_lower or table_lower in eng_lower:
                    thai_terms.append(thai_word)
                    break
                # Check if mapping matches any column
                if any(eng_lower in col or col in eng_lower for col in cols_lower):
                    thai_terms.append(thai_word)
                    break
        
        thai_str = " ".join(set(thai_terms)) if thai_terms else ""
        cols_str = ", ".join(columns[:10])  # Limit to 10 columns
        
        return f"Table: {table_name} Columns: {cols_str} Thai: {thai_str}"
    
    def index_schema_from_db(self, engine: Engine, force_reindex: bool = False):
        """
        Index database schema into the vector store.
        
        Args:
            engine: SQLAlchemy engine
            force_reindex: If True, re-index even if already indexed
        """
        from core.domain.schema_utils import is_denylisted

        inspector = inspect(engine)
        table_names = [t for t in inspector.get_table_names() if not is_denylisted(t)]
        try:
            table_names += [v for v in inspector.get_view_names() if not is_denylisted(v)]
        except Exception:
            pass

        # Check if already indexed
        collection = self._get_collection()
        if not force_reindex and collection.count() > 0:
            # Check if tables match
            existing = collection.get()
            if existing and existing.get('metadatas'):
                existing_tables = {m.get('table') for m in existing['metadatas'] if m.get('table')}
                if existing_tables == set(table_names):
                    logger.info("Schema already indexed (%s tables). Skipping.", len(table_names))
                    self._indexed_tables = existing_tables
                    return

        logger.info("Indexing schema: %s tables...", len(table_names))
        
        embedder = self._get_embedder()
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for table in table_names:
            try:
                cols_info = inspector.get_columns(table)
                col_names = [col["name"] for col in cols_info]
                
                # Create rich description for embedding
                description = self._create_thai_description(table, col_names)
                # E5 models require 'passage: ' prefix for documents being indexed
                text_to_embed = f"passage: {description}"
                embedding = embedder.encode(text_to_embed).tolist()
                
                ids.append(generate_stable_id(table))
                embeddings.append(embedding)
                documents.append(description)
                metadatas.append({
                    "table": table,
                    "columns": ",".join(col_names),
                    "column_count": len(col_names)
                })
                
                self._indexed_tables.add(table)
                
            except Exception as e:
                logger.warning("Could not index table %s: %s", table, e)
                continue
        
        if ids:
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        
        logger.info("Schema indexing complete. %s tables indexed.", len(ids))
    
    def get_relevant_tables(
        self,
        question: str,
        top_k: int = 5,
        include_mapped: bool = True
    ) -> List[str]:
        """
        Get relevant table names based on semantic similarity to question.
        
        Args:
            question: User's question (can be Thai or English)
            top_k: Maximum number of tables to return
            include_mapped: Also include tables from Thai keyword mapping
            
        Returns:
            List of relevant table names
        """
        relevant_tables: Set[str] = set()
        
        # 1. Thai keyword mapping (fast, rule-based)
        if include_mapped:
            mapped = self._get_mapped_tables(question)
            relevant_tables.update(mapped)
        
        # 2. Semantic search
        collection = self._get_collection()
        if collection.count() == 0:
            logger.warning("Schema not indexed. Returning all tables.")
            return list(self._indexed_tables)
        
        text_to_embed = f"query: {question}"
        query_embedding = self._cached_encode(text_to_embed)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        if results and results['metadatas'] and results['metadatas'][0]:
            for metadata in results['metadatas'][0]:
                table = metadata.get('table')
                if table:
                    relevant_tables.add(table)
        
        return list(relevant_tables)
    
    async def async_get_relevant_tables(
        self,
        question: str,
        top_k: int = 5,
        include_mapped: bool = True
    ) -> List[str]:
        """
        Async version of get_relevant_tables.
        Wraps blocking embedding/query operations in asyncio.to_thread.
        """
        return await asyncio.to_thread(
            self.get_relevant_tables,
            question, top_k, include_mapped
        )
    
    def _get_mapped_tables(self, question: str) -> Set[str]:
        """
        Get tables based on Thai keyword mapping (rule-based, fast).
        
        Args:
            question: User's question
            
        Returns:
            Set of table names from mapping
        """
        mapped_tables: Set[str] = set()
        question_lower = question.lower()
        
        for thai_word, english_terms in self.thai_mappings.items():
            if thai_word in question:
                for term in english_terms:
                    term_lower = term.lower()
                    # Check if term matches any indexed table
                    for table in self._indexed_tables:
                        if term_lower in table.lower() or table.lower() in term_lower:
                            mapped_tables.add(table)
        
        return mapped_tables
    
    def get_table_relationships(self) -> Dict[str, List[str]]:
        """
        Infer likely table relationships based on common column naming patterns.
        This helps with JOIN suggestions.
        
        Returns:
            Dict mapping table to list of likely related tables
        """
        collection = self._get_collection()
        if collection.count() == 0:
            return {}
        
        existing = collection.get()
        if not existing or not existing.get('metadatas'):
            return {}
        
        # Build column -> tables mapping
        column_tables: Dict[str, List[str]] = {}
        for metadata in existing['metadatas']:
            table = metadata.get('table', '')
            columns = metadata.get('columns', '').split(',')
            for col in columns:
                col = col.strip()
                if col:
                    if col not in column_tables:
                        column_tables[col] = []
                    column_tables[col].append(table)
        
        # Find tables that share columns (likely need JOINs)
        relationships: Dict[str, List[str]] = {}
        for metadata in existing['metadatas']:
            table = metadata.get('table', '')
            columns = metadata.get('columns', '').split(',')
            related = set()
            
            for col in columns:
                col = col.strip()
                if col in column_tables:
                    for other_table in column_tables[col]:
                        if other_table != table:
                            related.add(other_table)
            
            if related:
                relationships[table] = list(related)
        
        return relationships


# =============================================================================
# Factory Function
# =============================================================================

def create_schema_rag(
    persist_directory: Optional[str] = "schema_rag_db",
    embedder: Optional[SentenceTransformer] = None,
    embedding_cache: Optional[Dict[str, list]] = None,
    embedding_lock: Optional[threading.Lock] = None,
    profile: str = "default",
) -> SchemaRAG:
    """Create and return a SchemaRAG instance."""
    return SchemaRAG(
        persist_directory=persist_directory,
        embedder=embedder,
        embedding_cache=embedding_cache,
        embedding_lock=embedding_lock,
        profile=profile,
    )


# =============================================================================
# Utility Functions
# =============================================================================

def expand_tables_with_relationships(
    tables: List[str],
    relationships: Dict[str, List[str]],
    max_total: int = 8
) -> List[str]:
    """
    Expand table list with related tables (for JOINs).
    
    Args:
        tables: Initial list of relevant tables
        relationships: Table relationship mapping
        max_total: Maximum total tables to include
        
    Returns:
        Expanded list of tables including related ones
    """
    expanded = set(tables)
    
    for table in tables:
        if table in relationships:
            for related in relationships[table]:
                if len(expanded) < max_total:
                    expanded.add(related)
    
    return list(expanded)


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    # Test Thai mapping for a given profile
    import sys
    rag = create_schema_rag(profile=sys.argv[1] if len(sys.argv) > 1 else "sts")
    print(f"Thai mappings ({len(rag.thai_mappings)}):")
    for thai_word, terms in list(rag.thai_mappings.items())[:8]:
        print(f"  {thai_word} → {terms}")
