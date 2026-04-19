"""
FactCheckerAgent - Verifies factual claims during discussions.

The fact-checker:
- Detects controversial/factual claims in messages using LLM
- Researches claims via Tavily web search
- Compiles results with journalistic care
- Publishes compressed fact-check results to discussion
"""

import asyncio
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.llm.client import LLMClient
from app.llm.prompts import FACT_CHECK_PROMPT
from app.models.agent import AgentType
from app.models.message import Message, MessageType
from app.orchestration.event_bus import FactCheckEvent

if TYPE_CHECKING:
    from app.orchestration.session import DiscussionSession


class FactCheckSource(BaseModel):
    """Source information for a fact-check result."""

    url: str = Field(description="URL of the source")
    title: str = Field(description="Title of the source")
    credibility: str = Field(description="Credibility rating (high, medium, low)")


class FactCheckResult(BaseModel):
    """Result of a fact-check operation."""

    claim: str = Field(description="The claim that was checked")
    verdict: str = Field(description="Verdict: verified, unverified, disputed")
    sources: List[FactCheckSource] = Field(
        default_factory=list, description="Sources supporting the verdict"
    )
    explanation: Optional[str] = Field(
        default=None, description="Explanation of the verdict"
    )


class FactCheckerAgent(BaseAgent):
    """
    Agent that verifies factual claims during discussions.

    The fact-checker:
    - Detects claims in messages using LLM
    - Checks claims via web search (mock for tests, crawl4ai for production)
    - Validates sources using LLM
    - Publishes FactCheckEvent to event bus

    The fact-checker does NOT:
    - Block discussion (async execution)
    - Use LLM extraction for search (uses JsonCssExtractionStrategy)
    - Cache results (CacheMode.BYPASS)
    - Timeout > 10s per search
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional["DiscussionSession"] = None,
    ) -> None:
        """
        Initialize the fact-checker agent.

        Args:
            llm_client: LLM client instance for claim detection and source validation
            session: Optional discussion session for event bus access
        """
        super().__init__(
            id="fact_checker_001",
            name="Fact Checker",
            type=AgentType.FACT_CHECKER,
            llm_client=llm_client,
            session=session,
        )
        self._search_timeout: int = 10

    async def generate_response(self, context: list[dict]) -> "Message":
        """
        Generate a response based on the conversation context.

        Fact-checker doesn't generate discussion responses - it only
        produces fact-check results.

        Args:
            context: List of message dictionaries with 'role' and 'content'

        Returns:
            Message containing fact-check information (not used in normal flow)
        """
        return self._create_message(
            "Fact-checker ready to verify claims.", MessageType.FACT_CHECK
        )

    async def detect_claims(
        self, message: str, conversation_context: str = ""
    ) -> List[str]:
        detection_prompt = f"""You are a fact-checker. Identify the SINGLE most important factual claim in this message.

Check claims that make specific assertions about reality:
- Statistics or numbers ("80% of...", "5 million...")
- Trends or developments ("X is rising", "Y is declining")
- Cause and effect ("X causes Y", "X leads to Y")
- Scientific or medical claims ("X is healthy", "Y causes disease")
- Claims about groups ("Group X does Y", "Group X is responsible for Z")
- Claims about studies or organizations

Skip ONLY:
- Pure opinions clearly marked as such ("I personally feel...")
- Questions
- Obvious common knowledge

Return ONLY a JSON array with AT MOST ONE claim. Return [] only if truly nothing factual.
Do not include any other text.

Message: {message}
"""
        messages = [{"role": "user", "content": detection_prompt}]

        full_response = await self._stream_llm(messages)

        try:
            if "```json" in full_response:
                full_response = (
                    full_response.split("```json")[1].split("```")[0].strip()
                )
            elif "```" in full_response:
                full_response = full_response.split("```")[1].split("```")[0].strip()

            claims = json.loads(full_response)
            if isinstance(claims, list) and len(claims) > 0:
                claim = claims[0]
                if isinstance(claim, list):
                    claim = claim[0] if claim else None
                elif isinstance(claim, dict):
                    claim = claim.get("claim", claim.get("text", str(claim)))
                text = str(claim).strip()
                if text and len(text) > 15:
                    return [text]
        except (json.JSONDecodeError, IndexError):
            pass

        return []

    async def check_claim(self, claim: str) -> FactCheckResult:
        """
        Check a claim asynchronously using web search and LLM validation.

        Uses crawl4ai for web search (mocked in tests) with 10s timeout.
        LLM validates sources for credibility and relevance.

        Args:
            claim: The claim to verify

        Returns:
            FactCheckResult with verdict and sources
        """
        try:
            search_results = await self._web_search(claim)

            if not search_results:
                return FactCheckResult(
                    claim=claim,
                    verdict="unverified",
                    sources=[],
                    explanation="No sources found for this claim.",
                )

            validated_result = await self._validate_sources(claim, search_results)

            return validated_result

        except asyncio.TimeoutError:
            return FactCheckResult(
                claim=claim,
                verdict="unverified",
                sources=[],
                explanation="Search timed out after 10 seconds.",
            )
        except Exception as e:
            return FactCheckResult(
                claim=claim,
                verdict="unverified",
                sources=[],
                explanation=f"Error during fact-check: {str(e)}",
            )

    async def _web_search(self, claim: str) -> List[Dict[str, Any]]:
        trusted_sites = "site:de.wikipedia.org OR site:bpb.de OR site:rki.de OR site:tagesschau.de OR site:zeit.de OR site:spiegel.de OR site:sueddeutsche.de OR site:faz.net OR site:aerzteblatt.de OR site:dkfz.de"
        search_query = f"{claim} {trusted_sites}"

        try:
            from crawl4ai import AsyncWebCrawler
            from crawl4ai.cache_context import CacheMode

            async with AsyncWebCrawler() as crawler:
                search_results = await asyncio.wait_for(
                    crawler.arun(
                        url=f"https://www.google.com/search?q={search_query.replace(' ', '+')}",
                        cache_mode=CacheMode.BYPASS,
                    ),
                    timeout=15,
                )

                if search_results and getattr(search_results, "markdown", ""):
                    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

                    schema = {
                        "name": "search_results",
                        "baseSelector": "div.g",
                        "fields": [
                            {"name": "title", "selector": "h3", "type": "text"},
                            {
                                "name": "url",
                                "selector": "a",
                                "type": "attribute",
                                "attribute": "href",
                            },
                            {
                                "name": "snippet",
                                "selector": "div.VwiC3b",
                                "type": "text",
                            },
                        ],
                    }

                    extraction = JsonCssExtractionStrategy(schema)
                    extracted = extraction.run([search_results], None)

                    if extracted:
                        return [
                            {
                                "url": r.get("url", ""),
                                "title": r.get("title", ""),
                                "snippet": r.get("snippet", "")[:500],
                            }
                            for r in extracted
                            if r.get("url") and r.get("title")
                        ][:5]

                    return [
                        {
                            "url": search_results.url or "",
                            "title": "Google Search",
                            "snippet": (search_results.markdown or "")[:500],
                        }
                    ]
        except ImportError:
            pass
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

        try:
            from ddgs import DDGS

            def _search():
                with DDGS() as ddgs:
                    return list(ddgs.text(claim, max_results=5))

            results = await asyncio.to_thread(_search)

            return [
                {
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]
        except Exception:
            return []

    async def _validate_sources(
        self, claim: str, search_results: List[Dict[str, Any]]
    ) -> FactCheckResult:
        sources_text = "\n".join(
            f"- {result.get('title', 'Unknown')}: {result.get('snippet', 'No snippet')[:300]} (URL: {result.get('url', '')})"
            for result in search_results[:5]
        )

        validation_prompt = f"""You are a professional fact-checker.

CLAIM: {claim}

SEARCH RESULTS:
{sources_text}

EVALUATION RULES:
- ONLY trust sources from: academic institutions, peer-reviewed studies, government reports, official statistics, reputable news organizations, Wikipedia for basic facts
- DO NOT trust: blogs, opinion pieces, forums, social media, unknown websites

Return ONLY a JSON object with:
- verdict: ONE of these: "verified" (confirmed by trustworthy sources), "refuted" (sources prove the opposite), "disputed" (sources disagree), "mixed" (very contradictory results), or "unverified" (no trustworthy sources found)
- explanation: ONE short sentence in German explaining your verdict
- trusted_sources: array of 3-5 trustworthy source titles

Return ONLY the JSON object, no other text.
"""
        messages = [{"role": "user", "content": validation_prompt}]

        full_response = await self._stream_llm(messages)

        try:
            if "```json" in full_response:
                full_response = (
                    full_response.split("```json")[1].split("```")[0].strip()
                )
            elif "```" in full_response:
                full_response = full_response.split("```")[1].split("```")[0].strip()

            result_data = json.loads(full_response)

            verdict = result_data.get("verdict", "unverified")
            explanation = result_data.get("explanation", "Could not validate sources.")
            trusted_titles = result_data.get("trusted_sources", [])

            sources = []
            for r in search_results[:5]:
                title = r.get("title", "")
                url = r.get("url", "")

                if any(tt.lower() in title.lower() for tt in trusted_titles):
                    credibility = "high"
                elif any(
                    domain in url.lower()
                    for domain in [
                        "wikipedia",
                        ".edu",
                        ".gov",
                        "tagesschau",
                        "dw.com",
                        "reuters",
                        "apnews",
                    ]
                ):
                    credibility = "high"
                elif any(
                    domain in url.lower()
                    for domain in [
                        "zeit.de",
                        "spiegel.de",
                        "sueddeutsche",
                        "faz.net",
                        "bbc",
                        "ARD",
                    ]
                ):
                    credibility = "medium"
                else:
                    credibility = "low"

                if credibility in ("high", "medium"):
                    sources.append(
                        FactCheckSource(
                            url=url,
                            title=title,
                            credibility=credibility,
                        )
                    )

            if not sources:
                sources = [
                    FactCheckSource(
                        url=r.get("url", ""),
                        title=r.get("title", "Unknown"),
                        credibility="medium",
                    )
                    for r in search_results[:3]
                ]

            return FactCheckResult(
                claim=claim,
                verdict=verdict,
                sources=sources[:5],
                explanation=explanation,
            )
        except (json.JSONDecodeError, KeyError):
            return FactCheckResult(
                claim=claim,
                verdict="unverified",
                sources=[
                    FactCheckSource(
                        url=r.get("url", ""),
                        title=r.get("title", "Unknown"),
                        credibility="medium",
                    )
                    for r in search_results[:3]
                ],
                explanation="Quellen konnten nicht validiert werden.",
            )

    async def run_fact_check(self, message: str) -> List[FactCheckEvent]:
        """
        Main entry point - detect claims, check each, publish results.

        Runs asynchronously, doesn't block discussion.
        Results published to event bus via session.

        Args:
            message: The message to fact-check

        Returns:
            List of FactCheckEvent objects published to event bus
        """
        claims = await self.detect_claims(message)

        if not claims:
            return []

        events: List[FactCheckEvent] = []

        for claim in claims:
            result = await self.check_claim(claim)

            event = self._result_to_event(result)
            events.append(event)

            if self.session:
                self.session.event_bus.publish(event)

        return events

    def _result_to_event(self, result: FactCheckResult) -> FactCheckEvent:
        """
        Convert FactCheckResult to FactCheckEvent for event bus.

        Args:
            result: The FactCheckResult to convert

        Returns:
            FactCheckEvent for publishing to event bus
        """
        result_bool = result.verdict == "verified"
        primary_source = result.sources[0].url if result.sources else None
        confidence = self._calculate_confidence(result)

        return FactCheckEvent(
            claim=result.claim,
            source=primary_source,
            result=result_bool,
            confidence=confidence,
            metadata={
                "verdict": result.verdict,
                "sources": [s.model_dump() for s in result.sources],
                "explanation": result.explanation,
                "agent_id": self.id,
            },
        )

    def _calculate_confidence(self, result: FactCheckResult) -> float:
        """
        Calculate confidence score based on verdict and sources.

        Args:
            result: The FactCheckResult to calculate confidence for

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if result.verdict == "unverified":
            return 0.0

        if not result.sources:
            return 0.0

        high_credibility_count = sum(
            1 for s in result.sources if s.credibility == "high"
        )
        medium_credibility_count = sum(
            1 for s in result.sources if s.credibility == "medium"
        )

        total_sources = len(result.sources)

        if result.verdict == "verified":
            base_confidence = 0.7
            credibility_boost = (high_credibility_count * 0.1) + (
                medium_credibility_count * 0.05
            )
            return min(0.95, base_confidence + credibility_boost)

        if result.verdict == "disputed":
            return 0.3 + (high_credibility_count * 0.05)

        return 0.0
