"""LLM Proxy Claude Code Skill entry point.

This skill allows Claude Code to manage the LLM proxy providers,
switch between providers when hitting rate limits, and run latency benchmarks.
"""

from llm_proxy.claude_skill import LLMProxySkill


def run(query: str) -> str:
    """Run the skill with a natural language query."""
    skill = LLMProxySkill()
    command, result = skill.parse_natural_language(query)

    output = []

    if result.success:
        output.append(f"✅ Command: {command}")
        output.append("")
        output.append(result.output)
    else:
        output.append(f"❌ Command failed: {command}")
        if result.error:
            output.append("")
            output.append(f"Error: {result.error}")

    return "\n".join(output)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(run(" ".join(sys.argv[1:])))
