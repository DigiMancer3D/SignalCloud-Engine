#include "engine/pcp3/pcp3_asset.hpp"

#include <cmath>
#include <iostream>
#include <vector>

using signalcloud::pcp3::Asset;
using signalcloud::pcp3::LayeredPoint;
using signalcloud::pcp3::PreviewPurpose;
using signalcloud::pcp3::RuntimeContext;
using signalcloud::pcp3::RuntimeEntityBone;
using signalcloud::pcp3::RuntimeEntityBoneKeyframe;
using signalcloud::pcp3::RuntimeEntityClip;

namespace {

Asset make_entity() {
    Asset asset;
    asset.metadata.asset_id = "branch8_entity";
    asset.metadata.preview_zone = "Entity Lab";
    asset.metadata.preview_position = {0.0F, 0.0F, 0.0F};
    asset.metadata.preview_scale = 1.0F;
    asset.metadata.enabled = true;
    asset.metadata.auto_preview_in_game = false;
    asset.runtime_entity.present = true;
    asset.runtime_entity.enabled = true;
    asset.runtime_entity.game_enabled = true;
    asset.runtime_entity.stress_enabled = true;
    asset.runtime_entity.entity_kind = "enemy";
    asset.runtime_entity.movement_profile = "stationary";
    asset.runtime_entity.bone_deformation = true;
    asset.runtime_entity.detection_radius = 10.0F;
    asset.runtime_entity.attack_radius = 2.5F;
    asset.runtime_entity.attack_cooldown = 1.3F;
    asset.runtime_entity.state_clips["idle"] = RuntimeEntityClip{"Idle", 2.0F, true};
    asset.runtime_entity.state_clips["move"] = RuntimeEntityClip{"Idle", 2.0F, true};
    asset.runtime_entity.state_clips["alert"] = RuntimeEntityClip{"Idle", 2.0F, true};
    asset.runtime_entity.state_clips["attack"] = RuntimeEntityClip{"Idle", 2.0F, true};
    RuntimeEntityBone bone;
    bone.name = "root";
    bone.start = {0.0F, 0.0F, 0.0F};
    bone.end = {0.0F, 1.0F, 0.0F};
    bone.weight_channel = 0;
    asset.runtime_entity.bones.push_back(bone);
    RuntimeEntityBoneKeyframe key;
    key.state = "idle";
    key.bone_channel = 0;
    key.time = 0.0F;
    key.rotation_degrees = {0.0F, 0.0F, 90.0F};
    asset.runtime_entity.bone_keyframes.push_back(key);

    LayeredPoint point;
    point.point.position[0] = 1.0F;
    point.point.position[1] = 0.0F;
    point.point.position[2] = 0.0F;
    point.point.radius = 2.0F;
    point.point.color[0] = 1.0F;
    point.point.color[1] = 1.0F;
    point.point.color[2] = 1.0F;
    point.point.color[3] = 1.0F;
    point.point.normal[1] = 1.0F;
    point.point.density = 1.0F;
    point.attribute0 = 1.0F;
    point.attribute1 = 1000.0F;
    asset.layered_points.push_back(point);
    return asset;
}

}  // namespace

int main() {
    auto asset = make_entity();
    RuntimeContext context;
    context.time_seconds = 0.0;
    context.viewer_position = {50.0F, 0.0F, 0.0F};
    auto points = signalcloud::pcp3::points_for_zone({asset}, "Entity Lab", PreviewPurpose::game, context, 1000U);
    if (points.size() != 1U) return 1;
    if (std::abs(points[0].position[0]) > 0.001F || std::abs(points[0].position[1] - 1.0F) > 0.001F) return 2;

    // Entity execution alone must make the asset visible without auto-preview or Runtime Factory.
    asset.runtime_entity.bone_deformation = false;
    asset.runtime_entity.movement_profile = "hover";
    asset.runtime_entity.hover_height = 0.5F;
    asset.runtime_entity.hover_period = 2.0F;
    context.time_seconds = 0.5;
    points = signalcloud::pcp3::points_for_zone({asset}, "Entity Lab", PreviewPurpose::game, context, 1000U);
    if (points.empty() || std::abs(points[0].position[1] - 0.5F) > 0.01F) return 3;

    // Stress/debug evidence should add a state ring and rig lines but remain bounded.
    asset.runtime_entity.bone_deformation = true;
    asset.runtime_entity.movement_profile = "stationary";
    context.time_seconds = 0.0;
    context.viewer_position = {1.0F, 0.0F, 0.0F};
    context.debug_evidence = true;
    points = signalcloud::pcp3::points_for_zone({asset}, "Entity Lab", PreviewPurpose::stress, context, 2000U);
    if (points.size() <= 1U || points.size() > 2000U) return 4;

    std::cout << "PCP3 entity behavior and animation runtime PASS\n";
    return 0;
}
