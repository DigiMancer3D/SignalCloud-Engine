from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_MODES = {
    "modification",
    "forced_modification",
    "upgrade",
    "repair_small",
    "repair_full",
    "assembly",
}
VALID_TEST_ACTIONS = {
    "inspect",
    "handle",
    "primary",
    "collision",
    "break",
    "light",
    "interact",
}


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass(slots=True)
class TupdResult:
    result_id: str = "tupd.result"
    result_kind: str = "object"
    display_name: str = "Tupd Result"
    interfaces: list[str] = field(default_factory=list)
    sockets: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    point_budget: int = 1200

    def normalize(self) -> None:
        self.result_id = self.result_id.strip() or "tupd.result"
        self.result_kind = self.result_kind.strip() or "object"
        self.display_name = self.display_name.strip() or self.result_id
        self.interfaces = _unique_strings(self.interfaces)
        self.sockets = _unique_strings(self.sockets)
        self.tags = _unique_strings(self.tags)
        self.point_budget = max(64, min(50_000, int(self.point_budget)))


@dataclass(slots=True)
class TupdRecipe:
    schema: str = "signalcloud.tupd-recipe"
    schema_major: int = 1
    schema_minor: int = 1
    recipe_revision: int = 1
    recipe_id: str = "starter.tupd-draft"
    label: str = "Tupd Draft"
    mode: str = "modification"
    base_item_id: str = "weapon.service-pistol"
    inputs: list[str] = field(default_factory=lambda: ["weapon.service-pistol", "consumable.tupd-tape"])
    consumed_inputs: list[str] = field(default_factory=lambda: ["consumable.tupd-tape"])
    required_interfaces: list[str] = field(default_factory=lambda: ["weapon.base", "tupd.tape", "safe-room", "sandbox"])
    optional_interfaces: list[str] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)
    forced_connections: list[str] = field(default_factory=list)
    validation_rules: list[str] = field(default_factory=lambda: ["safe_room", "sandbox_only"])
    test_actions: list[str] = field(default_factory=lambda: ["inspect", "handle", "primary", "collision"])
    cost_xar: int = 0
    repair_percent: float = 0.0
    stability_penalty: float = 0.0
    weight_penalty: float = 0.0
    malfunction_policy: str = "none"
    result: TupdResult = field(default_factory=TupdResult)
    preview_shape: str = "assembly"
    preview_color: str = "#45d8ef"
    receipt_policy: str = "deterministic"
    extensions: dict[str, Any] = field(default_factory=dict)

    def normalize(self) -> None:
        self.schema = "signalcloud.tupd-recipe"
        self.schema_major = max(1, min(64, int(self.schema_major)))
        self.schema_minor = max(0, min(4096, int(self.schema_minor)))
        self.recipe_revision = max(1, min(9999, int(self.recipe_revision)))
        self.recipe_id = self.recipe_id.strip() or "starter.tupd-draft"
        self.label = self.label.strip() or self.recipe_id
        self.base_item_id = self.base_item_id.strip() or (self.inputs[0] if self.inputs else "object.tupd-base")
        if self.mode not in VALID_MODES:
            self.mode = "modification"
        for name in (
            "inputs", "consumed_inputs", "required_interfaces", "optional_interfaces",
            "connections", "forced_connections", "validation_rules",
        ):
            setattr(self, name, _unique_strings(getattr(self, name)))
        self.test_actions = [value for value in _unique_strings(self.test_actions) if value in VALID_TEST_ACTIONS]
        if not self.test_actions:
            self.test_actions = ["inspect"]
        if self.base_item_id not in self.inputs and self.mode != "assembly":
            self.inputs.insert(0, self.base_item_id)
        self.cost_xar = max(0, min(1_000_000, int(self.cost_xar)))
        self.repair_percent = max(0.0, min(100.0, float(self.repair_percent)))
        self.stability_penalty = max(0.0, min(100.0, float(self.stability_penalty)))
        self.weight_penalty = max(-100.0, min(1000.0, float(self.weight_penalty)))
        self.malfunction_policy = self.malfunction_policy.strip() or "none"
        self.preview_shape = self.preview_shape if self.preview_shape in {"weapon", "tool", "barrier", "assembly"} else "assembly"
        self.preview_color = self.preview_color.strip() or "#45d8ef"
        self.receipt_policy = self.receipt_policy if self.receipt_policy in {"deterministic", "none"} else "deterministic"
        self.result.normalize()


@dataclass(slots=True)
class TupdInventory:
    items: dict[str, int] = field(default_factory=dict)
    interfaces: set[str] = field(default_factory=set)
    xar: int = 120
    weapon_condition: float = 62.0
    weapon_weight: float = 2.4
    weapon_definition_id: str = "weapon.service-pistol"
    normal_save_fingerprint: str = "normal-save-untouched"

    def clone(self) -> "TupdInventory":
        return TupdInventory(
            items=dict(self.items),
            interfaces=set(self.interfaces),
            xar=self.xar,
            weapon_condition=self.weapon_condition,
            weapon_weight=self.weapon_weight,
            weapon_definition_id=self.weapon_definition_id,
            normal_save_fingerprint=self.normal_save_fingerprint,
        )


@dataclass(slots=True)
class TupdComparison:
    condition_before: float = 0.0
    condition_after: float = 0.0
    weight_before: float = 0.0
    weight_after: float = 0.0
    stability_before: float = 100.0
    stability_after: float = 100.0
    point_budget: int = 0
    added_interfaces: list[str] = field(default_factory=list)
    added_sockets: list[str] = field(default_factory=list)
    connection_count: int = 0
    forced_connection_count: int = 0


@dataclass(slots=True)
class TupdPreview:
    valid: bool = False
    forced: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_id: str = ""
    result_name: str = ""
    condition_before: float = 0.0
    condition_after: float = 0.0
    weight_before: float = 0.0
    weight_after: float = 0.0
    weight_delta: float = 0.0
    stability_percent: float = 100.0
    point_budget: int = 0
    xar_cost: int = 0
    added_interfaces: list[str] = field(default_factory=list)
    added_sockets: list[str] = field(default_factory=list)
    connection_count: int = 0
    forced_connection_count: int = 0
    signature: str = ""

    def comparison(self) -> TupdComparison:
        return TupdComparison(
            condition_before=self.condition_before,
            condition_after=self.condition_after,
            weight_before=self.weight_before,
            weight_after=self.weight_after,
            stability_before=100.0,
            stability_after=self.stability_percent,
            point_budget=self.point_budget,
            added_interfaces=list(self.added_interfaces),
            added_sockets=list(self.added_sockets),
            connection_count=self.connection_count,
            forced_connection_count=self.forced_connection_count,
        )


@dataclass(slots=True)
class TupdReceipt:
    committed: bool = False
    receipt_id: str = ""
    recipe_id: str = ""
    result_id: str = ""
    xar_before: int = 0
    xar_after: int = 0
    condition_before: float = 0.0
    condition_after: float = 0.0
    consumed: dict[str, int] = field(default_factory=dict)
    signature: str = ""


@dataclass(slots=True)
class TupdResultInstance:
    schema: str = "signalcloud.tupd-instance"
    schema_major: int = 1
    schema_minor: int = 0
    instance_id: str = ""
    recipe_id: str = ""
    recipe_revision: int = 1
    result_id: str = ""
    result_kind: str = "object"
    display_name: str = ""
    base_item_id: str = ""
    condition: float = 0.0
    weight: float = 0.0
    stability_percent: float = 100.0
    point_budget: int = 0
    interfaces: list[str] = field(default_factory=list)
    sockets: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    applied_parts: list[str] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)
    forced_connections: list[str] = field(default_factory=list)
    test_actions: list[str] = field(default_factory=list)
    malfunction_policy: str = "none"
    equipped: bool = False
    spawned: bool = False
    broken: bool = False
    test_count: int = 0
    last_action: str = ""
    last_outcome: str = ""
    signature: str = ""

    @property
    def state(self) -> str:
        if self.broken:
            return "BROKEN"
        if self.equipped:
            return "EQUIPPED"
        if self.spawned:
            return "SPAWNED"
        return "COMMITTED / NOT EQUIPPED"

    def normalize(self) -> None:
        self.schema = "signalcloud.tupd-instance"
        self.schema_major = max(1, min(64, int(self.schema_major)))
        self.schema_minor = max(0, min(4096, int(self.schema_minor)))
        self.recipe_revision = max(1, min(9999, int(self.recipe_revision)))
        self.condition = max(0.0, min(100.0, float(self.condition)))
        self.weight = max(0.0, min(10_000.0, float(self.weight)))
        self.stability_percent = max(0.0, min(100.0, float(self.stability_percent)))
        self.point_budget = max(64, min(50_000, int(self.point_budget)))
        self.test_count = max(0, min(1_000_000, int(self.test_count)))
        self.interfaces = _unique_strings(self.interfaces)
        self.sockets = _unique_strings(self.sockets)
        self.tags = _unique_strings(self.tags)
        self.applied_parts = _unique_strings(self.applied_parts)
        self.connections = _unique_strings(self.connections)
        self.forced_connections = _unique_strings(self.forced_connections)
        self.test_actions = [value for value in _unique_strings(self.test_actions) if value in VALID_TEST_ACTIONS]
        self.malfunction_policy = self.malfunction_policy.strip() or "none"


@dataclass(slots=True)
class TupdInstanceTest:
    accepted: bool = False
    action: str = "inspect"
    outcome: str = ""
    state_before: str = ""
    state_after: str = ""
    test_count: int = 0
    malfunctioned: bool = False
    signature: str = ""
