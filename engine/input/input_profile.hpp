#pragma once

#include <string>
#include <vector>

namespace signalcloud::input {

struct Binding {
    std::string device;
    std::string control;
};

struct Action {
    std::string id;
    std::string description;
    std::vector<Binding> bindings;
};

class InputProfile {
public:
    static InputProfile solo_paw_defaults();
    [[nodiscard]] const std::vector<Action>& actions() const noexcept { return actions_; }
    [[nodiscard]] std::vector<std::string> validate() const;
    [[nodiscard]] const Action* find(const std::string& id) const noexcept;
private:
    std::vector<Action> actions_;
};

}  // namespace signalcloud::input
