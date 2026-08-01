from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def octal_epoch(timestamp: int | None = None) -> str:
    return oct(int(time.time()) if timestamp is None else int(timestamp))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checksum_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def author_payload(author: dict[str, Any]) -> dict[str, Any]:
    return {
        "creator_name": str(author.get("creator_name", "")).strip(),
        "title": str(author.get("title", "")).strip(),
        "type": str(author.get("asset_type", author.get("type", ""))).strip(),
        "description": str(author.get("description", "")).strip(),
        "tags": sorted({str(tag).strip() for tag in author.get("tags", []) if str(tag).strip()}),
    }


def new_certificate(author: dict[str, Any], project_id: str, content_checksum: str) -> dict[str, Any]:
    epoch = int(time.time())
    serial = f"PCP3-{uuid.uuid4().hex.upper()}"
    clean_author = author_payload(author)
    proof_source = {
        "domain": "Point Cloud Paint++ creator certificate",
        "serial_id": serial,
        "project_id": project_id,
        "epoch_octal": octal_epoch(epoch),
        "author": clean_author,
        "content_checksum": content_checksum,
    }
    proof = sha256_hex(canonical_json(proof_source))
    return {
        "schema": "pcp3_creator_certificate_v1",
        "serial_id": serial,
        "project_id": project_id,
        "created_epoch_octal": octal_epoch(epoch),
        "author": clean_author,
        "initial_hash_proof": proof,
        "initial_checksum": content_checksum,
        "proof_chain": [
            {
                "kind": "initial_save",
                "epoch_octal": octal_epoch(epoch),
                "hash_proof": proof,
                "checksum": content_checksum,
                "author": clean_author,
            }
        ],
        "amendments": [],
    }


def update_certificate(certificate: dict[str, Any], author: dict[str, Any], content_checksum: str,
                       editor_name: str = "") -> tuple[dict[str, Any], bool]:
    clean_author = author_payload(author)
    previous_author = author_payload(certificate.get("author", {}))
    author_changed = clean_author != previous_author
    previous_checksum = str(certificate.get("proof_chain", [{}])[-1].get("checksum", ""))
    content_changed = content_checksum != previous_checksum
    if not author_changed and not content_changed:
        return certificate, False

    epoch = int(time.time())
    chain = certificate.setdefault("proof_chain", [])
    previous_proof = str(chain[-1].get("hash_proof", certificate.get("initial_hash_proof", ""))) if chain else ""
    visible_version = int(certificate.get("version", 1)) + 1
    proof_source = {
        "domain": "Point Cloud Paint++ certificate continuation",
        "serial_id": certificate.get("serial_id", ""),
        "project_id": certificate.get("project_id", ""),
        "previous_hash_proof": previous_proof,
        "epoch_octal": octal_epoch(epoch),
        "author": clean_author,
        "content_checksum": content_checksum,
        "version": visible_version,
    }
    new_proof = sha256_hex(canonical_json(proof_source))
    event = {
        "kind": "author_form_update" if author_changed else "asset_update",
        "epoch_octal": octal_epoch(epoch),
        "hash_proof": new_proof,
        "checksum": content_checksum,
        "previous_hash_proof": previous_proof,
        "version": visible_version,
        "author": clean_author,
    }
    if author_changed:
        event["edited_user_name"] = editor_name.strip() or clean_author.get("creator_name", "")
        certificate.setdefault("amendments", []).append(dict(event))
        certificate["author"] = clean_author
    chain.append(event)
    certificate["version"] = visible_version
    certificate["latest_hash_proof"] = new_proof
    certificate["latest_checksum"] = content_checksum
    return certificate, True


def validate_certificate(certificate: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = ("schema", "serial_id", "project_id", "created_epoch_octal", "author", "initial_hash_proof")
    for key in required:
        if key not in certificate:
            issues.append(f"Missing certificate field: {key}")
    chain = certificate.get("proof_chain", [])
    if not isinstance(chain, list) or not chain:
        issues.append("Certificate proof chain is empty.")
        return issues

    serial_id = str(certificate.get("serial_id", ""))
    project_id = str(certificate.get("project_id", ""))
    previous = ""
    for index, event in enumerate(chain):
        if not isinstance(event, dict):
            issues.append(f"Proof event {index} is not an object.")
            continue
        proof = str(event.get("hash_proof", ""))
        if len(proof) != 64:
            issues.append(f"Proof event {index} has an invalid SHA-256 value.")
        event_author = author_payload(event.get("author", certificate.get("author", {})))
        if index == 0:
            proof_source = {
                "domain": "Point Cloud Paint++ creator certificate",
                "serial_id": serial_id,
                "project_id": project_id,
                "epoch_octal": str(event.get("epoch_octal", certificate.get("created_epoch_octal", ""))),
                "author": event_author,
                "content_checksum": str(event.get("checksum", certificate.get("initial_checksum", ""))),
            }
            expected = sha256_hex(canonical_json(proof_source))
            if proof != expected or certificate.get("initial_hash_proof") != proof:
                issues.append("Initial certificate hash proof does not validate.")
        else:
            if event.get("previous_hash_proof") != previous:
                issues.append(f"Proof event {index} does not link to the previous proof.")
            proof_source = {
                "domain": "Point Cloud Paint++ certificate continuation",
                "serial_id": serial_id,
                "project_id": project_id,
                "previous_hash_proof": previous,
                "epoch_octal": str(event.get("epoch_octal", "")),
                "author": event_author,
                "content_checksum": str(event.get("checksum", "")),
                "version": int(event.get("version", index + 1)),
            }
            expected = sha256_hex(canonical_json(proof_source))
            if proof != expected:
                issues.append(f"Proof event {index} hash does not validate.")
        previous = proof

    if len(chain) > 1:
        if certificate.get("latest_hash_proof") != previous:
            issues.append("Latest certificate hash does not match the proof-chain tail.")
        if int(certificate.get("version", 0)) != int(chain[-1].get("version", 0)):
            issues.append("Visible certificate version does not match the proof-chain tail.")
    return issues
