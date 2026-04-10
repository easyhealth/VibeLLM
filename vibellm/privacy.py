"""Privacy detection and anonymization for PII data."""

import re
from typing import List, Dict, Any, Tuple, Optional
from .models import PIIMatch, AnonymizationResult


class PIIDetector:
    """Lightweight regex-based PII (Personal Identifiable Information) detector."""

    # Regex patterns for common PII types
    PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE_CHINA": r'(?:\+?86[-.\s]?)?1[3-9]\d{9}\b',
        "PHONE_INTERNATIONAL": r'(?:\+\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b',
        "ID_CARD": r'\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b',
        "IPV4": r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
        "CREDIT_CARD": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
    }

    def __init__(self):
        self._compiled_patterns = {
            name: re.compile(pattern) for name, pattern in self.PATTERNS.items()
        }

    def detect(self, text: str) -> List[PIIMatch]:
        """Detect all PII entities in the given text."""
        matches = []
        offset = 0

        for entity_type, pattern in self._compiled_patterns.items():
            for match in pattern.finditer(text):
                original_text = match.group()
                start = match.start()
                end = match.end()
                placeholder = f"{{{{{entity_type}_{len(matches)}}}}}"
                matches.append(PIIMatch(
                    entity_type=entity_type,
                    original_text=original_text,
                    placeholder=placeholder,
                    start=start,
                    end=end
                ))

        # Sort by start position to handle replacements correctly
        matches.sort(key=lambda m: m.start)
        return matches


class PrivacyProcessor:
    """Processes requests for privacy: detects PII, anonymizes, and restores responses."""

    def __init__(self):
        self.detector = PIIDetector()

    def extract_message_content(self, messages: List[Dict[str, Any]]) -> str:
        """Extract all text content from messages list."""
        all_text = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                all_text.append(content)
            elif isinstance(content, list):
                # Handle multi-modal content (OpenAI format)
                for block in content:
                    if block.get("type") == "text" and "text" in block:
                        all_text.append(block["text"])
        return "\n".join(all_text)

    def process_request(
        self,
        messages: List[Dict[str, Any]],
        pii_threshold: int = 3,
        allow_anonymization: bool = True,
    ) -> AnonymizationResult:
        """
        Process a request message list for PII.

        Returns:
            AnonymizationResult with decision on routing and anonymized content if needed.
        """
        # Extract all text and detect PII
        all_matches: List[PIIMatch] = []
        full_text = self.extract_message_content(messages)

        if full_text:
            all_matches = self.detector.detect(full_text)

        pii_count = len(all_matches)

        # Decision logic
        if pii_count == 0:
            # No PII, proceed normally
            return AnonymizationResult(
                anonymized_messages=messages,
                pii_mapping={},
                pii_count=0,
                has_complex_pii=False,
                should_route_local=False,
                should_anonymize=False,
            )

        has_complex_pii = pii_count > pii_threshold
        should_route_local = pii_count <= pii_threshold or not allow_anonymization
        should_anonymize = has_complex_pii and allow_anonymization

        if should_anonymize:
            # Create mapping and anonymize
            mapping = {match.placeholder: match for match in all_matches}
            anonymized_messages = self._anonymize_messages(messages, all_matches)
        else:
            # No anonymization needed (will route to local anyway)
            mapping = {match.placeholder: match for match in all_matches}
            anonymized_messages = messages

        return AnonymizationResult(
            anonymized_messages=anonymized_messages,
            pii_mapping=mapping,
            pii_count=pii_count,
            has_complex_pii=has_complex_pii,
            should_route_local=should_route_local,
            should_anonymize=should_anonymize,
        )

    def _anonymize_messages(
        self,
        messages: List[Dict[str, Any]],
        matches: List[PIIMatch],
    ) -> List[Dict[str, Any]]:
        """Anonymize PII in all messages."""
        # Work on a copy to avoid modifying original
        result = []
        for msg in messages:
            msg_copy = msg.copy()
            content = msg_copy.get("content", "")

            if isinstance(content, str):
                msg_copy["content"] = self._anonymize_text(content, matches)
            elif isinstance(content, list):
                # Handle multi-modal content
                new_content = []
                for block in content:
                    block_copy = block.copy()
                    if block.get("type") == "text" and "text" in block_copy:
                        block_copy["text"] = self._anonymize_text(block_copy["text"], matches)
                    new_content.append(block_copy)
                msg_copy["content"] = new_content

            result.append(msg_copy)
        return result

    def _anonymize_text(self, text: str, matches: List[PIIMatch]) -> str:
        """Anonymize PII in a single text string by replacing with placeholders."""
        if not matches:
            return text

        # Replace from end to start to avoid offset issues
        sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)
        chars = list(text)

        for match in sorted_matches:
            # Replace the original text with placeholder
            placeholder = match.placeholder
            # Clear the original range
            for i in range(match.start, match.end):
                chars[i] = ""
            # Insert placeholder at start position
            chars[match.start] = placeholder + "".join(chars[match.start+1:match.end])

        return "".join(chars)

    def restore_response(self, response_text: str, pii_mapping: Dict[str, PIIMatch]) -> str:
        """Restore original PII from placeholders in the response text."""
        if not pii_mapping:
            return response_text

        result = response_text
        for placeholder, match in pii_mapping.items():
            result = result.replace(placeholder, match.original_text)
        return result

    def get_local_provider(self, config) -> Optional[str]:
        """Get the configured local provider name from config."""
        # If explicitly configured, use that
        if config.privacy_local_provider:
            return config.privacy_local_provider

        # Otherwise, find the first provider marked as is_local
        for provider in config.providers:
            if provider.enabled and provider.is_local:
                return provider.name

        return None
