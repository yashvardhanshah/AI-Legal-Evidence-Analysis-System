# Public legal source register

## Phase 6 source/access review — 2026-10-21

The [India Code landing page](https://www.indiacode.nic.in/) still announces migration. Unlike the research browser, direct HTTPS reached `https://indiacode.gov.in/` (200; JavaScript shell), its public configuration and advertised `https://indiacode.gov.in/server/api` (200). Public discovery metadata is accessible, but broad act-name searches also return section headings and subordinate rules: search hits are not accepted as verified complete Acts. Resolving the three old act handles through the new public identifier API returned HTTP errors. No authentication/access restriction was bypassed, and no statute PDF or complete Act was acquired, and no statutory text was imported or indexed.

Candidate official record identifiers remain BNS 2023-45 (`123456789/20062`), BNSS 2023-46 (`123456789/20099`), and BSA 2023-47 (`123456789/20063`), with assent on 25 December 2023 according to the indexed official act register. The old copyright page timed out; a guessed new copyright-policy route returned the generic JavaScript shell, not verified policy text. The [MHA website policy](https://www.mha.gov.in/en/page/website-policy) requires permission for reproduction. The Legislative Department policy URL and Gazette landing page were inaccessible in the attempted checks. No blanket government/open-data license, present-day amendment coverage, or universal subsection commencement is assumed.

**Imported statutory sections: BNS 0, BNSS 0, BSA 0; legacy IPC/CrPC/IEA 0.** Current statutory download/import remains disabled. Commencement notifications, exceptions, amendments and section-specific legal versions require authoritative review before any future import; no mapping between old/new law is inferred. Versioned ingestion requires an operator-reviewed official PDF, SHA-256, full-section exact normalized page spans, explicit verified source reuse terms, publication/consolidation dates, and per-section commencement references/applicability notes. It never downloads a file or enables a blocked source. See [PHASE6_DESIGN.md](docs/PHASE6_DESIGN.md). The existing CC BY 4.0 Supreme Court batch remains the only live legal corpus used by Phase 6.

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
