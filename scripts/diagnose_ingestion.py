#!/usr/bin/env python3
"""
Check which PDFs exist vs which are indexed in ChromaDB.
"""

import sys
from pathlib import Path
from collections import Counter

# Add packages to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages"))

import chromadb
from chromadb.config import Settings

def main():
    # Connect to ChromaDB
    persist_dir = project_root / "data" / "embeddings"
    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False)
    )
    
    collection = client.get_collection(name="tribunal_cases")
    total_count = collection.count()
    
    print(f"📊 Total chunks in ChromaDB: {total_count:,}\n")
    
    # Get ALL case references from ChromaDB (sample larger)
    print("🔍 Fetching case references from index...")
    batch_size = 5000
    all_case_refs = set()
    all_years = []
    
    offset = 0
    while offset < total_count:
        results = collection.get(
            limit=min(batch_size, total_count - offset),
            offset=offset,
            include=["metadatas"]
        )
        
        for metadata in results.get("metadatas", []):
            if metadata.get("case_reference"):
                all_case_refs.add(metadata["case_reference"])
            if metadata.get("year"):
                all_years.append(metadata["year"])
        
        offset += batch_size
        print(f"   Processed {min(offset, total_count):,} / {total_count:,} chunks...")
    
    print(f"\n✅ Found {len(all_case_refs):,} unique cases indexed")
    
    # Analyze year distribution
    year_counts = Counter(all_years)
    print(f"\n📅 FULL Year Distribution:")
    for year in sorted(year_counts.keys()):
        count = year_counts[year]
        percentage = (count / len(all_years)) * 100 if all_years else 0
        bar = "█" * int(percentage / 2)
        print(f"   {year}: {count:6d} chunks ({percentage:5.1f}%) {bar}")
    
    # Now check what PDFs exist on disk
    print(f"\n\n🗂️  Scanning filesystem for PDFs...")
    bailii_dir = project_root / "data" / "raw" / "bailii"
    
    all_pdfs = list(bailii_dir.rglob("*.pdf"))
    print(f"   Found {len(all_pdfs):,} PDF files on disk")
    
    # Extract case references from PDF paths
    pdf_case_refs = set()
    pdf_by_year_dir = Counter()
    
    for pdf_path in all_pdfs:
        # Case reference is the parent directory name
        case_ref = pdf_path.parent.name
        pdf_case_refs.add(case_ref)
        
        # Find year directory in path
        for part in pdf_path.parts:
            if part.isdigit() and 2000 <= int(part) <= 2030:
                pdf_by_year_dir[int(part)] += 1
                break
    
    print(f"   Unique cases on disk: {len(pdf_case_refs):,}")
    
    print(f"\n📁 PDFs by Directory Year:")
    for year in sorted(pdf_by_year_dir.keys()):
        print(f"   {year}: {pdf_by_year_dir[year]:4d} PDFs")
    
    # Compare
    indexed_not_on_disk = all_case_refs - pdf_case_refs
    on_disk_not_indexed = pdf_case_refs - all_case_refs
    
    print(f"\n🔍 Comparison:")
    print(f"   Cases indexed: {len(all_case_refs):,}")
    print(f"   Cases on disk: {len(pdf_case_refs):,}")
    print(f"   Indexed but not on disk: {len(indexed_not_on_disk)}")
    print(f"   On disk but not indexed: {len(on_disk_not_indexed):,}")
    
    if len(on_disk_not_indexed) > 0:
        print(f"\n⚠️  You have {len(on_disk_not_indexed):,} PDFs that haven't been ingested yet!")
        print(f"   Run: python scripts/rag.py ingest --pdf-dir data/raw/bailii")

if __name__ == "__main__":
    main()

