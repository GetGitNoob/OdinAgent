
from __future__ import annotations



import time



from ddgs import DDGS



from tools.base import BaseTool, ToolResult





class WebSearchTool(BaseTool):

    name = "web_search"

    description = (

        "Durchsucht das Internet nach aktuellen oder externen Informationen. "

        "Liefert bis zu 5 Suchergebnisse mit Titel, URL und Beschreibung."

    )



    parameters = {

        "type": "object",

        "properties": {

            "query": {

                "type": "string",

                "description": "Die konkrete Suchanfrage.",

            }

        },

        "required": ["query"],

        "additionalProperties": False,

    }



    def run(self, query: str) -> ToolResult:

        start = time.perf_counter()

        query = query.strip()



        if not query:

            return ToolResult.fail(

                "Keine Suchanfrage angegeben.",

                duration=time.perf_counter() - start,

            )



        try:

            safe_limit = 5

            web_results = []



            with DDGS() as client:

                for i, hit in enumerate(

                    client.text(query, max_results=safe_limit)

                ):

                    if i >= safe_limit:

                        break



                    url = str(

                        hit.get("href") or hit.get("url") or ""

                    ).strip()



                    title = str(

                        hit.get("title", "")

                    ).strip()



                    description = str(

                        hit.get("body", "")

                    ).strip()



                    if title and url:

                        web_results.append(

                            {

                                "title": title,

                                "url": url,

                                "description": description,

                                "position": i + 1,

                            }

                        )



            if not web_results:

                return ToolResult.fail(

                    "Die Websuche hat keine Ergebnisse geliefert.",

                    duration=time.perf_counter() - start,

                )



            return ToolResult.ok(

                {

                    "query": query,

                    "results": web_results,

                },

                duration=time.perf_counter() - start,

            )



        except Exception as exc:

            return ToolResult.fail(

                f"DuckDuckGo-Suche fehlgeschlagen: {exc}",

                duration=time.perf_counter() - start,

            )

