"""
Schema Pruning Module - จาก LGESQL Paper

Graph Pruning เป็น auxiliary task ที่ช่วยให้ encoder เรียนรู้ที่จะแยกแยะ
schema items ที่ relevant กับ question จาก irrelevant ones

Based on: LGESQL (Cao et al., 2021) Section 3.3.2
"""
import torch
import torch.nn as nn
from typing import Dict, List, Tuple
import numpy as np


class SchemaPruner(nn.Module):
    """
    Binary classifier ที่ predict ว่า schema item แต่ละตัว
    relevant กับ question หรือไม่

    Architecture จาก LGESQL:
    1. Multi-head attention: question → schema item
    2. Biaffine classifier: (schema_emb, context_emb) → score
    """

    def __init__(self, hidden_dim: int = 256, num_heads: int = 8):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.head_dim = hidden_dim // num_heads

        # Multi-head attention layers
        self.W_sq = nn.Linear(hidden_dim, hidden_dim)  # schema query
        self.W_sk = nn.Linear(hidden_dim, hidden_dim)  # question key
        self.W_sv = nn.Linear(hidden_dim, hidden_dim)  # question value
        self.W_so = nn.Linear(hidden_dim, hidden_dim)  # output projection

        # Biaffine classifier
        self.U_s = nn.Linear(hidden_dim, hidden_dim)
        self.W_s = nn.Linear(hidden_dim * 2, 1)
        self.b_s = nn.Parameter(torch.zeros(1))

    def forward(
        self,
        schema_embeddings: torch.Tensor,  # [num_schema_items, hidden_dim]
        question_embeddings: torch.Tensor,  # [num_question_words, hidden_dim]
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass

        Returns:
            logits: [num_schema_items] - relevance scores
            probs: [num_schema_items] - probabilities (sigmoid)
        """
        # Step 1: Multi-head attention (question → schema)
        context_vectors = self._compute_context(
            schema_embeddings, question_embeddings
        )

        # Step 2: Biaffine classification
        logits = self._biaffine_classifier(schema_embeddings, context_vectors)
        probs = torch.sigmoid(logits)

        return logits, probs

    def _compute_context(
        self,
        schema_emb: torch.Tensor,
        question_emb: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute context vector for each schema item using multi-head attention

        จาก LGESQL Section 3.3.2:
        γ_ji = softmax_j (x_si W^h_sq)(x_qj W^h_sk)^T / √(d/H)
        x̃_si = (⊕^H_{h=1} Σ_j γ^h_ji x_qj W^h_sv) W_so
        """
        batch_size, num_schema = schema_emb.size(0), schema_emb.size(0)
        num_question = question_emb.size(0)

        # Project to query, key, value
        Q = self.W_sq(schema_emb)  # [num_schema, hidden_dim]
        K = self.W_sk(question_emb)  # [num_question, hidden_dim]
        V = self.W_sv(question_emb)  # [num_question, hidden_dim]

        # Reshape for multi-head: [num_heads, num_items, head_dim]
        Q = Q.view(num_schema, self.num_heads, self.head_dim).transpose(0, 1)
        K = K.view(num_question, self.num_heads, self.head_dim).transpose(0, 1)
        V = V.view(num_question, self.num_heads, self.head_dim).transpose(0, 1)

        # Scaled dot-product attention
        scores = torch.matmul(Q, K.transpose(-2, -1))  # [H, num_schema, num_question]
        scores = scores / np.sqrt(self.head_dim)

        attention_weights = torch.softmax(scores, dim=-1)  # [H, num_schema, num_question]

        # Weighted sum
        context = torch.matmul(attention_weights, V)  # [H, num_schema, head_dim]

        # Concatenate heads
        context = context.transpose(0, 1).contiguous()  # [num_schema, H, head_dim]
        context = context.view(num_schema, self.hidden_dim)  # [num_schema, hidden_dim]

        # Output projection
        context = self.W_so(context)  # [num_schema, hidden_dim]

        return context

    def _biaffine_classifier(
        self,
        schema_emb: torch.Tensor,
        context_emb: torch.Tensor
    ) -> torch.Tensor:
        """
        Biaffine binary classifier

        จาก LGESQL Section 3.3.2:
        Biaffine(x1, x2) = x1 U_s x2^T + [x1; x2] W_s + b_s
        P^gp(y_si | x_si, X_q) = σ(Biaffine(x_si, x̃_si))
        """
        # Biaffine term: x1 U_s x2^T
        biaffine_term = torch.sum(
            schema_emb * torch.matmul(context_emb, self.U_s.weight.t()),
            dim=-1
        )  # [num_schema]

        # Linear term: [x1; x2] W_s
        concat_emb = torch.cat([schema_emb, context_emb], dim=-1)  # [num_schema, 2*hidden_dim]
        linear_term = self.W_s(concat_emb).squeeze(-1)  # [num_schema]

        # Final score
        logits = biaffine_term + linear_term + self.b_s

        return logits

    def compute_loss(
        self,
        logits: torch.Tensor,
        labels: torch.Tensor
    ) -> torch.Tensor:
        """
        Binary cross-entropy loss

        จาก LGESQL Section 3.3.2:
        L_gp = -Σ_si [y^g_si log P^gp(y_si|x_si,X_q) + (1-y^g_si) log(1-P^gp(y_si|x_si,X_q))]
        """
        return nn.functional.binary_cross_entropy_with_logits(
            logits, labels.float()
        )


# =============================================================================
# Schema Mapping using Pruning Results
# =============================================================================

class SchemaMapper:
    """
    ใช้ schema pruning results เพื่อ map entities จาก examples → actual schema
    """

    def __init__(self, pruner: SchemaPruner):
        self.pruner = pruner

    def map_example_to_schema(
        self,
        example_sql: str,
        example_schema: Dict[str, List[str]],
        actual_schema: Dict[str, List[str]],
        question: str,
        question_emb: torch.Tensor,
        actual_schema_emb: Dict[str, torch.Tensor]
    ) -> Dict[str, str]:
        """
        Map entities จาก example schema → actual schema

        Strategy:
        1. Extract entities จาก example SQL (tables, columns)
        2. หา relevant schema items ใน actual schema (ใช้ pruner)
        3. Map โดยใช้ semantic similarity + pruning scores

        Returns:
            mappings: {example_entity: actual_entity}
            เช่น {"receipt": "orders", "month": "order_date"}
        """
        # Step 1: Extract entities from example
        example_entities = self._extract_entities_from_sql(example_sql)

        # Step 2: Get pruning scores for actual schema
        with torch.no_grad():
            schema_items = []
            schema_embs = []

            for table_name, columns in actual_schema.items():
                schema_items.append(("table", table_name))
                schema_embs.append(actual_schema_emb[f"table_{table_name}"])

                for col_name in columns:
                    schema_items.append(("column", col_name))
                    schema_embs.append(actual_schema_emb[f"col_{col_name}"])

            schema_emb_tensor = torch.stack(schema_embs)
            _, probs = self.pruner(schema_emb_tensor, question_emb)

        # Step 3: Map entities
        mappings = {}

        for example_entity in example_entities:
            # หา actual schema item ที่:
            # 1. มี type ตรงกัน (table → table, column → column)
            # 2. มี pruning score สูง (relevant กับ question)
            # 3. มี semantic similarity สูง

            best_match = None
            best_score = -1

            for idx, (schema_type, schema_name) in enumerate(schema_items):
                if schema_type != example_entity["type"]:
                    continue

                # Combined score = pruning_score * semantic_similarity
                pruning_score = probs[idx].item()
                semantic_sim = self._semantic_similarity(
                    example_entity["name"], schema_name
                )

                combined_score = pruning_score * semantic_sim

                if combined_score > best_score:
                    best_score = combined_score
                    best_match = schema_name

            if best_match:
                mappings[example_entity["name"]] = best_match

        return mappings

    def _extract_entities_from_sql(self, sql: str) -> List[Dict]:
        """
        Extract table และ column names จาก SQL

        Simple implementation - ในการใช้งานจริงควรใช้ SQL parser
        """
        import sqlglot

        entities = []
        try:
            parsed = sqlglot.parse_one(sql)

            # Extract tables
            for table in parsed.find_all(sqlglot.exp.Table):
                entities.append({
                    "type": "table",
                    "name": table.name
                })

            # Extract columns
            for column in parsed.find_all(sqlglot.exp.Column):
                entities.append({
                    "type": "column",
                    "name": column.name
                })
        except:
            pass

        return entities

    def _semantic_similarity(self, name1: str, name2: str) -> float:
        """
        คำนวณ semantic similarity ระหว่าง 2 names

        Simple implementation - ใช้ edit distance
        ในการใช้งานจริงควรใช้ embedding similarity
        """
        # Levenshtein distance
        import Levenshtein
        return 1.0 - (Levenshtein.distance(name1.lower(), name2.lower()) /
                      max(len(name1), len(name2)))


# =============================================================================
# Training Example
# =============================================================================

def train_schema_pruner_example():
    """
    ตัวอย่างการ train schema pruner
    """
    pruner = SchemaPruner(hidden_dim=256, num_heads=8)
    optimizer = torch.optim.Adam(pruner.parameters(), lr=1e-3)

    # Dummy data
    question_emb = torch.randn(10, 256)  # 10 question words
    schema_emb = torch.randn(20, 256)    # 20 schema items

    # Labels: 1 if schema item used in target SQL, 0 otherwise
    labels = torch.tensor([1, 1, 0, 1, 0, 0, 1, 0, 0, 0,
                          1, 0, 1, 0, 0, 0, 0, 1, 0, 0])

    # Training step
    optimizer.zero_grad()
    logits, probs = pruner(schema_emb, question_emb)
    loss = pruner.compute_loss(logits, labels)
    loss.backward()
    optimizer.step()

    print(f"Loss: {loss.item():.4f}")
    print(f"Predictions: {(probs > 0.5).long()}")
    print(f"Ground truth: {labels}")


if __name__ == "__main__":
    train_schema_pruner_example()
