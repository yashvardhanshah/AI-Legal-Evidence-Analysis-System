"""Offline model NER and deterministic literal spans; never infer legal findings."""
from functools import lru_cache
import re

from app.config import get_settings
from app import ner_model

RULES_VERSION = "literal-references-v1"
MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
RULES = [
    ("DATE", "date.named_day_first", rf"\b\d{{1,2}}(?:st|nd|rd|th)?[ \t]+{MONTH}[,.]?[ \t]+\d{{4}}\b"),
    ("DATE", "date.named_month_first", rf"\b{MONTH}[ \t]+\d{{1,2}}(?:st|nd|rd|th)?[,]?[ \t]+\d{{4}}\b"),
    ("DATE", "date.numeric", r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    ("DATE", "date.month_day_without_inferred_year", rf"\b{MONTH}[ \t]+\d{{1,2}}(?:st|nd|rd|th)?\b(?![,]?[ \t]+\d{{4}})"),
    ("TIME", "time.clock", r"\b(?:(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:[ \t]*[ap]\.?m\.?)?|(?:0?[1-9]|1[0-2])[ \t]*[ap]\.?m\.?)"),
    ("DOCUMENT_REFERENCE", "reference.numbered", r"\b(?:FIR|Case|Appeal|Petition|Writ(?:[ \t]+Petition)?|Civil[ \t]+Appeal|Criminal[ \t]+Appeal|Section|Article)[ \t]+(?:No\.?[ \t]*)?(?=[A-Za-z0-9()/.-]*\d)[A-Za-z0-9][A-Za-z0-9()/.-]*(?:[ \t]+of[ \t]+\d{4})?"),
    ("DOCUMENT_REFERENCE", "reference.exhibit", r"\b(?:Exhibit|Annexure)[ \t]+(?:No\.?[ \t]*)?(?:[A-Z](?:[/-][A-Z0-9]{1,10})?|\d[A-Z0-9()/.-]{0,20})(?![A-Z0-9])"),
    ("DOCUMENT_REFERENCE", "reference.abbreviated_section", r"\b(?:s\.|ss\.)[ \t]*\d+(?:[ \t]*\([A-Za-z0-9]+\))*"),
    ("DOCUMENT_REFERENCE", "reference.reported_citation", r"\b(?:AIR[ \t]+\d{4}[ \t]+(?:SC|[A-Z]{2,})[ \t]+\d+|\(?\d{4}\)?[ \t]+\d+[ \t]+(?:SCC|SCR)[ \t]+\d+)\b"),
]


def rule_entities(text):
    output, seen = [], set()
    for label, name, pattern in RULES:
        for match in re.finditer(pattern, text, re.I):
            key = label, match.start(), match.end()
            if key in seen:
                continue
            seen.add(key)
            output.append({"label": label, "text": match.group(), "char_start": match.start(), "char_end": match.end(),
                           "extractor": "rule", "score": None, "provenance": {"rule_id": name, "version": RULES_VERSION, "interpretation": "literal mention; not validated date, case identity or legal applicability"}})
    return output


@lru_cache
def ner():
    ner_model.verify(get_settings().private_root)
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer
    torch.set_num_threads(2)
    folder = str(ner_model.directory(get_settings().private_root))
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False, use_fast=True)
    model = AutoModelForTokenClassification.from_pretrained(folder, local_files_only=True, trust_remote_code=False, use_safetensors=True).to("cpu").eval()
    return tokenizer, model


def named_entities(text):
    if not text.strip():
        return []
    import torch
    tokenizer, model = ner()
    encoded = tokenizer(text, return_offsets_mapping=True, return_overflowing_tokens=True,
                        truncation=True, stride=64, max_length=512, padding=True, return_tensors="pt")
    offsets = encoded.pop("offset_mapping").tolist()
    encoded.pop("overflow_to_sample_mapping", None)
    found = []
    mapping = {"PER": "PERSON", "ORG": "ORGANIZATION", "LOC": "LOCATION"}
    for chunk, positions in enumerate(offsets):
        with torch.inference_mode():
            probabilities = model(**{key: value[chunk:chunk+1] for key, value in encoded.items()}).logits.softmax(-1)[0]
        # CoNLL labels describe words. Aggregate WordPiece probabilities before
        # applying BIO boundaries so repeated B tags inside one word cannot
        # produce fragments such as "V", "idy", "a" from "Vidya".
        groups = []
        for index, (word_id, position) in enumerate(zip(encoded.word_ids(batch_index=chunk), positions)):
            if word_id is None or position[0] == position[1]:
                continue
            if not groups or groups[-1][0] != word_id:
                groups.append((word_id, [index]))
            else:
                groups[-1][1].append(index)
        words = []
        for _, indices in groups:
            score, label_id = probabilities[indices].mean(0).max(0)
            words.append((positions[indices[0]][0], positions[indices[-1]][1], label_id.item(), score.item()))
        current = None

        def finish():
            nonlocal current
            if current:
                start, end = current["char_start"], current["char_end"]
                # Strip only boundary whitespace; offsets still refer to exact page text.
                while start < end and text[start].isspace(): start += 1
                while end > start and text[end-1].isspace(): end -= 1
                if end > start and any(character.isalnum() for character in text[start:end]):
                    found.append({"label": current["label"], "text": text[start:end], "char_start": start, "char_end": end,
                                  "extractor": "ner", "score": sum(current["scores"])/len(current["scores"]),
                                  "provenance": {"model": ner_model.MODEL, "revision": ner_model.REVISION,
                                                 "word_aggregation": "average subtoken BIO probabilities",
                                                 "score_method": "mean selected word-averaged BIO softmax; uncalibrated", "chunk": chunk}})
                current = None

        for start, end, index, score in words:
            predicted = model.config.id2label[index]
            prefix, _, short = predicted.partition("-")
            label = mapping.get(short)
            if start == end or not label:
                finish()
                continue
            if current and (prefix == "B" or current["label"] != label):
                finish()
            if current is None:
                current = {"label": label, "char_start": start, "char_end": end, "scores": [score]}
            else:
                current["char_end"] = end
                current["scores"].append(score)
        finish()
    # Remove exact overlap-window duplicates and contained seam fragments.
    unique = {}
    for item in sorted(found, key=lambda e: (-(e["char_end"]-e["char_start"]), -e["score"])):
        if any(other["label"] == item["label"] and other["char_start"] <= item["char_start"] and other["char_end"] >= item["char_end"] for other in unique.values()):
            continue
        unique[item["label"], item["char_start"], item["char_end"]] = item
    return list(unique.values())


def entities(text):
    output = named_entities(text)+rule_entities(text)
    for item in output:
        if text[item["char_start"]:item["char_end"]] != item["text"]:
            raise ValueError("Entity provenance span mismatch")
    return sorted(output, key=lambda e: (e["char_start"], e["char_end"], e["label"]))
