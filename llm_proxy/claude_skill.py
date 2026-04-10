"""Claude Code skill integration for LLM Proxy management."""

import subprocess
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SkillResult:
    """Result of a skill command execution."""
    success: bool
    output: str
    error: Optional[str] = None


class LLMProxySkill:
    """Claude Code skill for managing LLM Proxy providers."""

    def __init__(self, binary_path: str = "llm-proxy"):
        self.binary_path = binary_path

    def _run_command(self, args: List[str]) -> SkillResult:
        """Run a llm-proxy command."""
        try:
            result = subprocess.run(
                [self.binary_path] + args,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return SkillResult(
                    success=True,
                    output=result.stdout,
                )
            else:
                return SkillResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr,
                )

        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=str(e),
            )

    def list_providers(self) -> SkillResult:
        """List all configured providers."""
        return self._run_command(["list"])

    def status(self) -> SkillResult:
        """Get current server status."""
        return self._run_command(["status"])

    def add_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        enabled: bool = True,
        priority: int = 1,
    ) -> SkillResult:
        """Add a new provider."""
        args = [
            "add",
            "--name", name,
            "--base-url", base_url,
            "--api-key", api_key,
            "--default-model", default_model,
            "--priority", str(priority),
        ]
        if not enabled:
            args.append("--disabled")
        return self._run_command(args)

    def remove_provider(self, name: str) -> SkillResult:
        """Remove a provider."""
        return self._run_command(["remove", "--name", name])

    def enable_provider(self, name: str) -> SkillResult:
        """Enable a provider."""
        return self._run_command(["enable", "--name", name])

    def disable_provider(self, name: str) -> SkillResult:
        """Disable a provider."""
        return self._run_command(["disable", "--name", name])

    def set_default(self, name: str) -> SkillResult:
        """Set default provider."""
        return self._run_command(["default", "--name", name])

    def test_provider(self, name: str) -> SkillResult:
        """Test a provider."""
        return self._run_command(["test", "--name", name])

    def benchmark(self, auto_set: bool = False) -> SkillResult:
        """Run latency benchmark."""
        args = ["benchmark"]
        if auto_set:
            args.append("--auto-set")
        return self._run_command(args)

    def parse_natural_language(self, query: str) -> Tuple[str, SkillResult]:
        """Parse natural language query and execute appropriate command."""
        query_lower = query.lower()

        # Common intents
        if any(word in query_lower for word in ["list", "show", "all"]):
            return "list_providers", self.list_providers()

        elif any(word in query_lower for word in ["status", "server running"]):
            return "status", self.status()

        elif "benchmark" in query_lower or "latency" in query_lower or "speed" in query_lower or "fastest" in query_lower:
            auto_set = "set" in query_lower or "switch" in query_lower or "select" in query_lower
            return "benchmark", self.benchmark(auto_set=auto_set)

        elif ("switch" in query_lower or "change" in query_lower or "set" in query_lower) and "default" in query_lower:
            # Extract provider name
            words = query_lower.split()
            # Try to find the provider name after keywords
            for keyword in ["to", "switch to", "change to", "set to"]:
                if keyword in query_lower:
                    name = query_lower.split(keyword)[-1].strip().split()[0]
                    # Capitalization might not match, let user fix if needed
                    return "set_default", self.set_default(name)

        elif ("add" in query_lower or "new" in query_lower) and "provider" in query_lower:
            # This needs more parameters, ask user
            return "add_provider", SkillResult(
                success=False,
                output="",
                error="To add a provider, I need: name, base_url, api_key, and default_model. Please provide these details."
            )

        elif ("remove" in query_lower or "delete" in query_lower) and "provider" in query_lower:
            words = query_lower.split()
            for keyword in ["remove", "delete"]:
                if keyword in query_lower:
                    idx = words.index(keyword)
                    if idx + 1 < len(words):
                        name = words[idx + 1]
                        return "remove_provider", self.remove_provider(name)

        elif "enable" in query_lower:
            words = query_lower.split()
            idx = words.index("enable")
            if idx + 1 < len(words):
                name = words[idx + 1]
                return "enable_provider", self.enable_provider(name)

        elif "disable" in query_lower:
            words = query_lower.split()
            idx = words.index("disable")
            if idx + 1 < len(words):
                name = words[idx + 1]
                return "disable_provider", self.disable_provider(name)

        elif "test" in query_lower:
            words = query_lower.split()
            for keyword in ["test", "test provider"]:
                if keyword in query_lower:
                    parts = query_lower.split(keyword)
                    if len(parts) > 1:
                        name = parts[1].strip().split()[0]
                        return "test_provider", self.test_provider(name)

        # Default: help
        return "help", SkillResult(
            success=False,
            output="""Available commands through natural language:
- list providers - show all configured providers
- status - check if server is running
- benchmark fastest - run latency test and show results
- benchmark and set fastest - run test and set fastest as default
- switch default to NAME - set NAME as default provider
- enable NAME - enable provider NAME
- disable NAME - disable provider NAME
- test NAME - test connectivity to provider NAME
- add provider - add a new provider
- remove NAME - remove provider NAME
""",
        )


# Entry point for Claude Code skill
def handle_query(query: str) -> str:
    """Handle a natural language query from Claude Code."""
    skill = LLMProxySkill()
    command, result = skill.parse_natural_language(query)

    if result.success:
        return result.output
    else:
        return f"Command '{command}' failed: {result.error}" if result.error else f"Command '{command}'"
