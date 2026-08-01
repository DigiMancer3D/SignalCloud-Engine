from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .model import PhysicsProfile, ShowcaseTestResult


@dataclass(slots=True)
class MotionState:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    yaw: float = 0.0
    angular_velocity: float = 0.0
    elapsed_seconds: float = 0.0
    max_speed: float = 0.0
    impact_speed: float = 0.0
    bounce_count: int = 0
    broken: bool = False
    settled: bool = False
    settle_frames: int = 0


LOOP_SECONDS = {
    "drop": 4.0,
    "bounce": 5.0,
    "slide": 5.5,
    "throw": 5.5,
    "break": 4.0,
}


def support_height(profile: PhysicsProfile) -> float:
    profile = PhysicsProfile.from_dict(profile.to_dict())
    if profile.shape == "sphere":
        return profile.collision_radius
    if profile.shape == "capsule":
        return profile.collision_half_y + profile.collision_radius
    return profile.collision_half_y


def _initial(test_name: str, profile: PhysicsProfile) -> MotionState:
    if test_name == "drop":
        state = MotionState(0.0, 5.0, 0.0, 0.0, 0.0, 0.0, angular_velocity=0.45)
    elif test_name == "bounce":
        state = MotionState(0.0, 4.0, 0.0, 1.2, -1.0, 0.4, angular_velocity=1.35)
    elif test_name == "slide":
        state = MotionState(-4.0, 0.35, 0.0, 5.5, 0.0, 0.6, angular_velocity=2.10)
    elif test_name == "throw":
        state = MotionState(-3.0, 1.35, -1.0, 6.2, 5.4, 1.7, angular_velocity=3.10)
    elif test_name == "break":
        state = MotionState(0.0, 7.5, 0.0, 0.0, -8.0, 0.0, angular_velocity=1.75)
    else:
        raise ValueError(f"unknown Showcase test: {test_name}")
    floor = support_height(profile)
    if test_name == "slide":
        state.y = floor
    elif test_name == "throw":
        state.y = max(floor + 0.70, state.y)
    else:
        state.y = max(state.y, floor + 0.20)
    return state


def _step(profile: PhysicsProfile, state: MotionState, dt: float, settle_limit: int) -> None:
    if state.settled:
        state.elapsed_seconds += dt
        return
    gravity = -9.80665 * profile.gravity_scale
    radius = min(2000.0, max(0.02, support_height(profile)))
    speed = math.sqrt(state.vx * state.vx + state.vy * state.vy + state.vz * state.vz)
    state.max_speed = max(state.max_speed, speed)
    drag_factor = max(0.0, 1.0 - profile.drag * dt)
    state.vx *= drag_factor
    state.vz *= drag_factor
    state.vy = state.vy * drag_factor + gravity * dt
    state.x += state.vx * dt
    state.y += state.vy * dt
    state.z += state.vz * dt
    state.elapsed_seconds += dt
    state.yaw = math.remainder(state.yaw + state.angular_velocity * dt, math.tau)
    state.angular_velocity *= max(0.0, 1.0 - profile.drag * dt * 0.42)

    if state.y < radius:
        incoming = abs(state.vy)
        state.impact_speed = max(state.impact_speed, incoming)
        impulse = incoming * profile.mass * profile.impact_multiplier
        state.broken = state.broken or (profile.break_threshold > 0.0 and impulse >= profile.break_threshold)
        state.y = radius
        if incoming > 0.12 and profile.restitution > 0.015:
            state.vy = incoming * profile.restitution
            state.bounce_count += 1
        else:
            state.vy = 0.0
        planar_friction = max(0.0, 1.0 - min(0.98, profile.friction * dt * 7.0))
        state.vx *= planar_friction
        state.vz *= planar_friction
        state.angular_velocity *= max(0.10, 1.0 - min(0.92, profile.friction * dt * 4.0))

    stage_half = 7.5
    if profile.shape in {"sphere", "capsule"}:
        support_x = support_z = profile.collision_radius
    else:
        support_x, support_z = profile.collision_half_x, profile.collision_half_z
    min_x = -stage_half + min(stage_half - 0.02, support_x)
    max_x = stage_half - min(stage_half - 0.02, support_x)
    min_z = -stage_half + min(stage_half - 0.02, support_z)
    max_z = stage_half - min(stage_half - 0.02, support_z)
    wall_bounce = min(0.90, max(0.18, 0.18 + profile.restitution * 0.72))
    if state.x < min_x or state.x > max_x:
        state.x = min(max_x, max(min_x, state.x))
        state.vx = -state.vx * wall_bounce
        state.angular_velocity = -state.angular_velocity * 0.82
    if state.z < min_z or state.z > max_z:
        state.z = min(max_z, max(min_z, state.z))
        state.vz = -state.vz * wall_bounce
        state.angular_velocity = -state.angular_velocity * 0.82

    planar = math.sqrt(state.vx * state.vx + state.vz * state.vz)
    if state.y <= radius + 1.0e-5 and planar < 0.025 and abs(state.vy) < 0.025:
        state.settle_frames += 1
        if profile.sleep_policy == "after_settle" and state.settle_frames > settle_limit:
            state.vx = state.vy = state.vz = 0.0
            state.angular_velocity = 0.0
            state.settled = True
    else:
        state.settle_frames = 0


def sample_test(
    profile: PhysicsProfile,
    test_name: str,
    elapsed_seconds: float,
    *,
    loop: bool = True,
    hz: int = 120,
) -> MotionState:
    profile = PhysicsProfile.from_dict(profile.to_dict())
    duration = LOOP_SECONDS.get(test_name, 5.0)
    elapsed = max(0.0, float(elapsed_seconds))
    if loop and duration > 0.0:
        elapsed = elapsed % duration
    else:
        elapsed = min(duration, elapsed)
    hz = min(1000, max(20, int(hz)))
    dt = 1.0 / hz
    state = _initial(test_name, profile)
    steps = int(elapsed * hz)
    remainder = elapsed - steps * dt
    for _ in range(steps):
        _step(profile, state, dt, max(1, hz // 3))
    if remainder > 1.0e-8:
        _step(profile, state, remainder, max(1, hz // 3))
    return state


def run_test(profile: PhysicsProfile, test_name: str, *, duration_seconds: float = 6.0, hz: int = 120) -> ShowcaseTestResult:
    profile = PhysicsProfile.from_dict(profile.to_dict())
    duration_seconds = min(30.0, max(0.1, float(duration_seconds)))
    hz = min(1000, max(20, int(hz)))
    dt = 1.0 / hz
    steps = max(1, round(duration_seconds * hz))
    state = _initial(test_name, profile)
    start = (state.x, state.y, state.z)
    for _ in range(steps):
        _step(profile, state, dt, max(1, hz // 3))

    payload = {
        "test": test_name,
        "profile": profile.to_dict(),
        "steps": steps,
        "end": [round(state.x, 7), round(state.y, 7), round(state.z, 7)],
        "yaw": round(state.yaw, 7),
        "max_speed": round(state.max_speed, 7),
        "impact_speed": round(state.impact_speed, 7),
        "bounces": state.bounce_count,
        "broken": state.broken,
    }
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    return ShowcaseTestResult(
        test_name=test_name,
        duration_seconds=duration_seconds,
        steps=steps,
        start_position=start,
        end_position=(state.x, state.y, state.z),
        max_speed=state.max_speed,
        impact_speed=state.impact_speed,
        bounce_count=state.bounce_count,
        broken=state.broken,
        settled=state.settled,
        signature=signature,
    )
