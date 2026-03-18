from core.schema_utils import smart_filter_schema, _llm_guess_tables
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage

# Mock Large Schema (> 5 tables to avoid fallback)
schema = {
    "orders": [{"name": "id", "type": "INT"}],
    "customers": [{"name": "name", "type": "VARCHAR"}],
    "products": [{"name": "price", "type": "DECIMAL"}],
    "staff": [{"name": "name", "type": "VARCHAR"}],
    "locations": [{"name": "city", "type": "VARCHAR"}],
    "payments": [{"name": "amount", "type": "DECIMAL"}],
}

# 1. Test Keyword Match (Tier 2) - Should work without LLM
print("\n--- Test 1: Keyword Match ---")
# Query mentions 'orders' explicitly
res1 = smart_filter_schema(schema, "Show me orders", llm=None)
print(f"Result: {list(res1.keys())}")
assert "orders" in res1, "Should find 'orders' by keyword"
assert "staff" not in res1, "Should NOT find 'staff'"

# 2. Test LLM Guess (Tier 3) - Should trigger when keyword fails
print("\n--- Test 2: LLM Guess ---")
mock_llm = MagicMock()
# Mock invoke to return an AIMessage (simulating ChatModel output)
mock_llm.invoke.return_value = AIMessage(content="customers, products")

# We mock the chain behavior in _llm_guess_tables
# Since we can't easily mock the pipe operator '|' inside the function without dependency injection or patching,
# we will verify the behavior by patching `chain.invoke` if possible, 
# BUT `_llm_guess_tables` constructs the chain internally.
# WORKAROUND: We will mock the `llm` to behave like a Runnable that returns the AIMessage.
# The `StrOutputParser` will handle AIMessage correctly.

# To make the mock work with the pipe `|` operator in LangChain, it's tricky.
# Instead, let's just trust that if `smart_filter_schema` calls `_llm_guess_tables`, it works.
# Let's test `_llm_guess_tables` with a Real-ish mock that supports pipe?
# Actually, let's just use `unittest.mock.patch` to patch the chain execution or just test logic if possible.
# For simplicity, let's assume `mock_llm` works if we don't strict check type.

# In `_llm_guess_tables`: chain = prompt | llm | StrOutputParser()
# If we pass a mock_llm that allows `or`, it might work.
# But `PromptTemplate | Mock` might fail.

# Plan B: Test `smart_filter_schema` triggering.
# If we pass a Mock LLM, it should try to use it.
# We will catch the error if pipe fails, but at least verify it TRIED to call guessing.

try:
    # Use a dummy class that supports `|` roughly or just let it fail but check logs
    class MockLLM:
        def invoke(self, input):
            return AIMessage(content="customers, products")
        def __or__(self, other):
            return self # Hacky
        def __ror__(self, other):
            return self # Hacky

    # This is getting too complex to mock internal chain construction.
    # Let's focus on logic: `smart_filter_schema` calls `_llm_guess_tables` if empty.
    
    # We will patch `core.schema_utils._llm_guess_tables` to simply return what we want.
    # This verifies the orchestration logic in `smart_filter_schema`.
    
    from unittest.mock import patch
    
    with patch('core.schema_utils._llm_guess_tables') as mock_guess:
        mock_guess.return_value = {"customers", "products"}
        
        # Query mentioning nothing relevant
        res2 = smart_filter_schema(schema, "Who bought expensive items?", llm=True) # llm=True just to trigger check
        
        print(f"Result with Mock Guess: {list(res2.keys())}")
        assert "customers" in res2
        assert "products" in res2
        assert mock_guess.called, "Should call _llm_guess_tables"

except Exception as e:
    print(f"Test failed: {e}")
    raise e

print("\n✅ Verification Successful!")
