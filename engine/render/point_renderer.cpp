#include "engine/render/point_renderer.hpp"

#include <algorithm>
#include <cstddef>
#include <cmath>
#include <vector>

namespace signalcloud::render {
namespace {
constexpr const char* vertex_source = R"GLSL(#version 330 core
layout(location = 0) in vec3 inPosition;
layout(location = 1) in float inRadius;
layout(location = 2) in vec4 inColor;
layout(location = 3) in vec3 inNormal;
layout(location = 4) in float inDensity;

uniform mat4 uViewProjection;
uniform float uTime;
uniform float uPulse;
uniform float uPointScale;
uniform float uDensityScale;
uniform int uScanner;
uniform int uTactical;
uniform float uSignalLevel;
uniform vec3 uLocalSirenPosition;
uniform float uLocalSirenRadius;
uniform float uLocalSirenStrength;
uniform vec3 uSplashPosition;
uniform float uSplashRadius;
uniform float uSplashStrength;
uniform int uSplashBomb;
uniform vec3 uLightPosition;
uniform float uLightRadius;
uniform float uLightStrength;
uniform int uAuthoredLightCount;
uniform vec3 uAuthoredLightPositions[4];
uniform vec3 uAuthoredLightColors[4];
uniform float uAuthoredLightRadii[4];
uniform float uAuthoredLightStrengths[4];
uniform vec3 uAuthoredGlobalColor;
uniform float uAuthoredGlobalStrength;
uniform float uAuthoredPointSizeBoost;
uniform float uAuthoredVisibilityFloor;
uniform int uRenderClass;
uniform int uMaterialEnabled[3];
uniform vec3 uMaterialSourceColors[3];
uniform vec3 uMaterialAccentColors[3];
uniform vec3 uMaterialDetailColors[3];
uniform float uMaterialJG[3];
uniform float uMaterialJL[3];
uniform float uMaterialJC[3];
uniform float uMaterialJS[3];
uniform float uMaterialJitter[3];
uniform float uMaterialVariation[3];
uniform float uMaterialOpacity[3];
uniform float uMaterialSeed[3];
uniform int uMaterialPatternMode[3];
uniform float uMaterialPrimarySpacing[3];
uniform float uMaterialSecondarySpacing[3];
uniform float uMaterialBreakupScale[3];
uniform float uMaterialBreakupStrength[3];
uniform float uMaterialDisplacementWeight[3];
uniform float uMaterialColorWeight[3];
uniform float uMaterialLineWidth[3];
uniform float uMaterialDefinitionLayers[15];
uniform vec3 uSoundPosition;
uniform float uSoundRadius;
uniform float uSoundStrength;
uniform int uSoundBand;
uniform float uSoundSeed;
uniform float uSoundObstruction;
uniform int uSoundWaveCount;
uniform float uSoundWaveSharpness;
uniform float uSoundDisplacementScale;
uniform float uSoundColorMix;
uniform float uSoundVisibilityFloor;
uniform vec3 uVoidPosition;
uniform float uVoidRadius;
uniform float uVoidStrength;
uniform int uPreviewClip;
uniform vec3 uPreviewViewer;
uniform vec3 uPreviewCenter;
uniform vec3 uPreviewNormal;
uniform float uPreviewHalfWidth;
uniform float uPreviewBottom;
uniform float uPreviewTop;
uniform float uPreviewStrength;

out vec4 vColor;
out float vDensity;
out float vDepth;
out float vScannerBand;
out float vWater;
out float vLocalSiren;
out float vSplash;
out float vLight;
out float vAuthoredLight;
out float vAuthoredGlobal;
out float vMaterialOpacity;
out float vMaterialPattern;
flat out int vMaterialMode;
out float vSound;
out float vVoid;
out float vStableOverlay;
out float vCeilingFixture;
out float vPreview;
flat out int vSolidBackplate;

void main() {
    float water = inDensity < -1.05 ? 2.0 : (inDensity < 0.0 ? 1.0 : 0.0);
    vec3 worldPosition = inPosition;
    float splashMask = 0.0;
    if (water > 0.5 && water < 1.5) {
        worldPosition.y += sin(inPosition.x * 0.72 + inPosition.z * 0.43 + uTime * 1.8) * 0.035;
        float splashDistance = length(worldPosition.xz - uSplashPosition.xz);
        float ringWidth = uSplashBomb == 1 ? 1.35 : 0.72;
        splashMask = (1.0 - smoothstep(ringWidth, ringWidth + 0.85,
                      abs(splashDistance - uSplashRadius))) * uSplashStrength;
        worldPosition.y += splashMask * (uSplashBomb == 1 ? 0.34 : 0.18);
    }
    if (uPreviewClip == 1) {
        vec3 normal = normalize(uPreviewNormal + vec3(0.000001, 0.0, 0.000001));
        vec3 ray = worldPosition - uPreviewViewer;
        float denominator = dot(ray, normal);
        float planeDistance = dot(uPreviewCenter - uPreviewViewer, normal);
        vec3 tangent = vec3(-normal.z, 0.0, normal.x);
        float viewerLateral = abs(dot(uPreviewViewer - uPreviewCenter, tangent));
        bool crossedThreshold = planeDistance < -0.02 && planeDistance > -1.45 &&
                                viewerLateral <= uPreviewHalfWidth + 0.90;
        bool visible = crossedThreshold || abs(denominator) > 0.00001;
        float t = (!crossedThreshold && visible) ? planeDistance / denominator : 0.0;
        // A small guard band prevents oblique point sprites from disappearing
        // at the exact threshold plane. Once the player has geometrically
        // crossed the aperture but room ownership has not switched yet, the
        // destination is rendered directly instead of being clipped behind
        // the plane they already crossed.
        visible = crossedThreshold || (visible && t > -0.015 && t < 1.035);
        vec3 hit = crossedThreshold ? uPreviewViewer : uPreviewViewer + ray * t;
        float lateral = abs(dot(hit - uPreviewCenter, tangent));
        bool beyondOpening = dot(worldPosition - uPreviewCenter, normal) >= -0.14;
        const float apertureGuard = 0.18;
        visible = crossedThreshold || (visible && beyondOpening &&
                  lateral <= uPreviewHalfWidth + apertureGuard &&
                  hit.y >= uPreviewBottom - 0.14 && hit.y <= uPreviewTop + 0.14);
        if (!visible) {
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
            gl_PointSize = 0.0;
            vColor = vec4(0.0);
            vDensity = 0.0;
            vDepth = 9999.0;
            vScannerBand = 0.0;
            vWater = 0.0;
            vLocalSiren = 0.0;
            vSplash = 0.0;
            vLight = 0.0;
            vAuthoredLight = 0.0;
            vAuthoredGlobal = 0.0;
            vMaterialOpacity = 1.0;
            vMaterialPattern = 0.0;
            vMaterialMode = 0;
            vSound = 0.0;
            vVoid = 0.0;
            vStableOverlay = 0.0;
            vCeilingFixture = 0.0;
            vPreview = 0.0;
            vSolidBackplate = 0;
            return;
        }
    }
    bool environmentPass = uRenderClass == 0;
    // Dynamic world text keeps depth and perspective, but a reserved density
    // class isolates it from material/audio deformation just like readable UI.
    bool stableWorldText = uRenderClass == 1 && inDensity >= 3.5;
    bool solidBackplate = uRenderClass == 2 && inDensity >= 4.5;
    bool stableOverlay = uRenderClass == 2 || stableWorldText;
    int materialIndex = inNormal.y > 0.62 ? 0 : (inNormal.y < -0.62 ? 2 : 1);
    float materialEnabled = float(uMaterialEnabled[materialIndex]) * (environmentPass ? 1.0 : 0.0);

    // A room material is a surface-shell treatment, not a generic normal-based
    // skin for every environment object. Ground height excludes furniture tops;
    // the warm structural-wall palette excludes desks, benches, portals, and
    // colored obstacle faces that happen to have vertical normals.
    float floorShellMask = 1.0 - smoothstep(0.14, 0.48, abs(worldPosition.y));
    float wallWarmMask = smoothstep(0.43, 0.58, inColor.r) *
                         smoothstep(0.36, 0.51, inColor.g);
    float wallBlueMask = smoothstep(0.17, 0.29, inColor.b) *
                         (1.0 - smoothstep(0.58, 0.78, inColor.b));
    float wallBalanceMask = 1.0 - smoothstep(0.24, 0.48, abs(inColor.r - inColor.g));
    float wallShellMask = clamp(wallWarmMask * wallBlueMask * wallBalanceMask, 0.0, 1.0);
    float ceilingShellMask = smoothstep(2.10, 2.85, worldPosition.y);
    if (materialIndex == 0) materialEnabled *= floorShellMask;
    if (materialIndex == 1) materialEnabled *= wallShellMask;
    if (materialIndex == 2) materialEnabled *= ceilingShellMask;

    float materialJG = max(0.001, uMaterialJG[materialIndex]);
    float materialJL = max(0.001, uMaterialJL[materialIndex]);
    float materialJC = max(0.01, uMaterialJC[materialIndex]);
    float materialJS = max(0.02, uMaterialJS[materialIndex]);
    float materialSeed = uMaterialSeed[materialIndex];
    int patternMode = uMaterialPatternMode[materialIndex];
    float primarySpacing = max(0.08, uMaterialPrimarySpacing[materialIndex]);
    float secondarySpacing = max(0.08, uMaterialSecondarySpacing[materialIndex]);
    float breakupScale = max(0.20, uMaterialBreakupScale[materialIndex]);
    float breakupStrength = clamp(uMaterialBreakupStrength[materialIndex], 0.0, 1.0);
    float displacementWeight = clamp(uMaterialDisplacementWeight[materialIndex], 0.0, 1.0);
    float colorWeight = clamp(uMaterialColorWeight[materialIndex], 0.0, 1.0);
    float lineWidth = clamp(uMaterialLineWidth[materialIndex], 0.02, 0.48);
    int layerBase = materialIndex * 5;
    float definitionHDLight = clamp(uMaterialDefinitionLayers[layerBase + 0], 0.0, 1.0);
    float definitionHDTexture = clamp(uMaterialDefinitionLayers[layerBase + 1], 0.0, 1.0);
    float definitionOuterLight = clamp(uMaterialDefinitionLayers[layerBase + 2], 0.0, 1.0);
    float definitionOuterTexture = clamp(uMaterialDefinitionLayers[layerBase + 3], 0.0, 1.0);
    float definitionInnerTexture = clamp(uMaterialDefinitionLayers[layerBase + 4], 0.0, 1.0);

    // Stable world-anchored surface coordinates. Walls use a tangent axis plus
    // height instead of XZ projection, preventing carpet-like stripes and
    // orientation-dependent line density.
    vec2 materialUV = worldPosition.xz;
    if (materialIndex == 1) {
        bool wallFacesX = abs(inNormal.x) > abs(inNormal.z);
        materialUV = vec2(wallFacesX ? worldPosition.z : worldPosition.x, worldPosition.y);
    }
    float phase = fract(materialSeed * 0.0000001192092896) * 6.28318530718;
    float primaryWave = sin(materialUV.x * 6.28318530718 / primarySpacing + phase);
    float secondaryWave = sin(materialUV.y * 6.28318530718 / secondarySpacing + phase * 0.371);
    float breakupWave = sin((materialUV.x + materialUV.y * 0.73) * 6.28318530718 / breakupScale +
                            sin(materialUV.y * 1.37 + phase * 0.19) * 0.83);
    float materialMacro = sin((materialUV.x + materialSeed * 0.00017) / materialJG +
                              (materialUV.y - materialSeed * 0.00011) / materialJS);
    float materialLocal = sin((materialUV.x - materialUV.y) / materialJL + materialSeed * 0.0013);
    float materialCluster = sin(length(materialUV) / materialJC + materialSeed * 0.00071);
    float materialPattern = 0.5;
    float detailSignal = materialLocal;
    if (patternMode == 1) {
        // Carpet/fiber rows: dense directional structure and full displacement.
        materialPattern = clamp(0.50 + 0.27 * primaryWave + 0.13 * secondaryWave +
                                0.10 * materialMacro + 0.08 * breakupWave, 0.0, 1.0);
        detailSignal = primaryWave;
    } else if (patternMode == 2) {
        // Wallpaper restores the useful A5a1 legacy jitter character without
        // restoring its cross-object leakage. Several incommensurate,
        // world-anchored signals create paper grain that breaks up procedural
        // point rows. Only a faint, widely spaced tangent seam remains; there
        // is deliberately no periodic height wave and no screen-space weave.
        float legacyWallGrain = sin(materialMacro * 1.73 + materialLocal * 0.61 +
                                    materialCluster * 1.19 + phase * 0.23);
        float paperGrain = materialMacro * 0.31 + materialLocal * 0.27 +
                           materialCluster * 0.22 + legacyWallGrain * 0.20;
        float sparseSeam = smoothstep(1.0 - lineWidth, 1.0, abs(primaryWave));
        float seamBreakSignal = 0.5 + 0.5 * sin(
            (materialUV.x * 0.29 + materialUV.y * 0.47) * 6.28318530718 / breakupScale +
            phase * 0.31 + legacyWallGrain * 0.35);
        float brokenSeam = sparseSeam * smoothstep(0.58, 0.82, seamBreakSignal);
        materialPattern = clamp(0.50 + paperGrain * breakupStrength * 0.09 +
                                brokenSeam * 0.045, 0.38, 0.64);
        detailSignal = legacyWallGrain;
    } else if (patternMode == 3) {
        // Flat ceiling tiles: wide seams and very low color variation.
        float seamU = smoothstep(1.0 - lineWidth, 1.0, abs(primaryWave));
        float seamV = smoothstep(1.0 - lineWidth, 1.0, abs(secondaryWave));
        materialPattern = clamp(0.58 - max(seamU, seamV) * 0.20 +
                                breakupWave * breakupStrength * 0.04, 0.0, 1.0);
        detailSignal = max(seamU, seamV);
    } else {
        materialPattern = clamp(0.5 + 0.22 * materialMacro + 0.18 * materialLocal +
                                0.10 * materialCluster, 0.0, 1.0);
    }
    // Definition layers are deliberately restrained at their shipped values so
    // the visually accepted A5a2r2 carpet, wallpaper, and ceiling remain the baseline.
    float definitionDisplacement = 0.97 + definitionHDTexture * 0.03;
    float materialDisplacement = (materialPattern - 0.5) * 2.0 *
                                 uMaterialJitter[materialIndex] * displacementWeight *
                                 definitionDisplacement * materialEnabled;
    worldPosition += normalize(inNormal + vec3(0.00001)) * materialDisplacement;
    float ceilingSurface = environmentPass && inNormal.y < -0.62 ? 1.0 : 0.0;
    float ceilingLuma = dot(inColor.rgb, vec3(0.2126, 0.7152, 0.0722));
    float ceilingFixture = ceilingSurface * smoothstep(0.72, 0.90, ceilingLuma);
    // Bright ceiling points are lowered slightly to create a deterministic
    // hanging-fixture silhouette without changing the resident cloud.
    worldPosition += normalize(inNormal + vec3(0.00001)) * ceilingFixture * 0.070;
    vec3 materialColor = mix(uMaterialSourceColors[materialIndex],
                             uMaterialAccentColors[materialIndex], materialPattern);
    float detailBand = smoothstep(0.72, 0.94, abs(detailSignal));
    float outerBand = smoothstep(0.46, 0.92, abs(materialPattern - 0.5) * 2.0);
    float detailMix = patternMode == 2 ? 0.10 : 0.34;
    detailMix *= 0.94 + definitionHDTexture * 0.06;
    detailMix += definitionInnerTexture * 0.025 + definitionOuterTexture * outerBand * 0.018;
    materialColor = mix(materialColor, uMaterialDetailColors[materialIndex],
                        clamp(detailBand * detailMix, 0.0, 0.72));
    float materialOpacity = mix(1.0, uMaterialOpacity[materialIndex], materialEnabled);

    float deformationPass = stableOverlay ? 0.0 : 1.0;
    float lightDistance = length(worldPosition - uLightPosition);
    float lightMask = deformationPass * (1.0 - smoothstep(uLightRadius * 0.22, max(0.1, uLightRadius), lightDistance)) * uLightStrength;
    float authoredMask = 0.0;
    vec3 authoredTint = vec3(0.0);
    for (int authoredIndex = 0; authoredIndex < 4; ++authoredIndex) {
        if (authoredIndex >= uAuthoredLightCount) break;
        float authoredDistance = length(worldPosition - uAuthoredLightPositions[authoredIndex]);
        float contribution = (1.0 - smoothstep(uAuthoredLightRadii[authoredIndex] * 0.16,
                             max(0.1, uAuthoredLightRadii[authoredIndex]), authoredDistance)) *
                             uAuthoredLightStrengths[authoredIndex];
        authoredMask += contribution;
        authoredTint += uAuthoredLightColors[authoredIndex] * contribution;
    }
    vec3 authoredColor = authoredMask > 0.0001 ? authoredTint / authoredMask : vec3(1.0);
    authoredMask = clamp(authoredMask, 0.0, 1.8) * deformationPass;
    float authoredGlobal = clamp(uAuthoredGlobalStrength, 0.0, 1.35) * deformationPass;
    float soundDistance = length(worldPosition.xz - uSoundPosition.xz);
    float soundSharpness = clamp(uSoundWaveSharpness, 0.08, 1.0);
    float authoredWaveCount = clamp(float(uSoundWaveCount), 1.0, 8.0);
    float waveSpacing = clamp(uSoundRadius / (authoredWaveCount + 0.5), 0.42, 1.60);
    float soundMask = 0.0;
    float soundWavePhase = 0.0;
    // Each authored wave is a separate trailing ring. A5a3 previously used
    // wave_count only as a sine frequency multiplier, so three or five waves
    // still looked like one ring. The fixed loop is GLSL 3.30 compatible.
    for (int waveIndex = 0; waveIndex < 8; ++waveIndex) {
        if (waveIndex >= uSoundWaveCount) break;
        float ringRadius = uSoundRadius - float(waveIndex) * waveSpacing;
        if (ringRadius <= 0.18) continue;
        float ringWidth = mix(0.46, 0.14, soundSharpness) + ringRadius * 0.012;
        float ring = 1.0 - smoothstep(ringWidth, ringWidth + 0.34,
                                     abs(soundDistance - ringRadius));
        float ringWeight = 1.0 - float(waveIndex) / (authoredWaveCount + 1.0) * 0.42;
        float weighted = ring * ringWeight;
        if (weighted > soundMask) {
            soundMask = weighted;
            soundWavePhase = float(waveIndex) * 0.83;
        }
    }
    soundMask *= deformationPass * uSoundStrength;
    float soundBandFrequency = uSoundBand == 0 ? 3.2 : (uSoundBand == 2 ? 11.5 : (uSoundBand == 3 ? 8.0 : 6.2));
    float soundPhase = soundDistance * soundBandFrequency -
                       uTime * (8.0 + float(uSoundBand) * 2.2) +
                       uSoundSeed * 0.00091 + soundWavePhase;
    float soundShape = pow(abs(sin(soundPhase)), mix(2.4, 0.55, soundSharpness));
    float soundJitter = sin(soundPhase) * soundShape * soundMask *
                        (1.0 - clamp(uSoundObstruction, 0.0, 1.0) * 0.55);
    worldPosition += normalize(inNormal + vec3(0.00001)) * soundJitter *
                     0.095 * clamp(uSoundDisplacementScale, 0.0, 1.5);
    float voidDistance = length(worldPosition - uVoidPosition);
    float voidMask = deformationPass * (uVoidRadius > 0.0
        ? (1.0 - smoothstep(uVoidRadius * 0.18, max(0.1, uVoidRadius), voidDistance)) * uVoidStrength
        : 0.0);
    float sirenDistance = length(worldPosition.xz - uLocalSirenPosition.xz);
    float sirenMask = deformationPass * (1.0 - smoothstep(uLocalSirenRadius * 0.35, max(0.1, uLocalSirenRadius), sirenDistance)) * uLocalSirenStrength;
    float jitter = sin(worldPosition.x * 17.0 + worldPosition.z * 11.0 + uTime * 31.0);
    worldPosition.xz += vec2(jitter, -jitter) * sirenMask * 0.11;
    vec4 clip = uViewProjection * vec4(worldPosition, 1.0);
    gl_Position = clip;
    float depthScale = max(0.65, abs(clip.w));
    float scannerBoost = uScanner == 1 ? 1.32 : 1.0;
    float tacticalBoost = uTactical == 1 ? 1.65 : 1.0;
    float densitySize = mix(0.72, 1.22, clamp(abs(inDensity) * uDensityScale, 0.0, 1.0));
    float wallSurface = 1.0 - smoothstep(0.20, 0.62, abs(inNormal.y));
    float nearWallBoost = mix(1.0, 2.55, wallSurface * (1.0 - smoothstep(0.38, 2.15, depthScale)));
    gl_PointSize = clamp((inRadius * 950.0 * scannerBoost * tacticalBoost *
                         uPointScale * densitySize * nearWallBoost *
                         (1.0 + lightMask * 0.28 + soundMask * 0.42 + authoredMask * uAuthoredPointSizeBoost +
                          ceilingFixture * 0.34) *
                         (1.0 - voidMask * 0.92)) / depthScale + uPulse * 0.22,
                         1.0, 52.0);
    float normalLight = stableOverlay ? 1.0 :
        0.58 + 0.42 * max(dot(normalize(inNormal + vec3(0.001)),
                              normalize(vec3(-0.3, 0.8, 0.4))), 0.0);
    vec3 color = inColor.rgb * normalLight;
    color = mix(color, color * materialColor * (1.0 + uMaterialVariation[materialIndex]),
                materialEnabled * colorWeight * (0.96 + definitionHDTexture * 0.04));
    color *= 1.0 + materialEnabled * definitionHDLight * 0.015;
    color = mix(color, color * uMaterialAccentColors[materialIndex] * 1.08,
                materialEnabled * definitionOuterLight * outerBand * 0.025);
    float globalBrightness = stableOverlay ? 1.0 :
        mix(0.42, 1.18, clamp(authoredGlobal, 0.0, 1.0));
    color *= globalBrightness;
    color = mix(color, color * uAuthoredGlobalColor,
                clamp(authoredGlobal * 0.38, 0.0, 0.52));
    if (uScanner == 1) color = mix(color, vec3(0.28, 0.95, 0.74), 0.50);
    color = mix(color, vec3(1.0, 0.98, 0.82), clamp(lightMask * 0.58, 0.0, 0.72));
    color = mix(color, color * authoredColor * 1.45,
                clamp(authoredMask * 0.72, 0.0, 0.82));
    color = mix(color, vec3(0.015, 0.006, 0.028), clamp(voidMask * 0.96, 0.0, 0.96));
    if (uTactical == 1) color = mix(color, vec3(0.18, 0.72, 0.96), 0.58);
    float previewPass = uPreviewClip == 1 ? clamp(uPreviewStrength, 0.0, 1.0) : 0.0;
    // Destination previews carry a bounded inferred light/visibility floor.
    // This does not copy the destination room's full lighting state; it merely
    // prevents a valid clipped preview from collapsing into a black void when
    // the source room has little local-light influence.
    color *= 1.0 + previewPass * 0.20;
    float authoredAlpha = stableOverlay ? inColor.a :
        max(inColor.a * clamp(0.52 + authoredGlobal * 0.48, 0.18, 1.25),
            inColor.a * uAuthoredVisibilityFloor);
    authoredAlpha = max(authoredAlpha, inColor.a * previewPass * 0.28);
    vColor = vec4(color, authoredAlpha);
    vDensity = clamp(abs(inDensity) * uDensityScale, 0.0, 2.0);
    vDepth = abs(clip.w);
    float sweep = fract((inPosition.z + inPosition.x * 0.18 + uTime * 4.0) * 0.055);
    vScannerBand = 1.0 - smoothstep(0.035, 0.16, abs(sweep - 0.5));
    vWater = water;
    vLocalSiren = sirenMask;
    vSplash = splashMask;
    vLight = lightMask;
    vAuthoredLight = authoredMask;
    vAuthoredGlobal = authoredGlobal;
    vMaterialOpacity = materialOpacity;
    vMaterialPattern = materialPattern * materialEnabled;
    vMaterialMode = materialEnabled > 0.001 ? patternMode : 0;
    vSound = soundMask;
    vVoid = voidMask;
    vStableOverlay = stableOverlay ? 1.0 : 0.0;
    vCeilingFixture = ceilingFixture;
    vPreview = previewPass;
    vSolidBackplate = solidBackplate ? 1 : 0;
}
)GLSL";

constexpr const char* fragment_source = R"GLSL(#version 330 core
in vec4 vColor;
in float vDensity;
in float vDepth;
in float vScannerBand;
in float vWater;
in float vLocalSiren;
in float vSplash;
in float vLight;
in float vAuthoredLight;
in float vAuthoredGlobal;
in float vMaterialOpacity;
in float vMaterialPattern;
flat in int vMaterialMode;
in float vSound;
in float vVoid;
in float vStableOverlay;
in float vCeilingFixture;
in float vPreview;
flat in int vSolidBackplate;
uniform float uTime;
uniform float uPulse;
uniform int uScanner;
uniform int uTactical;
uniform float uSignalLevel;
uniform float uSoundColorMix;
uniform float uSoundVisibilityFloor;
out vec4 outColor;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

void main() {
    vec2 centered = gl_PointCoord * 2.0 - 1.0;
    float radius = dot(centered, centered);
    bool solidBackplate = vSolidBackplate == 1;
    if (!solidBackplate && radius > 1.0) discard;
    // SCUI backplates remain point-native, but their reserved density class
    // uses square, fully covered sprites. Circular soft edges left thousands
    // of translucent pinholes through which bright room signs bled.
    float soft = solidBackplate ? 1.0 : smoothstep(1.0, 0.18, radius);
    float stable = step(0.5, vStableOverlay);
    float grain = mix(0.86 + 0.23 * hash12(gl_FragCoord.xy + vec2(floor(uTime * 12.0))), 1.0, stable);
    float scanline = mix(0.93 + 0.07 * sin(gl_FragCoord.y * 1.35 + uTime * 8.0), 1.0, stable);
    float distanceFade = mix(clamp(1.28 - vDepth * 0.018, 0.22, 1.0), 1.0, stable);
    float densityAlpha = mix(clamp(vDensity + 0.16, 0.08, 1.25),
                             clamp(vDensity + 0.42, 0.72, 1.25), stable);
    float alpha = solidBackplate ? vColor.a : vColor.a * soft * densityAlpha * distanceFade;
    vec3 color = vColor.rgb;
    if (uScanner == 1) {
        alpha = min(1.0, alpha * (1.10 + vScannerBand * 1.05));
        color += vec3(0.04, 0.30, 0.21) * vScannerBand;
    }
    if (uTactical == 1) alpha = min(1.0, alpha * 1.30);
    float signalNoise = mix(0.72 + 0.28 * hash12(gl_FragCoord.xy * 0.37 + vec2(floor(uTime * 18.0))), 1.0, stable);
    float signalBrightness = mix(mix(0.48, 1.0, clamp(uSignalLevel, 0.0, 1.0)), 1.0, stable);
    color *= mix(signalNoise, 1.0, max(stable, clamp(uSignalLevel * 1.35, 0.0, 1.0)));
    if (vWater > 1.5) {
        float caustic = 0.82 + 0.18 * sin(gl_FragCoord.x * 0.031 -
                                           gl_FragCoord.y * 0.023 + uTime * 1.9);
        color = mix(color, vec3(0.08, 0.44, 0.68), 0.58) * caustic;
        alpha *= 0.88;
    } else if (vWater > 0.5) {
        float shimmer = 0.74 + 0.26 * sin(gl_FragCoord.x * 0.055 + gl_FragCoord.y * 0.031 + uTime * 3.6);
        color = mix(color, vec3(0.12, 0.48, 0.74), 0.42) * shimmer;
        alpha *= 0.78;
    }
    if (vLocalSiren > 0.0) {
        float dropout = hash12(gl_FragCoord.xy * 0.19 + vec2(floor(uTime * 24.0)));
        if (dropout < vLocalSiren * 0.58) discard;
        color = mix(color, vec3(0.96, 0.18, 0.10), vLocalSiren * 0.44);
        alpha *= 1.0 - vLocalSiren * 0.32;
    }
    if (vSplash > 0.0) {
        color = mix(color, vec3(0.40, 0.90, 1.0), clamp(vSplash * 0.82, 0.0, 1.0));
        alpha = min(1.0, alpha * (1.0 + vSplash * 0.55));
    }
    if (vLight > 0.0) {
        alpha = min(1.0, alpha * (1.0 + vLight * 0.34));
    }
    if (vAuthoredGlobal > 0.0) {
        alpha = min(1.0, alpha * (0.76 + clamp(vAuthoredGlobal, 0.0, 1.2) * 0.46));
    }
    if (vAuthoredLight > 0.0) {
        alpha = min(1.0, alpha * (1.0 + vAuthoredLight * 0.58));
    }
    if (vPreview > 0.0) {
        alpha = max(alpha, vColor.a * (0.34 + vPreview * 0.24));
        color *= 1.0 + vPreview * 0.12;
    }
    if (vCeilingFixture > 0.0) {
        float fixtureCenter = 1.0 - smoothstep(0.04, 0.54, radius);
        float fixtureRim = smoothstep(0.44, 0.98, radius);
        color = mix(color * (1.10 + fixtureCenter * 0.22),
                    vec3(0.025, 0.022, 0.018), fixtureRim * 0.74);
        alpha = min(1.0, alpha * (1.0 + fixtureCenter * 0.26));
    }
    if (vMaterialPattern > 0.0) {
        // The screen-space weave is intentionally limited to carpet fibers.
        // Applying it to walls/ceilings created view-dependent diagonal bands
        // that appeared to change spacing while the player turned or moved.
        if (vMaterialMode == 1) {
            float fiberWeave = 0.92 + 0.12 * sin(
                (gl_FragCoord.x + gl_FragCoord.y) * 0.17 + vMaterialPattern * 6.2831);
            color *= fiberWeave;
        }
        alpha *= clamp(vMaterialOpacity, 0.02, 1.0);
    }
    if (vSound > 0.0) {
        color = mix(color, vec3(1.0, 0.92, 0.56),
                    clamp(vSound * uSoundColorMix, 0.0, 0.92));
        alpha = max(alpha, vColor.a * clamp(uSoundVisibilityFloor, 0.0, 0.4) * vSound);
        alpha = min(1.0, alpha * (1.0 + vSound * 0.65));
    }
    if (vVoid > 0.0) {
        float dropout = hash12(gl_FragCoord.xy * 0.27 + vec2(floor(uTime * 20.0)));
        if (dropout < vVoid * 0.82) discard;
        color = mix(color, vec3(0.07, 0.01, 0.12), vVoid * 0.88);
        alpha *= 1.0 - vVoid * 0.78;
    }
    outColor = vec4(color * grain * scanline * signalBrightness * (1.0 + uPulse * 0.05), alpha);
}
)GLSL";
}

PointRenderer::~PointRenderer() { shutdown(); }

GLuint PointRenderer::compile(GLenum type, const char* source, std::string* error) {
    const GLuint shader = gl_->create_shader(type);
    gl_->shader_source(shader, 1, &source, nullptr);
    gl_->compile_shader(shader);
    GLint ok = 0;
    gl_->get_shader_iv(shader, GL_COMPILE_STATUS, &ok);
    if (ok == 0) {
        GLint length = 0;
        gl_->get_shader_iv(shader, GL_INFO_LOG_LENGTH, &length);
        std::vector<char> log(static_cast<std::size_t>(length > 1 ? length : 1));
        gl_->get_shader_info_log(shader, length, nullptr, log.data());
        if (error != nullptr) *error = std::string("Shader compilation failed: ") + log.data();
        gl_->delete_shader(shader);
        return 0;
    }
    return shader;
}

void PointRenderer::configure_point_vao(GLuint vao, GLuint vbo) {
    gl_->bind_vertex_array(vao);
    gl_->bind_buffer(GL_ARRAY_BUFFER, vbo);
    constexpr GLsizei stride = static_cast<GLsizei>(sizeof(PointGpu));
    gl_->enable_vertex_attrib_array(0);
    gl_->vertex_attrib_pointer(0, 3, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<const void*>(offsetof(PointGpu, position)));
    gl_->enable_vertex_attrib_array(1);
    gl_->vertex_attrib_pointer(1, 1, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<const void*>(offsetof(PointGpu, radius)));
    gl_->enable_vertex_attrib_array(2);
    gl_->vertex_attrib_pointer(2, 4, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<const void*>(offsetof(PointGpu, color)));
    gl_->enable_vertex_attrib_array(3);
    gl_->vertex_attrib_pointer(3, 3, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<const void*>(offsetof(PointGpu, normal)));
    gl_->enable_vertex_attrib_array(4);
    gl_->vertex_attrib_pointer(4, 1, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<const void*>(offsetof(PointGpu, density)));
}

bool PointRenderer::initialize(GLApi& gl, const PointCloud& cloud, std::string* error) {
    if (!initialize_points(gl, cloud.points(), error)) return false;
    return true;
}

bool PointRenderer::initialize_points(GLApi& gl, const std::vector<PointGpu>& points, std::string* error) {
    gl_ = &gl;
    const GLuint vertex = compile(GL_VERTEX_SHADER, vertex_source, error);
    if (vertex == 0) return false;
    const GLuint fragment = compile(GL_FRAGMENT_SHADER, fragment_source, error);
    if (fragment == 0) { gl_->delete_shader(vertex); return false; }

    program_ = gl_->create_program();
    gl_->attach_shader(program_, vertex);
    gl_->attach_shader(program_, fragment);
    gl_->link_program(program_);
    gl_->delete_shader(vertex);
    gl_->delete_shader(fragment);
    GLint ok = 0;
    gl_->get_program_iv(program_, GL_LINK_STATUS, &ok);
    if (ok == 0) {
        GLint length = 0;
        gl_->get_program_iv(program_, GL_INFO_LOG_LENGTH, &length);
        std::vector<char> log(static_cast<std::size_t>(length > 1 ? length : 1));
        gl_->get_program_info_log(program_, length, nullptr, log.data());
        if (error != nullptr) *error = std::string("Shader link failed: ") + log.data();
        shutdown();
        return false;
    }

    gl_->gen_vertex_arrays(1, &vao_);
    gl_->gen_buffers(1, &vbo_);
    configure_point_vao(vao_, vbo_);
    gl_->gen_vertex_arrays(1, &marker_vao_);
    gl_->gen_buffers(1, &marker_vbo_);
    configure_point_vao(marker_vao_, marker_vbo_);
    gl_->gen_vertex_arrays(1, &dynamic_vao_);
    gl_->gen_buffers(1, &dynamic_vbo_);
    configure_point_vao(dynamic_vao_, dynamic_vbo_);
    gl_->gen_vertex_arrays(1, &viewmodel_vao_);
    gl_->gen_buffers(1, &viewmodel_vbo_);
    configure_point_vao(viewmodel_vao_, viewmodel_vbo_);

    matrix_location_ = gl_->get_uniform_location(program_, "uViewProjection");
    time_location_ = gl_->get_uniform_location(program_, "uTime");
    pulse_location_ = gl_->get_uniform_location(program_, "uPulse");
    scanner_location_ = gl_->get_uniform_location(program_, "uScanner");
    tactical_location_ = gl_->get_uniform_location(program_, "uTactical");
    point_scale_location_ = gl_->get_uniform_location(program_, "uPointScale");
    density_scale_location_ = gl_->get_uniform_location(program_, "uDensityScale");
    signal_level_location_ = gl_->get_uniform_location(program_, "uSignalLevel");
    local_siren_position_location_ = gl_->get_uniform_location(program_, "uLocalSirenPosition");
    local_siren_radius_location_ = gl_->get_uniform_location(program_, "uLocalSirenRadius");
    local_siren_strength_location_ = gl_->get_uniform_location(program_, "uLocalSirenStrength");
    splash_position_location_ = gl_->get_uniform_location(program_, "uSplashPosition");
    splash_radius_location_ = gl_->get_uniform_location(program_, "uSplashRadius");
    splash_strength_location_ = gl_->get_uniform_location(program_, "uSplashStrength");
    splash_bomb_location_ = gl_->get_uniform_location(program_, "uSplashBomb");
    light_position_location_ = gl_->get_uniform_location(program_, "uLightPosition");
    light_radius_location_ = gl_->get_uniform_location(program_, "uLightRadius");
    light_strength_location_ = gl_->get_uniform_location(program_, "uLightStrength");
    sound_position_location_ = gl_->get_uniform_location(program_, "uSoundPosition");
    sound_radius_location_ = gl_->get_uniform_location(program_, "uSoundRadius");
    sound_strength_location_ = gl_->get_uniform_location(program_, "uSoundStrength");
    void_position_location_ = gl_->get_uniform_location(program_, "uVoidPosition");
    void_radius_location_ = gl_->get_uniform_location(program_, "uVoidRadius");
    void_strength_location_ = gl_->get_uniform_location(program_, "uVoidStrength");
    preview_clip_location_ = gl_->get_uniform_location(program_, "uPreviewClip");
    preview_viewer_location_ = gl_->get_uniform_location(program_, "uPreviewViewer");
    preview_center_location_ = gl_->get_uniform_location(program_, "uPreviewCenter");
    preview_normal_location_ = gl_->get_uniform_location(program_, "uPreviewNormal");
    preview_half_width_location_ = gl_->get_uniform_location(program_, "uPreviewHalfWidth");
    preview_bottom_location_ = gl_->get_uniform_location(program_, "uPreviewBottom");
    preview_top_location_ = gl_->get_uniform_location(program_, "uPreviewTop");
    preview_strength_location_ = gl_->get_uniform_location(program_, "uPreviewStrength");
    authored_light_count_location_ = gl_->get_uniform_location(program_, "uAuthoredLightCount");
    for (std::size_t index = 0U; index < lighting::kMaxEvaluatedLocalLights; ++index) {
        const std::string suffix = "[" + std::to_string(index) + "]";
        authored_light_position_locations_[index] = gl_->get_uniform_location(
            program_, ("uAuthoredLightPositions" + suffix).c_str());
        authored_light_color_locations_[index] = gl_->get_uniform_location(
            program_, ("uAuthoredLightColors" + suffix).c_str());
        authored_light_radius_locations_[index] = gl_->get_uniform_location(
            program_, ("uAuthoredLightRadii" + suffix).c_str());
        authored_light_strength_locations_[index] = gl_->get_uniform_location(
            program_, ("uAuthoredLightStrengths" + suffix).c_str());
    }
    authored_global_color_location_ = gl_->get_uniform_location(program_, "uAuthoredGlobalColor");
    authored_global_strength_location_ = gl_->get_uniform_location(program_, "uAuthoredGlobalStrength");
    authored_point_size_boost_location_ = gl_->get_uniform_location(program_, "uAuthoredPointSizeBoost");
    authored_visibility_floor_location_ = gl_->get_uniform_location(program_, "uAuthoredVisibilityFloor");
    render_class_location_ = gl_->get_uniform_location(program_, "uRenderClass");
    for (std::size_t index = 0U; index < 3U; ++index) {
        const std::string suffix = "[" + std::to_string(index) + "]";
        material_enabled_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialEnabled" + suffix).c_str());
        material_source_color_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialSourceColors" + suffix).c_str());
        material_accent_color_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialAccentColors" + suffix).c_str());
        material_detail_color_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialDetailColors" + suffix).c_str());
        material_jg_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialJG" + suffix).c_str());
        material_jl_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialJL" + suffix).c_str());
        material_jc_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialJC" + suffix).c_str());
        material_js_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialJS" + suffix).c_str());
        material_jitter_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialJitter" + suffix).c_str());
        material_variation_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialVariation" + suffix).c_str());
        material_opacity_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialOpacity" + suffix).c_str());
        material_seed_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialSeed" + suffix).c_str());
        material_pattern_mode_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialPatternMode" + suffix).c_str());
        material_primary_spacing_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialPrimarySpacing" + suffix).c_str());
        material_secondary_spacing_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialSecondarySpacing" + suffix).c_str());
        material_breakup_scale_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialBreakupScale" + suffix).c_str());
        material_breakup_strength_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialBreakupStrength" + suffix).c_str());
        material_displacement_weight_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialDisplacementWeight" + suffix).c_str());
        material_color_weight_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialColorWeight" + suffix).c_str());
        material_line_width_locations_[index] = gl_->get_uniform_location(program_, ("uMaterialLineWidth" + suffix).c_str());
        for (std::size_t layer = 0U; layer < materials::kDefinitionLayerCount; ++layer) {
            const std::size_t flat = index * materials::kDefinitionLayerCount + layer;
            const std::string layer_suffix = "[" + std::to_string(flat) + "]";
            material_definition_layer_locations_[flat] = gl_->get_uniform_location(
                program_, ("uMaterialDefinitionLayers" + layer_suffix).c_str());
        }
    }
    sound_band_location_ = gl_->get_uniform_location(program_, "uSoundBand");
    sound_seed_location_ = gl_->get_uniform_location(program_, "uSoundSeed");
    sound_obstruction_location_ = gl_->get_uniform_location(program_, "uSoundObstruction");
    sound_wave_count_location_ = gl_->get_uniform_location(program_, "uSoundWaveCount");
    sound_wave_sharpness_location_ = gl_->get_uniform_location(program_, "uSoundWaveSharpness");
    sound_displacement_scale_location_ = gl_->get_uniform_location(program_, "uSoundDisplacementScale");
    sound_color_mix_location_ = gl_->get_uniform_location(program_, "uSoundColorMix");
    sound_visibility_floor_location_ = gl_->get_uniform_location(program_, "uSoundVisibilityFloor");

    timer_query_available_ = gl_->gen_queries && gl_->delete_queries && gl_->begin_query &&
        gl_->end_query && gl_->get_query_object_iv && gl_->get_query_object_ui64v;
    if (timer_query_available_) gl_->gen_queries(static_cast<GLsizei>(timer_queries_.size()), timer_queries_.data());

    gl_->enable(GL_DEPTH_TEST);
    gl_->depth_func(GL_LEQUAL);
    gl_->enable(GL_BLEND);
    gl_->blend_func(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    gl_->enable(GL_PROGRAM_POINT_SIZE);
    return upload_points(points, error);
}

bool PointRenderer::upload_dynamic_points(const std::vector<PointGpu>& points, std::string* error) {
    if (gl_ == nullptr || dynamic_vbo_ == 0U) {
        if (error != nullptr) *error = "Dynamic point renderer has not been initialized.";
        return false;
    }
    gl_->bind_vertex_array(dynamic_vao_);
    gl_->bind_buffer(GL_ARRAY_BUFFER, dynamic_vbo_);
    if (points.empty()) {
        dynamic_count_ = 0;
        return true;
    }
    gl_->buffer_data(GL_ARRAY_BUFFER,
                     static_cast<GLsizeiptr>(points.size() * sizeof(PointGpu)),
                     points.data(), GL_DYNAMIC_DRAW);
    dynamic_count_ = static_cast<GLsizei>(points.size());
    return true;
}

bool PointRenderer::upload_viewmodel_points(const std::vector<PointGpu>& points, std::string* error) {
    if (gl_ == nullptr || viewmodel_vbo_ == 0U) {
        if (error != nullptr) *error = "Viewmodel point renderer has not been initialized.";
        return false;
    }
    gl_->bind_vertex_array(viewmodel_vao_);
    gl_->bind_buffer(GL_ARRAY_BUFFER, viewmodel_vbo_);
    if (points.empty()) {
        viewmodel_count_ = 0;
        return true;
    }
    gl_->buffer_data(GL_ARRAY_BUFFER,
                     static_cast<GLsizeiptr>(points.size() * sizeof(PointGpu)),
                     points.data(), GL_DYNAMIC_DRAW);
    viewmodel_count_ = static_cast<GLsizei>(points.size());
    return true;
}

bool PointRenderer::upload_cloud(const PointCloud& cloud, std::string* error) {
    return upload_points(cloud.points(), error);
}

bool PointRenderer::upload_points(const std::vector<PointGpu>& points, std::string* error) {
    if (gl_ == nullptr || vbo_ == 0) {
        if (error != nullptr) *error = "Point renderer has not been initialized.";
        return false;
    }
    if (points.empty()) {
        if (error != nullptr) *error = "Cannot upload an empty point cloud.";
        return false;
    }
    gl_->bind_vertex_array(vao_);
    gl_->bind_buffer(GL_ARRAY_BUFFER, vbo_);
    gl_->buffer_data(GL_ARRAY_BUFFER,
                     static_cast<GLsizeiptr>(points.size() * sizeof(PointGpu)),
                     points.data(), GL_DYNAMIC_DRAW);
    allocated_count_ = points.size();
    draw_ranges_.clear();
    draw_ranges_.push_back({0U, allocated_count_});
    submitted_count_ = allocated_count_;
    return true;
}

void PointRenderer::set_draw_count(std::size_t count) noexcept {
    const std::size_t safe = std::min(count, allocated_count_);
    draw_ranges_.clear();
    if (safe > 0U) draw_ranges_.push_back({0U, safe});
    submitted_count_ = safe;
}

void PointRenderer::set_draw_ranges(const std::vector<DrawRange>& ranges) noexcept {
    draw_ranges_.clear();
    submitted_count_ = 0U;
    for (const auto& range : ranges) {
        if (range.first >= allocated_count_ || range.count == 0U) continue;
        const std::size_t count = std::min(range.count, allocated_count_ - range.first);
        draw_ranges_.push_back({range.first, count});
        submitted_count_ += count;
    }
}

void PointRenderer::set_tactical_marker(math::Vec3 position) noexcept {
    marker_position_ = position;
    if (gl_ == nullptr || marker_vbo_ == 0U) return;
    std::vector<PointGpu> points;
    points.reserve(25U);
    auto add = [&](float x, float y, float z, float radius, float r, float g, float b) {
        points.push_back({{x, y, z}, radius, {r, g, b, 1.0F}, {0.0F, 1.0F, 0.0F}, 1.0F});
    };
    const float y = position.y + 6.5F;
    add(position.x, y, position.z, 0.34F, 1.0F, 0.24F, 0.82F);
    for (int i = 0; i < 8; ++i) {
        const float angle = static_cast<float>(i) * 0.78539816339F;
        add(position.x + std::cos(angle) * 1.25F, y,
            position.z + std::sin(angle) * 1.25F, 0.24F, 1.0F, 0.72F, 0.96F);
    }
    for (int i = 0; i < 8; ++i) {
        add(position.x, position.y + static_cast<float>(i) * 0.72F,
            position.z, 0.22F, 1.0F, 0.30F, 0.80F);
    }
    gl_->bind_buffer(GL_ARRAY_BUFFER, marker_vbo_);
    gl_->buffer_data(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(points.size() * sizeof(PointGpu)),
                     points.data(), GL_DYNAMIC_DRAW);
    marker_count_ = static_cast<GLsizei>(points.size());
}

void PointRenderer::poll_timer_query() {
    if (!timer_query_available_) return;
    for (std::size_t i = 0; i < timer_queries_.size(); ++i) {
        if (!timer_pending_[i]) continue;
        GLint available = 0;
        gl_->get_query_object_iv(timer_queries_[i], GL_QUERY_RESULT_AVAILABLE, &available);
        if (available == 0) continue;
        GLuint64 nanoseconds = 0;
        gl_->get_query_object_ui64v(timer_queries_[i], GL_QUERY_RESULT, &nanoseconds);
        last_gpu_ms_ = static_cast<double>(nanoseconds) / 1'000'000.0;
        timer_pending_[i] = false;
    }
}

void PointRenderer::render(const math::Mat4& view_projection, float time_seconds, float action_pulse,
                           bool scanner_mode, bool tactical_mode, float point_scale,
                           float density_scale, float signal_level,
                           math::Vec3 local_siren_position, float local_siren_radius,
                           float local_siren_strength,
                           math::Vec3 splash_position, float splash_radius,
                           float splash_strength, bool splash_bomb,
                           math::Vec3 light_position, float light_radius, float light_strength,
                           math::Vec3 sound_position, float sound_radius, float sound_strength,
                           math::Vec3 void_position, float void_radius, float void_strength,
                           int viewport_width, int viewport_height) {
    if (gl_ == nullptr || program_ == 0) return;
    poll_timer_query();
    gl_->viewport(0, 0, viewport_width, viewport_height);
    if (tactical_mode) gl_->clear_color(0.008F, 0.020F, 0.030F, 1.0F);
    else {
        const float dim = std::clamp(signal_level, 0.0F, 1.0F);
        const float global = std::clamp(illuminosity_frame_.global_strength, 0.0F, 1.0F);
        gl_->clear_color((0.012F + 0.023F * dim) * (0.72F + illuminosity_frame_.global_color.x * global * 0.18F),
                         (0.010F + 0.020F * dim) * (0.72F + illuminosity_frame_.global_color.y * global * 0.18F),
                         (0.007F + 0.011F * dim) * (0.72F + illuminosity_frame_.global_color.z * global * 0.18F), 1.0F);
    }
    gl_->clear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    gl_->use_program(program_);
    gl_->uniform_matrix4fv(matrix_location_, 1, GL_FALSE, view_projection.data());
    gl_->uniform1f(time_location_, time_seconds);
    gl_->uniform1f(pulse_location_, action_pulse);
    gl_->uniform1f(point_scale_location_, point_scale);
    gl_->uniform1f(density_scale_location_, density_scale);
    gl_->uniform1f(signal_level_location_, signal_level);
    gl_->uniform3f(local_siren_position_location_, local_siren_position.x, local_siren_position.y, local_siren_position.z);
    gl_->uniform1f(local_siren_radius_location_, local_siren_radius);
    gl_->uniform1f(local_siren_strength_location_, local_siren_strength);
    gl_->uniform3f(splash_position_location_, splash_position.x, splash_position.y, splash_position.z);
    gl_->uniform1f(splash_radius_location_, splash_radius);
    gl_->uniform1f(splash_strength_location_, splash_strength);
    gl_->uniform1i(splash_bomb_location_, splash_bomb ? 1 : 0);
    gl_->uniform3f(light_position_location_, light_position.x, light_position.y, light_position.z);
    gl_->uniform1f(light_radius_location_, light_radius);
    gl_->uniform1f(light_strength_location_, light_strength);
    gl_->uniform1i(authored_light_count_location_, static_cast<int>(illuminosity_frame_.local_light_count));
    for (std::size_t index = 0U; index < lighting::kMaxEvaluatedLocalLights; ++index) {
        const auto& contribution = illuminosity_frame_.local_lights[index];
        gl_->uniform3f(authored_light_position_locations_[index], contribution.position.x,
                       contribution.position.y, contribution.position.z);
        gl_->uniform3f(authored_light_color_locations_[index], contribution.color.x,
                       contribution.color.y, contribution.color.z);
        gl_->uniform1f(authored_light_radius_locations_[index], contribution.radius);
        gl_->uniform1f(authored_light_strength_locations_[index], contribution.strength);
    }
    gl_->uniform3f(authored_global_color_location_, illuminosity_frame_.global_color.x,
                   illuminosity_frame_.global_color.y, illuminosity_frame_.global_color.z);
    gl_->uniform1f(authored_global_strength_location_, illuminosity_frame_.global_strength);
    gl_->uniform1f(authored_point_size_boost_location_, illuminosity_frame_.point_size_boost);
    gl_->uniform1f(authored_visibility_floor_location_, illuminosity_frame_.visibility_floor);
    for (std::size_t index = 0U; index < material_frame_.surfaces.size(); ++index) {
        const auto& material = material_frame_.surfaces[index];
        gl_->uniform1i(material_enabled_locations_[index], material.enabled ? 1 : 0);
        gl_->uniform3f(material_source_color_locations_[index], material.source_color.x, material.source_color.y, material.source_color.z);
        gl_->uniform3f(material_accent_color_locations_[index], material.accent_color.x, material.accent_color.y, material.accent_color.z);
        gl_->uniform3f(material_detail_color_locations_[index], material.detail_color.x, material.detail_color.y, material.detail_color.z);
        gl_->uniform1f(material_jg_locations_[index], material.jG);
        gl_->uniform1f(material_jl_locations_[index], material.jL);
        gl_->uniform1f(material_jc_locations_[index], material.jC);
        gl_->uniform1f(material_js_locations_[index], material.jS);
        gl_->uniform1f(material_jitter_locations_[index], material.jitter_amplitude);
        gl_->uniform1f(material_variation_locations_[index], material.variation);
        gl_->uniform1f(material_opacity_locations_[index], material.opacity);
        gl_->uniform1f(material_seed_locations_[index], static_cast<float>(material.seed));
        gl_->uniform1i(material_pattern_mode_locations_[index], static_cast<int>(material.pattern_mode));
        gl_->uniform1f(material_primary_spacing_locations_[index], material.primary_spacing);
        gl_->uniform1f(material_secondary_spacing_locations_[index], material.secondary_spacing);
        gl_->uniform1f(material_breakup_scale_locations_[index], material.breakup_scale);
        gl_->uniform1f(material_breakup_strength_locations_[index], material.breakup_strength);
        gl_->uniform1f(material_displacement_weight_locations_[index], material.displacement_weight);
        gl_->uniform1f(material_color_weight_locations_[index], material.color_weight);
        gl_->uniform1f(material_line_width_locations_[index], material.line_width);
        for (std::size_t layer = 0U; layer < materials::kDefinitionLayerCount; ++layer) {
            const std::size_t flat = index * materials::kDefinitionLayerCount + layer;
            gl_->uniform1f(material_definition_layer_locations_[flat], material.definition_opacity[layer]);
        }
    }
    gl_->uniform3f(sound_position_location_, sound_position.x, sound_position.y, sound_position.z);
    gl_->uniform1f(sound_radius_location_, sound_radius);
    gl_->uniform1f(sound_strength_location_, sound_strength);
    gl_->uniform1i(sound_band_location_, static_cast<int>(audio_band_));
    gl_->uniform1f(sound_seed_location_, static_cast<float>(audio_seed_));
    gl_->uniform1f(sound_obstruction_location_, audio_obstruction_path_);
    gl_->uniform1i(sound_wave_count_location_, static_cast<int>(audio_wave_count_));
    gl_->uniform1f(sound_wave_sharpness_location_, audio_wave_sharpness_);
    gl_->uniform1f(sound_displacement_scale_location_, audio_displacement_scale_);
    gl_->uniform1f(sound_color_mix_location_, audio_color_mix_);
    gl_->uniform1f(sound_visibility_floor_location_, audio_visibility_floor_);
    gl_->uniform3f(void_position_location_, void_position.x, void_position.y, void_position.z);
    gl_->uniform1f(void_radius_location_, void_radius);
    gl_->uniform1f(void_strength_location_, void_strength);
    gl_->uniform1i(scanner_location_, scanner_mode ? 1 : 0);
    gl_->uniform1i(tactical_location_, tactical_mode ? 1 : 0);
    gl_->uniform1i(render_class_location_, 0);
    gl_->bind_vertex_array(vao_);

    bool timing_this_frame = false;
    const std::size_t query_index = timer_write_index_;
    if (timer_query_available_ && !timer_pending_[query_index]) {
        gl_->begin_query(GL_TIME_ELAPSED, timer_queries_[query_index]);
        timing_this_frame = true;
    }
    for (const auto& range : draw_ranges_) {
        gl_->uniform1i(preview_clip_location_, range.aperture.enabled ? 1 : 0);
        gl_->uniform1f(preview_strength_location_, range.aperture.enabled ? range.aperture.strength : 0.0F);
        if (range.aperture.enabled) {
            gl_->uniform3f(preview_viewer_location_, range.aperture.viewer_position.x,
                           range.aperture.viewer_position.y, range.aperture.viewer_position.z);
            gl_->uniform3f(preview_center_location_, range.aperture.opening_center.x,
                           range.aperture.opening_center.y, range.aperture.opening_center.z);
            gl_->uniform3f(preview_normal_location_, range.aperture.opening_normal.x,
                           range.aperture.opening_normal.y, range.aperture.opening_normal.z);
            gl_->uniform1f(preview_half_width_location_, range.aperture.half_width);
            gl_->uniform1f(preview_bottom_location_, range.aperture.bottom_y);
            gl_->uniform1f(preview_top_location_, range.aperture.top_y);
        }
        gl_->draw_arrays(GL_POINTS, static_cast<GLint>(range.first), static_cast<GLsizei>(range.count));
    }
    gl_->uniform1i(preview_clip_location_, 0);
    gl_->uniform1f(preview_strength_location_, 0.0F);
    if (dynamic_count_ > 0) {
        gl_->uniform1i(render_class_location_, tactical_mode ? 2 : 1);
        gl_->uniform1f(void_strength_location_, 0.0F);
        gl_->bind_vertex_array(dynamic_vao_);
        gl_->draw_arrays(GL_POINTS, 0, dynamic_count_);
        gl_->uniform1f(void_strength_location_, void_strength);
        gl_->uniform1i(render_class_location_, 0);
        gl_->bind_vertex_array(vao_);
    }
    if (!tactical_mode && viewmodel_count_ > 0) {
        gl_->clear(GL_DEPTH_BUFFER_BIT);
        gl_->uniform1i(render_class_location_, 2);
        gl_->uniform1f(void_strength_location_, 0.0F);
        gl_->uniform1f(signal_level_location_, 1.0F);
        gl_->bind_vertex_array(viewmodel_vao_);
        gl_->draw_arrays(GL_POINTS, 0, viewmodel_count_);
        gl_->uniform1f(signal_level_location_, signal_level);
        gl_->uniform1f(void_strength_location_, void_strength);
        gl_->uniform1i(render_class_location_, 0);
        gl_->bind_vertex_array(vao_);
    }
    if (tactical_mode && marker_count_ > 0) {
        gl_->uniform1i(render_class_location_, 2);
        gl_->bind_vertex_array(marker_vao_);
        gl_->draw_arrays(GL_POINTS, 0, marker_count_);
        gl_->uniform1i(render_class_location_, 0);
        gl_->bind_vertex_array(vao_);
    }
    if (timing_this_frame) {
        gl_->end_query(GL_TIME_ELAPSED);
        timer_pending_[query_index] = true;
        timer_write_index_ = (timer_write_index_ + 1U) % timer_queries_.size();
    }
}

void PointRenderer::shutdown() {
    if (gl_ != nullptr) {
        if (timer_query_available_) gl_->delete_queries(static_cast<GLsizei>(timer_queries_.size()), timer_queries_.data());
        if (viewmodel_vbo_ != 0) gl_->delete_buffers(1, &viewmodel_vbo_);
        if (viewmodel_vao_ != 0) gl_->delete_vertex_arrays(1, &viewmodel_vao_);
        if (dynamic_vbo_ != 0) gl_->delete_buffers(1, &dynamic_vbo_);
        if (dynamic_vao_ != 0) gl_->delete_vertex_arrays(1, &dynamic_vao_);
        if (marker_vbo_ != 0) gl_->delete_buffers(1, &marker_vbo_);
        if (marker_vao_ != 0) gl_->delete_vertex_arrays(1, &marker_vao_);
        if (vbo_ != 0) gl_->delete_buffers(1, &vbo_);
        if (vao_ != 0) gl_->delete_vertex_arrays(1, &vao_);
        if (program_ != 0) gl_->delete_program(program_);
    }
    timer_queries_.fill(0);
    timer_pending_.fill(false);
    viewmodel_vbo_ = 0;
    viewmodel_vao_ = 0;
    viewmodel_count_ = 0;
    dynamic_vbo_ = 0;
    dynamic_vao_ = 0;
    dynamic_count_ = 0;
    marker_vbo_ = 0;
    marker_vao_ = 0;
    marker_count_ = 0;
    vbo_ = 0;
    vao_ = 0;
    program_ = 0;
    allocated_count_ = 0;
    submitted_count_ = 0;
    draw_ranges_.clear();
    last_gpu_ms_ = 0.0;
    timer_query_available_ = false;
    gl_ = nullptr;
}

}  // namespace signalcloud::render
