from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.pcp3.advanced_authoring import ensure_authoring
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.model import PCPDocument
from tools.pcp3.runtime_factory import ALLOWED_ACTIONS, ALLOWED_TRIGGER_TYPES, ensure_runtime_factory

INTERACTION_SCHEMA = "pcp3_guarded_interaction_v1"
MAX_STATE_ENTRIES = 1024
MAX_EVENT_LEDGER = 1024
MAX_ACTIVE_PROXIES = 64

LEGACY_ACTION_ALIASES = {
    "scanner_reveal": "reveal",
    "light_pulse": "pulse_light",
}


def normalize_action(value: Any) -> str:
    action = str(value or "none").strip() or "none"
    return LEGACY_ACTION_ALIASES.get(action, action)


@dataclass(frozen=True)
class InteractionIssue:
    severity: str
    code: str
    message: str
    hint: str = ""

    def to_json(self) -> dict[str, str]:
        return asdict(self)


DEFAULT_INTERACTION: dict[str, Any] = {
    "schema": INTERACTION_SCHEMA,
    "enabled": False,
    "game_enabled": False,
    "stress_enabled": True,
    "default_cooldown": 1.3,
    "alert_duration": 3.0,
    "pulse_duration": 1.25,
    "proxy_lifetime": 5.0,
    "max_state_entries": 256,
    "max_event_ledger": 256,
    "max_active_proxies": 16,
    "reset_policy": "zone_exit",
    "show_runtime_evidence": True,
    "console_event_log": True,
    "future_attributes": {},
}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _vec3(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return (0.0, 0.0, 0.0)
    return (_finite(value[0]), _finite(value[1]), _finite(value[2]))


def ensure_runtime_interaction(document: PCPDocument) -> dict[str, Any]:
    current = document.metadata.get("runtime_interaction")
    if not isinstance(current, dict):
        current = {}
        document.metadata["runtime_interaction"] = current
    for key, value in DEFAULT_INTERACTION.items():
        if key not in current:
            current[key] = json.loads(json.dumps(value)) if isinstance(value, (dict, list)) else value
    current["schema"] = INTERACTION_SCHEMA
    current["default_cooldown"] = max(0.05, min(60.0, _finite(current.get("default_cooldown"), 1.3)))
    current["alert_duration"] = max(0.1, min(60.0, _finite(current.get("alert_duration"), 3.0)))
    current["pulse_duration"] = max(0.1, min(30.0, _finite(current.get("pulse_duration"), 1.25)))
    current["proxy_lifetime"] = max(0.25, min(120.0, _finite(current.get("proxy_lifetime"), 5.0)))
    current["max_state_entries"] = max(16, min(MAX_STATE_ENTRIES, int(_finite(current.get("max_state_entries"), 256))))
    current["max_event_ledger"] = max(16, min(MAX_EVENT_LEDGER, int(_finite(current.get("max_event_ledger"), 256))))
    current["max_active_proxies"] = max(1, min(MAX_ACTIVE_PROXIES, int(_finite(current.get("max_active_proxies"), 16))))
    if current.get("reset_policy") not in {"zone_exit", "session", "manual"}:
        current["reset_policy"] = "zone_exit"
    return current


def validate_runtime_interaction(document: PCPDocument) -> list[InteractionIssue]:
    settings = ensure_runtime_interaction(document)
    factory = ensure_runtime_factory(document)
    authoring = ensure_authoring(document)
    issues: list[InteractionIssue] = []
    if not settings["enabled"]:
        issues.append(InteractionIssue("info", "interaction_disabled", "Guarded Interaction Runtime is disabled; Branch 6 behavior remains unchanged."))
    if settings["enabled"] and not factory["enabled"]:
        issues.append(InteractionIssue("warning", "factory_disabled", "Interaction execution requires the Runtime Factory to be enabled."))
    if settings["enabled"] and not (settings["game_enabled"] or settings["stress_enabled"]):
        issues.append(InteractionIssue("warning", "no_target", "Interaction Runtime is enabled but neither Game nor Stress is selected."))
    approved = 0
    for index, trigger in enumerate(item for item in authoring.get("triggers", []) if isinstance(item, dict)):
        trigger_type = str(trigger.get("type", "proximity"))
        original_action = str(trigger.get("action", "none"))
        action = normalize_action(original_action)
        if original_action != action:
            issues.append(InteractionIssue("info", "legacy_action_alias", f"Trigger {index + 1} action {original_action!r} is normalized to {action!r}."))
        if trigger_type in ALLOWED_TRIGGER_TYPES and action in ALLOWED_ACTIONS and action != "none":
            approved += 1
        else:
            issues.append(InteractionIssue(
                "warning",
                "trigger_deferred",
                f"Trigger {index + 1} ({trigger_type}/{original_action}) remains telemetry-only.",
                "Use an approved Branch 7 type and action.",
            ))
        if action == "set_theme":
            target = str(trigger.get("target", ""))
            if target and not target.startswith("#") and not any(str(slot.get("semantic", "")) == target for slot in authoring.get("theme", {}).get("slots", []) if isinstance(slot, dict)):
                issues.append(InteractionIssue("info", "theme_target_missing", f"Trigger {index + 1} targets theme {target!r}, but no matching theme slot exists."))
    if not approved:
        severity = "warning" if settings["enabled"] else "info"
        issues.append(InteractionIssue(severity, "no_approved_actions", "No approved non-empty trigger actions are currently authored.", "Open Authoring → Gameplay or use the Interaction quick-trigger bridge."))
    if not any(issue.severity == "error" for issue in issues):
        issues.append(InteractionIssue("pass", "interaction_compilable", "Guarded interaction data can be compiled without arbitrary code execution."))
    return issues


def compile_runtime_interaction(document: PCPDocument) -> dict[str, Any]:
    settings = ensure_runtime_interaction(document)
    authoring = ensure_authoring(document)
    triggers: list[dict[str, Any]] = []
    for index, source in enumerate(item for item in authoring.get("triggers", []) if isinstance(item, dict)):
        trigger_type = str(source.get("type", "proximity"))
        original_action = str(source.get("action", "none"))
        normalized_action = normalize_action(original_action)
        approved = trigger_type in ALLOWED_TRIGGER_TYPES and normalized_action in ALLOWED_ACTIONS
        triggers.append({
            "index": index,
            "id": str(source.get("id", f"trigger-{index + 1}")),
            "type": trigger_type,
            "position": list(_vec3(source.get("position"))),
            "radius": max(0.05, min(10_000.0, _finite(source.get("radius"), 1.0))),
            "action": normalized_action if approved else "none",
            "original_action": original_action,
            "target": str(source.get("target", "")),
            "delay": max(0.0, min(3600.0, _finite(source.get("delay"), 0.0))),
            "repeat": bool(source.get("repeat", False)),
            "cooldown": max(0.05, min(60.0, _finite(source.get("cooldown"), settings["default_cooldown"]))),
            "runtime_status": "approved" if approved else "telemetry_only",
        })
    return {
        "schema": INTERACTION_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "enabled": bool(settings["enabled"]),
        "targets": {"game": bool(settings["game_enabled"]), "stress": bool(settings["stress_enabled"])},
        "timing": {
            "default_cooldown": float(settings["default_cooldown"]),
            "alert_duration": float(settings["alert_duration"]),
            "pulse_duration": float(settings["pulse_duration"]),
            "proxy_lifetime": float(settings["proxy_lifetime"]),
        },
        "limits": {
            "max_state_entries": int(settings["max_state_entries"]),
            "max_event_ledger": int(settings["max_event_ledger"]),
            "max_active_proxies": int(settings["max_active_proxies"]),
        },
        "reset_policy": str(settings["reset_policy"]),
        "show_runtime_evidence": bool(settings["show_runtime_evidence"]),
        "console_event_log": bool(settings["console_event_log"]),
        "triggers": triggers,
        "approved_actions": sorted(ALLOWED_ACTIONS - {"none"}),
        "blocked_actions": ["script", "damage", "economy", "inventory", "save", "teleport", "external_program", "unrestricted_ai"],
        "policy": "bounded_reversible_visual_state_no_gameplay_mutation",
        "future_attributes": settings.get("future_attributes", {}),
    }


def _json_value(value: Any) -> str:
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def runtime_interaction_udata(payload: dict[str, Any]) -> str:
    lines = ["@udata 1", "", "[interaction]"]
    lines += [
        f"schema: {_json_value(payload['schema'])};",
        f"enabled: {_json_value(payload['enabled'])};",
        f"game_enabled: {_json_value(payload['targets']['game'])};",
        f"stress_enabled: {_json_value(payload['targets']['stress'])};",
        f"default_cooldown: {_json_value(payload['timing']['default_cooldown'])};",
        f"alert_duration: {_json_value(payload['timing']['alert_duration'])};",
        f"pulse_duration: {_json_value(payload['timing']['pulse_duration'])};",
        f"proxy_lifetime: {_json_value(payload['timing']['proxy_lifetime'])};",
        f"max_state_entries: {_json_value(payload['limits']['max_state_entries'])};",
        f"max_event_ledger: {_json_value(payload['limits']['max_event_ledger'])};",
        f"max_active_proxies: {_json_value(payload['limits']['max_active_proxies'])};",
        f"reset_policy: {_json_value(payload['reset_policy'])};",
        f"show_runtime_evidence: {_json_value(payload['show_runtime_evidence'])};",
        f"console_event_log: {_json_value(payload['console_event_log'])};",
        "",
    ]
    for trigger in payload["triggers"]:
        index = int(trigger["index"])
        lines += [
            f"[trigger_policy.{index}]",
            f"id: {_json_value(trigger['id'])};",
            f"runtime_status: {_json_value(trigger['runtime_status'])};",
            f"delay: {_json_value(trigger['delay'])};",
            f"repeat: {_json_value(trigger['repeat'])};",
            f"cooldown: {_json_value(trigger['cooldown'])};",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def write_runtime_interaction_files(asset_dir: Path, document: PCPDocument) -> dict[str, Path]:
    payload = compile_runtime_interaction(document)
    asset_name = slugify(document.asset_id)
    json_path = asset_dir / f"{asset_name}.pcp3interaction.json"
    udata_path = asset_dir / f"{asset_name}.pcp3interaction.udata"
    atomic_write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(udata_path, runtime_interaction_udata(payload))
    return {"json": json_path, "udata": udata_path}


class InteractionSimulator:
    """Small deterministic mirror used by editor dry runs and automated tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.trigger_state: dict[int, dict[str, Any]] = {}
        self.visible = True
        self.revealed = False
        self.alert_until = 0.0
        self.pulse_until = 0.0
        self.theme_target = ""
        self.proxies: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.zone = ""

    def reset(self) -> None:
        self.trigger_state.clear()
        self.visible = True
        self.revealed = False
        self.alert_until = 0.0
        self.pulse_until = 0.0
        self.theme_target = ""
        self.proxies.clear()
        self.events.clear()

    def update(self, *, now: float, viewer: tuple[float, float, float], scanner: bool = False,
               interaction_pressed: bool = False, zone: str = "Test") -> list[dict[str, Any]]:
        if self.zone and self.zone != zone and self.payload.get("reset_policy") == "zone_exit":
            self.reset()
        self.zone = zone
        if not self.payload.get("enabled"):
            return []
        emitted: list[dict[str, Any]] = []
        for trigger in self.payload.get("triggers", []):
            if trigger.get("runtime_status") != "approved" or trigger.get("action") == "none":
                continue
            index = int(trigger.get("index", 0))
            state = self.trigger_state.setdefault(index, {"active": False, "armed": now, "last": -1e30, "fired": 0})
            position = _vec3(trigger.get("position"))
            distance = math.sqrt(sum((viewer[i] - position[i]) ** 2 for i in range(3)))
            inside = distance <= float(trigger.get("radius", 1.0))
            trigger_type = str(trigger.get("type", "proximity"))
            condition = {
                "proximity": inside,
                "threshold": inside,
                "scanner": scanner,
                "interaction": inside and interaction_pressed,
                "timer": True,
            }.get(trigger_type, False)
            rising = condition and not bool(state["active"])
            if condition and not state["active"]:
                state["armed"] = now
            state["active"] = condition
            delay = float(trigger.get("delay", 0.0))
            cooldown = float(trigger.get("cooldown", self.payload["timing"]["default_cooldown"]))
            ready = now >= float(state["armed"]) + delay and now >= float(state["last"]) + cooldown
            repeat = bool(trigger.get("repeat", False))
            should_fire = condition and ready and (state["fired"] == 0 or repeat)
            if trigger_type in {"proximity", "threshold", "scanner", "interaction"} and not repeat:
                should_fire = should_fire and rising
            if not should_fire:
                continue
            state["last"] = now
            state["fired"] += 1
            event = {"time": now, "trigger": index, "action": trigger["action"], "target": trigger.get("target", "")}
            emitted.append(event)
            self.events.append(event)
            self._apply(event, position)
        ledger_cap = int(self.payload["limits"]["max_event_ledger"])
        self.events = self.events[-ledger_cap:]
        self.proxies = [item for item in self.proxies if item["expires"] > now]
        return emitted

    def _apply(self, event: dict[str, Any], position: tuple[float, float, float]) -> None:
        now = float(event["time"])
        action = str(event["action"])
        if action == "show":
            self.visible = True
        elif action == "hide":
            self.visible = False
        elif action == "reveal":
            self.visible = True
            self.revealed = True
        elif action == "alert":
            self.alert_until = now + float(self.payload["timing"]["alert_duration"])
        elif action == "pulse_light":
            self.pulse_until = now + float(self.payload["timing"]["pulse_duration"])
        elif action == "set_theme":
            self.theme_target = str(event.get("target", ""))
        elif action == "spawn_proxy":
            self.proxies.append({"position": position, "expires": now + float(self.payload["timing"]["proxy_lifetime"])})
            self.proxies = self.proxies[-int(self.payload["limits"]["max_active_proxies"]):]
