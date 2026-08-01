#include "engine/input/input_profile.hpp"

#include <algorithm>
#include <set>

namespace signalcloud::input {

InputProfile InputProfile::solo_paw_defaults() {
    InputProfile profile;
    profile.actions_ = {
        {"look", "First-person camera look", {{"mouse", "motion"}, {"controller", "right_stick"}}},
        {"move_forward", "Move forward", {{"keyboard", "W"}, {"controller", "left_stick_up"}}},
        {"move_backward", "Move backward", {{"keyboard", "S"}, {"controller", "left_stick_down"}}},
        {"move_left", "Strafe left", {{"keyboard", "A"}, {"controller", "left_stick_left"}}},
        {"move_right", "Strafe right", {{"keyboard", "D"}, {"controller", "left_stick_right"}}},
        {"jump", "Grounded jump", {{"keyboard", "Space"}, {"controller", "A"}}},
        {"primary", "Use, shoot, attack, or sustained tool", {{"mouse", "left"}, {"keyboard", "J"}, {"controller", "right_trigger"}}},
        {"quick_action", "Evade or contextual quick action", {{"mouse", "right"}, {"keyboard", "K"}, {"controller", "B"}}},
        {"next_weapon", "Cycle weapon", {{"mouse", "wheel_up"}, {"keyboard", "E"}, {"controller", "dpad_up"}}},
        {"next_belt", "Cycle belt slot", {{"mouse", "wheel_down"}, {"keyboard", "Q"}, {"controller", "dpad_down"}}},
        {"interact", "Interact or pick up", {{"mouse", "extra_button_1"}, {"keyboard", "F"}, {"controller", "X"}}},
        {"reload", "Reload active weapon", {{"mouse", "extra_button_2"}, {"keyboard", "R"}, {"controller", "Y"}}},
        {"scanner", "Scanner or flashlight mode", {{"mouse", "extra_button_3"}, {"keyboard", "C"}, {"controller", "left_bumper"}}},
        {"belt_activate", "Activate highlighted belt item", {{"mouse", "extra_button_4"}, {"keyboard", "V"}, {"controller", "right_bumper"}}},
        {"sabs", "Open SABS maps and communications", {{"mouse", "extra_button_5"}, {"keyboard", "Tab"}, {"controller", "back"}}},
        {"squad_ping", "Squad ping, companion order, or build action", {{"mouse", "extra_button_6"}, {"keyboard", "G"}, {"controller", "left_stick_click"}}},
        {"capture_mouse", "Capture or release first-person mouse", {{"keyboard", "F1"}}},
        {"probe_buttons", "Toggle raw mouse-button discovery", {{"keyboard", "F2"}}},
        {"tactical_map", "Toggle compact persistent tactical-memory map", {{"keyboard", "F3"}}},
        {"quit", "Exit the test application", {{"keyboard", "F10"}}}
    };
    return profile;
}

std::vector<std::string> InputProfile::validate() const {
    std::vector<std::string> issues;
    std::set<std::string> ids;
    for (const Action& action : actions_) {
        if (action.id.empty()) issues.emplace_back("Input action has an empty ID.");
        if (!ids.insert(action.id).second) issues.emplace_back("Duplicate action ID: " + action.id);
        if (action.bindings.empty()) issues.emplace_back("Action has no bindings: " + action.id);
    }
    constexpr const char* required[] = {"look", "move_forward", "move_backward", "move_left",
        "move_right", "jump", "primary", "quick_action", "next_weapon", "next_belt",
        "interact", "reload", "scanner", "belt_activate", "sabs", "squad_ping"};
    for (const char* id : required) {
        if (find(id) == nullptr) issues.emplace_back(std::string("Required action missing: ") + id);
    }
    return issues;
}

const Action* InputProfile::find(const std::string& id) const noexcept {
    const auto found = std::find_if(actions_.begin(), actions_.end(), [&](const Action& action) {
        return action.id == id;
    });
    return found == actions_.end() ? nullptr : &*found;
}

}  // namespace signalcloud::input
