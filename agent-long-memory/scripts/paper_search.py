#!/usr/bin/env python3
"""
Daily paper search for vector database and cardinality estimation topics.
Searches OpenAlex and arXiv, deduplicates, saves results to ~/papers/.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
OUTPUT_DIR = Path.home() / "papers"
DAYS_BACK = 7

# Search topics with multiple query variants
TOPICS = {
    "vector_database": [
        "vector database",
        "vector similarity search",
        "approximate nearest neighbor",
        "HNSW index",
        "learned index structure",
        "similarity search high-dimensional",
    ],
    "cardinality_estimation": [
        "cardinality estimation",
        "selectivity estimation",
        "learned cardinality estimation",
        "query optimization cardinality",
        "histogram cardinality database",
        "cardinality estimation machine learning",
    ],
}

OPENALEX_BASE = "https://api.openalex.org/works"
ARXIV_BASE = "https://export.arxiv.org/api/query"


def get_date_cutoff(days_back):
    """Return ISO date string for N days ago."""
    return (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")


def search_openalex(query, cutoff_date, per_page=50):
    """Search OpenAlex API for papers after cutoff_date."""
    params = {
        "filter": f"default.search:{query},publication_year:2024-2026",
        "sort": "publication_year:desc,cited_by_count:desc",
        "per_page": str(per_page),
        "mailto": "corrie@hermes-agent.local",
    }
    url = f"{OPENALEX_BASE}?{urllib.parse.urlencode(params)}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HermesAgent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        
        papers = []
        for work in data.get("results", []):
            pub_date = work.get("publication_date", "")
            if pub_date and pub_date < cutoff_date:
                continue
            
            doi = work.get("doi", "")
            title = work.get("title", "").strip()
            if not title:
                continue
            
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])[:5]
            ]
            venue = ""
            locations = work.get("locations", [])
            if locations:
                source = locations[0].get("source", {})
                if source:
                    venue = source.get("display_name", "")
            
            papers.append({
                "title": title,
                "authors": [a for a in authors if a],
                "year": work.get("publication_year"),
                "date": pub_date,
                "venue": venue,
                "citations": work.get("cited_by_count", 0),
                "doi": doi.replace("https://doi.org/", "") if doi else "",
                "url": work.get("id", ""),
                "source": "OpenAlex",
            })
        return papers
    except Exception as e:
        print(f"  [OpenAlex] Error searching '{query}': {e}", file=sys.stderr)
        return []


def search_arxiv(query, max_results=30):
    """Search arXiv API for recent papers."""
    params = {
        "search_query": f"all:{query}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }
    url = f"{ARXIV_BASE}?{urllib.parse.urlencode(params)}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HermesAgent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_data = resp.read().decode()
        
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_data)
        
        papers = []
        for entry in root.findall("a:entry", ns):
            title = entry.find("a:title", ns).text.strip().replace("\n", " ")
            published = entry.find("a:published", ns).text[:10]
            arxiv_id = entry.find("a:id", ns).text.strip().split("/abs/")[-1]
            
            authors = [
                a.find("a:name", ns).text
                for a in entry.findall("a:author", ns)[:5]
            ]
            categories = [
                c.get("term") for c in entry.findall("a:category", ns)
            ]
            
            papers.append({
                "title": title,
                "authors": authors,
                "year": int(published[:4]),
                "date": published,
                "venue": f"arXiv ({', '.join(categories[:3])})",
                "citations": 0,
                "doi": "",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "source": "arXiv",
            })
        return papers
    except Exception as e:
        print(f"  [arXiv] Error searching '{query}': {e}", file=sys.stderr)
        return []


def deduplicate(papers):
    """Remove duplicates based on title similarity."""
    seen_titles = set()
    unique = []
    for p in papers:
        # Normalize title for comparison
        norm = p["title"].lower().strip()
        # Remove common prefixes/suffixes
        for prefix in ["a ", "an ", "the "]:
            if norm.startswith(prefix):
                norm = norm[len(prefix):]
        
        if norm not in seen_titles:
            seen_titles.add(norm)
            unique.append(p)
    return unique


def format_paper(paper, idx):
    """Format a single paper for display."""
    authors_str = ", ".join(paper["authors"][:3])
    if len(paper["authors"]) > 3:
        authors_str += " et al."
    
    lines = [
        f"  {idx}. {paper['title']}",
        f"     Authors: {authors_str}",
        f"     Year: {paper['year']} | Venue: {paper['venue']} | Citations: {paper['citations']}",
    ]
    if paper["doi"]:
        lines.append(f"     DOI: {paper['doi']}")
    lines.append(f"     URL: {paper['url']}")
    return "\n".join(lines)


def main():
    cutoff = get_date_cutoff(DAYS_BACK)
    print(f"Searching for papers published after {cutoff}...")
    print(f"Topics: {', '.join(TOPICS.keys())}")
    print()
    
    all_results = {}
    
    for topic_name, queries in TOPICS.items():
        print(f"=== {topic_name.upper().replace('_', ' ')} ===")
        topic_papers = []
        
        for query in queries:
            print(f"  Searching OpenAlex: '{query}'...")
            papers = search_openalex(query, cutoff)
            topic_papers.extend(papers)
            print(f"    Found {len(papers)} papers")
            time.sleep(0.5)  # Rate limit
            
            print(f"  Searching arXiv: '{query}'...")
            papers = search_arxiv(query)
            # Filter by date
            papers = [p for p in papers if p["date"] >= cutoff]
            topic_papers.extend(papers)
            print(f"    Found {len(papers)} papers")
            time.sleep(3)  # arXiv rate limit
        
        # Deduplicate
        topic_papers = deduplicate(topic_papers)
        # Sort by citations (desc) then date (desc)
        topic_papers.sort(key=lambda p: (-p["citations"], p["date"]), reverse=False)
        
        all_results[topic_name] = topic_papers
        print(f"  Total unique papers for {topic_name}: {len(topic_papers)}")
        print()
    
    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"papers_{today}.md"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# Paper Search Results - {today}\n\n")
        f.write(f"Search period: {cutoff} to {today} (last {DAYS_BACK} days)\n\n")
        
        total = 0
        for topic_name, papers in all_results.items():
            display_name = topic_name.replace("_", " ").title()
            f.write(f"## {display_name}\n\n")
            f.write(f"Found: {len(papers)} papers\n\n")
            
            if papers:
                for i, paper in enumerate(papers, 1):
                    f.write(format_paper(paper, i) + "\n\n")
            else:
                f.write("  No new papers found in this period.\n\n")
            
            total += len(papers)
        
        f.write(f"---\nTotal: {total} papers across all topics\n")
    
    print(f"Results saved to: {output_file}")
    
    # Also save as JSON for programmatic access
    json_file = OUTPUT_DIR / f"papers_{today}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"JSON saved to: {json_file}")
    
    # Print summary
    print("\n=== SUMMARY ===")
    for topic_name, papers in all_results.items():
        display_name = topic_name.replace("_", " ").title()
        print(f"  {display_name}: {len(papers)} papers")
    
    return all_results


if __name__ == "__main__":
    main()
