from __future__ import annotations

import time
import requests

from tools.base import BaseTool, ToolResult


class WebResearchTool(BaseTool):
    name = "web_research"
    description = ("Recherchiert aktuelle Informationen im Internet. " "Verwende dieses Tool, wenn aktuelle oder externe Informationen benötigt werden. Liefert Titel, URL und kurze Auszüge.")
    parameters = {"type": "object", "properties": {"query": {"type": "string", "description": "Die konkrete Suchanfrage."}}, "required": ["query"], "additionalProperties": False}

    def run(self, query: str) -> ToolResult:
        start = time.perf_counter()
        query = query.strip()
        if not query:
            return ToolResult.fail("Keine Suchanfrage angegeben.", duration=time.perf_counter() - start)
        try:
            response = requests.get("http://127.0.0.1:8080/search", params={"q": query, "format": "json", "language": "de-DE"}, timeout=10)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                return ToolResult.fail("Die Websuche hat keine Ergebnisse geliefert.", duration=time.perf_counter() - start)
            output = []
            for result in results[:5]:
                title = str(result.get("title", "")).strip()
                url = str(result.get("url", "")).strip()
                content = str(result.get("content", "")).strip()
                if title and url:
                    output.append({"title": title, "url": url, "snippet": content[:800]})
            if not output:
                return ToolResult.fail("Die Websuche lieferte keine verwertbaren Ergebnisse.", duration=time.perf_counter() - start)
            return ToolResult.ok({"query": query, "results": output}, duration=time.perf_counter() - start)
        except requests.Timeout:
            return ToolResult.fail("Die Websuche hat das Zeitlimit überschritten.", duration=time.perf_counter() - start)
        except requests.RequestException as exc:
            return ToolResult.fail(f"Websuche nicht erreichbar: {exc}", duration=time.perf_counter() - start)
        except ValueError as exc:
            return ToolResult.fail(f"Ungültige Antwort von SearXNG: {exc}", duration=time.perf_counter() - start)
