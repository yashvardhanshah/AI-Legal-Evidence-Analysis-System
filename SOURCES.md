# Public legal source register

Research date: 2026-10-19. No source is assumed reusable merely because it is public. These are research copies, not court-certified evidence.

| Source | Access/format and rights | Status |
| --- | --- | --- |
| [Supreme Court, AWS registry](https://registry.opendata.aws/indian-supreme-court-judgments/) | Anonymous S3 HTTPS listings, individual English PDFs and JSON; registry and [maintainer](https://github.com/vanga/indian-supreme-court-judgments/blob/main/README.md) declare CC BY 4.0. Upstream: Supreme Court [eSCR](https://scr.sci.gov.in/); mirror managed by Dattam Labs/vanga. | Bounded 50-document acquisition explicitly approved; actual import/index results in TESTING.md. |
| [High Courts, AWS registry](https://registry.opendata.aws/indian-high-court-judgments/) | Registry declares CC BY 4.0; [maintainer docs](https://github.com/vanga/indian-high-court-judgments/blob/main/opendata/docs/dataset.md) describe PDF/JSON/Parquet/TAR, eCourts web/mobile provenance and deduplication caveats. | Anonymous partition listing and PDF HEAD succeeded (28,227 bytes, application/pdf); no document body acquired. Corpus-specific identity review remains necessary. |
| [India Code](https://www.indiacode.nic.in/) | Landing page announces migration to indiacode.gov.in, which the research tool could not access. An [official BNS PDF](https://www.indiacode.nic.in/indiacode/bitstream/123456789/20062/1/a202345.pdf) was readable and labels its consolidation as of 2025-10-06. Applicable reproduction terms were not verified. | Statute acquisition remains gated; no CC license inferred, no text imported without further rights review. |

## Approved Supreme Court batch

Deterministic selection: first 50 lexicographically ordered English PDF keys in `data/pdf/year=1951/english/`, joined to matching JSON in `metadata/json/year=1951/`. Some object IDs begin with 1952: publisher partition year is not an inferred judgment date. Actual dates are parsed from source metadata only. The user explicitly approved the batch, model and CPU dependencies before downloading.

50 PDFs: **44,616,296 bytes**. 50 JSON records: **276,773 bytes**. Total: **44,893,069 bytes**. Initial manifest SHA-256: `58fd46d2e7a7188cd0b0eedc8bf29fab5e1f6d9f281b1282ee4a7b7a9dbbdbd0`.

Canonical host: `https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/`. Actual example: [1951_1_1125_1147_EN.pdf](https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/data/pdf/year=1951/english/1951_1_1125_1147_EN.pdf). The corresponding JSON is `metadata/json/year=1951/1951_1_1125_1147.json` on the same host.

The ignored plan records exact URLs, byte counts, ETags and selection time. Conditional HTTPS pins ETags; SHA-256 verifies preserved bytes. ETags select source versions and do not replace content hashes. Receipts retain retrieval times and hashes. SQL provenance retains original IDs, metadata hash, available citations, court, dates, source scrape time, license, attribution, transformation version and normalized page hashes. Missing metadata stays null.

Attribution: Indian Supreme Court Judgments, Dattam Labs/vanga, accessed 2026-10-19 through AWS Open Data; [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); original publisher Supreme Court of India. Normalization, page chunking and embeddings are derived transformations. Source/OCR text can contain errors and must be checked against the original.

No restrictions were bypassed. No High Court archive, entire dataset, paid query, NIST or COCO download was performed. Future acquisitions require separate provenance, rights, size and integrity review, with renewed approval for substantial downloads.
