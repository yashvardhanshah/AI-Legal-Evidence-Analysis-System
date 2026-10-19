# Data sourcing register

No datasets or legal documents have been downloaded, ingested or licensed for use in Phase 1. The following are **candidates**, not validated acquisitions. No license or authenticity finding is implied by listing a URL.

| Candidate publisher / original entry point | Intended use | Required checks before acquisition |
| --- | --- | --- |
| AWS Open Data registry / https://registry.opendata.aws/indian-supreme-court-judgments/ | Published judgment retrieval | Identify original publishing court, dataset operator, applicable license, versions, metadata and subset size |
| AWS Open Data registry / https://registry.opendata.aws/indian-high-court-judgments/ | Expanded judgment retrieval | Verify provenance and reuse terms per collection and document |
| India Code / https://www.indiacode.nic.in/ | Authoritative statutory texts | Verify exact enactments, amendments, effective dates and reuse terms; retain original citations |
| NIST / https://cfreds.nist.gov/ | Forensic pipeline benchmarks | Review each collection's license and whether intentionally simulated; do not represent test scenarios as real police cases |
| COCO / https://cocodataset.org/ | Supported object detection evaluation | Review annotation terms and individual image rights separately; retain image provenance |

Phase 2 acquisition procedure: verify publisher and original document URL, inspect license/terms, distinguish authentic records from simulations, document format and estimated size, request approval for large downloads, then acquire a small reproducible permitted subset. Record source URL, retrieval date, license text/reference, version, bytes, SHA-256, selection method and limitations in a source manifest. Keep acquired files ignored. Do not bypass CAPTCHA or authentication. Do not combine unrelated documents into an invented criminal case.
