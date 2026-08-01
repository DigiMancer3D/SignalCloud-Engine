from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .model import (
    VALID_TEST_ACTIONS,
    TupdInstanceTest,
    TupdInventory,
    TupdPreview,
    TupdReceipt,
    TupdRecipe,
    TupdResultInstance,
)


def make_test_inventory() -> TupdInventory:
    return TupdInventory(
        items={
            "weapon.service-pistol": 1,
            "weapon.service-pistol.duplicate": 1,
            "weapon.prybar": 1,
            "part.signal-grip": 2,
            "part.office-bracket": 2,
            "part.upgrade-stabilizer": 1,
            "part.wall-panel": 2,
            "part.mount-bracket": 2,
            "consumable.tupd-tape": 6,
        },
        interfaces={
            "weapon.base", "weapon.service-pistol", "weapon.duplicate.match",
            "socket.grip", "socket.body", "socket.signal", "upgrade.stability",
            "object.office", "object.barrier", "tupd.tape", "safe-room", "sandbox",
        },
        xar=120,
        weapon_condition=62.0,
        weapon_weight=2.4,
        weapon_definition_id="weapon.service-pistol",
        normal_save_fingerprint="normal-save-untouched",
    )


def _signature(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def preview_recipe(recipe: TupdRecipe, inventory: TupdInventory) -> TupdPreview:
    recipe.normalize()
    preview = TupdPreview(
        forced=recipe.mode == "forced_modification" or bool(recipe.forced_connections),
        result_id=recipe.result.result_id,
        result_name=recipe.result.display_name,
        condition_before=inventory.weapon_condition,
        condition_after=max(0.0, min(100.0, inventory.weapon_condition + recipe.repair_percent)),
        weight_before=inventory.weapon_weight,
        weight_after=max(0.0, inventory.weapon_weight + recipe.weight_penalty),
        weight_delta=recipe.weight_penalty,
        stability_percent=max(0.0, min(100.0, 100.0 - recipe.stability_penalty)),
        point_budget=recipe.result.point_budget,
        xar_cost=recipe.cost_xar,
        added_interfaces=list(recipe.result.interfaces),
        added_sockets=list(recipe.result.sockets),
        connection_count=len(recipe.connections),
        forced_connection_count=len(recipe.forced_connections),
    )
    for item_id in recipe.inputs:
        if inventory.items.get(item_id, 0) <= 0:
            preview.errors.append(f"missing input: {item_id}")
    for interface in recipe.required_interfaces:
        if interface not in inventory.interfaces:
            if preview.forced and "allow_forced_connection" in recipe.validation_rules:
                preview.warnings.append(f"forced interface: {interface}")
            else:
                preview.errors.append(f"missing interface: {interface}")
    if inventory.xar < recipe.cost_xar:
        preview.errors.append("insufficient test XAR")
    if recipe.mode == "repair_full" and "weapon.duplicate.match" not in inventory.interfaces:
        preview.errors.append("matching duplicate weapon required")
    if recipe.mode == "repair_small" and inventory.weapon_condition >= 100.0:
        preview.warnings.append("weapon already at full condition")
    if preview.forced:
        preview.warnings.append("forced connection carries stability/weight penalties")
    if recipe.malfunction_policy != "none":
        preview.warnings.append(f"malfunction policy: {recipe.malfunction_policy}")
    if not recipe.connections and not recipe.forced_connections and recipe.mode not in {"repair_small", "upgrade"}:
        preview.warnings.append("recipe has no authored connection")
    preview.valid = not preview.errors
    preview.signature = _signature({
        "recipe": recipe.recipe_id,
        "revision": recipe.recipe_revision,
        "mode": recipe.mode,
        "base": recipe.base_item_id,
        "inputs": recipe.inputs,
        "connections": recipe.connections,
        "forced_connections": recipe.forced_connections,
        "test_actions": recipe.test_actions,
        "inventory": inventory.items,
        "interfaces": sorted(inventory.interfaces),
        "condition": inventory.weapon_condition,
        "weight": inventory.weapon_weight,
        "xar": inventory.xar,
        "result": asdict(recipe.result),
        "preview": {
            "condition_after": preview.condition_after,
            "weight_after": preview.weight_after,
            "stability": preview.stability_percent,
        },
    })
    return preview


def commit_recipe(recipe: TupdRecipe, inventory: TupdInventory, preview: TupdPreview | None = None) -> TupdReceipt:
    recipe.normalize()
    preview = preview or preview_recipe(recipe, inventory)
    receipt = TupdReceipt(
        recipe_id=recipe.recipe_id,
        result_id=recipe.result.result_id,
        xar_before=inventory.xar,
        xar_after=inventory.xar,
        condition_before=inventory.weapon_condition,
        condition_after=inventory.weapon_condition,
    )
    if not preview.valid:
        receipt.signature = _signature({"recipe": recipe.recipe_id, "rejected": preview.signature})
        receipt.receipt_id = f"tupd-rejected-{receipt.signature}"
        return receipt

    candidate = inventory.clone()
    for item_id in recipe.consumed_inputs:
        if candidate.items.get(item_id, 0) <= 0:
            receipt.signature = _signature({"recipe": recipe.recipe_id, "atomic_reject": item_id})
            receipt.receipt_id = f"tupd-rejected-{receipt.signature}"
            return receipt
        candidate.items[item_id] -= 1
        receipt.consumed[item_id] = receipt.consumed.get(item_id, 0) + 1
    if candidate.xar < recipe.cost_xar:
        receipt.consumed.clear()
        receipt.signature = _signature({"recipe": recipe.recipe_id, "atomic_reject": "xar"})
        receipt.receipt_id = f"tupd-rejected-{receipt.signature}"
        return receipt

    candidate.xar -= recipe.cost_xar
    candidate.weapon_condition = preview.condition_after
    candidate.weapon_weight = preview.weight_after
    candidate.items[recipe.result.result_id] = candidate.items.get(recipe.result.result_id, 0) + 1
    candidate.interfaces.update(recipe.result.interfaces)

    inventory.items = candidate.items
    inventory.interfaces = candidate.interfaces
    inventory.xar = candidate.xar
    inventory.weapon_condition = candidate.weapon_condition
    inventory.weapon_weight = candidate.weapon_weight

    receipt.committed = True
    receipt.xar_after = inventory.xar
    receipt.condition_after = inventory.weapon_condition
    receipt.signature = _signature({
        "recipe": recipe.recipe_id,
        "revision": recipe.recipe_revision,
        "preview": preview.signature,
        "before": {"xar": receipt.xar_before, "condition": receipt.condition_before},
        "after": {"xar": receipt.xar_after, "condition": receipt.condition_after},
        "consumed": receipt.consumed,
    })
    receipt.receipt_id = f"tupd-{receipt.signature}"
    return receipt


def create_result_instance(recipe: TupdRecipe, preview: TupdPreview, receipt: TupdReceipt, inventory: TupdInventory) -> TupdResultInstance | None:
    if not receipt.committed or not preview.valid:
        return None
    applied_parts = [item_id for item_id in recipe.inputs if item_id != recipe.base_item_id and not item_id.startswith("consumable.")]
    signature = _signature({
        "recipe": recipe.recipe_id,
        "revision": recipe.recipe_revision,
        "receipt": receipt.signature,
        "result": recipe.result.result_id,
        "condition": preview.condition_after,
        "weight": preview.weight_after,
        "stability": preview.stability_percent,
        "connections": recipe.connections,
        "forced": recipe.forced_connections,
    })
    instance = TupdResultInstance(
        instance_id=f"tupd-instance-{signature}",
        recipe_id=recipe.recipe_id,
        recipe_revision=recipe.recipe_revision,
        result_id=recipe.result.result_id,
        result_kind=recipe.result.result_kind,
        display_name=recipe.result.display_name,
        base_item_id=recipe.base_item_id,
        condition=preview.condition_after,
        weight=preview.weight_after,
        stability_percent=preview.stability_percent,
        point_budget=preview.point_budget,
        interfaces=sorted(set(recipe.result.interfaces) | set(inventory.interfaces & set(recipe.optional_interfaces))),
        sockets=list(recipe.result.sockets),
        tags=list(recipe.result.tags),
        applied_parts=applied_parts,
        connections=list(recipe.connections),
        forced_connections=list(recipe.forced_connections),
        test_actions=list(recipe.test_actions),
        malfunction_policy=recipe.malfunction_policy,
        signature=signature,
    )
    instance.normalize()
    return instance


def equip_or_spawn_instance(instance: TupdResultInstance) -> bool:
    if instance.broken:
        return False
    is_world_object = instance.result_kind in {"barrier", "interactable", "object", "assembly"}
    instance.equipped = not is_world_object
    instance.spawned = is_world_object
    instance.last_action = "equip" if instance.equipped else "spawn"
    instance.last_outcome = "sandbox test slot equipped" if instance.equipped else "sandbox proving-ground object spawned"
    return True


def run_instance_test(instance: TupdResultInstance, action: str) -> TupdInstanceTest:
    action = action if action in VALID_TEST_ACTIONS else "inspect"
    state_before = instance.state
    test = TupdInstanceTest(action=action, state_before=state_before)
    if not (instance.equipped or instance.spawned):
        test.outcome = "commit then equip/spawn the result before testing"
    elif instance.broken and action != "inspect":
        test.outcome = "result is broken; clear or reset the sandbox"
    elif action not in instance.test_actions:
        test.outcome = f"action {action} is not declared by this recipe"
    else:
        test.accepted = True
        if action == "inspect":
            test.outcome = f"{instance.display_name}: {instance.condition:.0f}% condition, {instance.stability_percent:.0f}% stability"
        elif action == "handle":
            test.outcome = "stable handling envelope" if instance.stability_percent >= 70.0 else "unstable handling envelope"
        elif action == "primary":
            weaponish = instance.result_kind in {"weapon-modification", "weapon-upgrade", "repair", "tool"}
            if not weaponish:
                test.accepted = False
                test.outcome = "primary action is not available for this result kind"
            else:
                test.malfunctioned = instance.malfunction_policy != "none" and instance.stability_percent < 80.0
                test.outcome = (
                    f"malfunction preview: {instance.malfunction_policy}"
                    if test.malfunctioned
                    else "sandbox primary action completed"
                )
        elif action == "collision":
            test.outcome = "bounded collision proxy held inside the proving ground"
        elif action == "break":
            instance.broken = True
            test.outcome = "sandbox break state reached; normal inventory unchanged"
        elif action == "light":
            if "signal.link" in instance.interfaces or "light.emitter" in instance.interfaces:
                test.outcome = "bounded signal-light pulse completed"
            else:
                test.accepted = False
                test.outcome = "result does not expose a signal/light interface"
        elif action == "interact":
            if instance.spawned or instance.result_kind in {"barrier", "interactable", "object", "assembly"}:
                test.outcome = "sandbox interaction proxy completed"
            else:
                test.accepted = False
                test.outcome = "result is not a spawned interactable"
    if test.accepted:
        instance.test_count += 1
        instance.last_action = action
        instance.last_outcome = test.outcome
    test.test_count = instance.test_count
    test.state_after = instance.state
    test.signature = _signature({
        "instance": instance.instance_id,
        "action": action,
        "accepted": test.accepted,
        "outcome": test.outcome,
        "count": test.test_count,
        "state_before": state_before,
        "state_after": test.state_after,
    })
    return test


class TupdSandbox:
    def __init__(self, inventory: TupdInventory | None = None) -> None:
        self.initial = (inventory or make_test_inventory()).clone()
        self.inventory = self.initial.clone()
        self.normal_save_fingerprint = self.initial.normal_save_fingerprint
        self.last_preview = TupdPreview()
        self.last_receipt = TupdReceipt()
        self.result_instance: TupdResultInstance | None = None
        self.last_test = TupdInstanceTest()
        self.test_history: list[TupdInstanceTest] = []

    @property
    def normal_save_unchanged(self) -> bool:
        return (
            self.inventory.normal_save_fingerprint == self.normal_save_fingerprint
            and self.initial.normal_save_fingerprint == self.normal_save_fingerprint
        )

    def preview(self, recipe: TupdRecipe) -> TupdPreview:
        self.last_preview = preview_recipe(recipe, self.inventory)
        return self.last_preview

    def commit(self, recipe: TupdRecipe) -> TupdReceipt:
        self.last_preview = preview_recipe(recipe, self.inventory)
        self.last_receipt = commit_recipe(recipe, self.inventory, self.last_preview)
        self.result_instance = create_result_instance(
            recipe, self.last_preview, self.last_receipt, self.inventory
        )
        self.last_test = TupdInstanceTest()
        self.test_history.clear()
        return self.last_receipt

    def equip_or_spawn(self) -> bool:
        if self.result_instance is None:
            return False
        return equip_or_spawn_instance(self.result_instance)

    def test_result(self, action: str) -> TupdInstanceTest:
        if self.result_instance is None:
            self.last_test = TupdInstanceTest(
                accepted=False,
                action=action,
                outcome="commit a valid recipe before testing",
                state_before="NO RESULT",
                state_after="NO RESULT",
                signature=_signature({"action": action, "state": "no-result"}),
            )
        else:
            self.last_test = run_instance_test(self.result_instance, action)
        self.test_history.append(self.last_test)
        return self.last_test

    def clear_result(self) -> None:
        self.result_instance = None
        self.last_test = TupdInstanceTest()
        self.test_history.clear()

    def reset(self) -> None:
        self.inventory = self.initial.clone()
        self.last_preview = TupdPreview()
        self.last_receipt = TupdReceipt()
        self.clear_result()
