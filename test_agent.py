# ABOUTME: Test script for McMaster agent.
# ABOUTME: Tests end-to-end search and product recommendation.

from agent import McMasterAgent

def test_agent():
    """Test agent search and recommendation."""
    print("Testing McMaster agent...")
    print("=" * 60)

    agent = McMasterAgent(headless=True, verbose=True)

    # Test with a real query for the radiatron project
    query = "motorized ball valve 3/4 inch brass"

    print(f"\nQuery: {query}\n")
    print("=" * 60)

    candidates = agent.search(query, max_candidates=3)

    print("\n" + "=" * 60)
    print(agent.format_results(candidates))

if __name__ == "__main__":
    test_agent()
