#pragma once

#include "engine/ui/ar_interface.hpp"
#include "engine/scfont/scfont.hpp"
#include "engine/ui/scui_panel.hpp"

#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace signalcloud::ui {

enum class ScuiNativeNoticeKind { success, info, warning, failure };

enum class ScuiNativeKey {
    focus_previous,
    focus_next,
    adjust_previous,
    adjust_next,
    confirm,
    cancel,
    page_previous,
    page_next,
};

struct ScuiNativeRuntimeStats {
    std::size_t page_count{0};
    std::size_t current_page{0};
    std::size_t focusable_controls{0};
    std::size_t generated_points{0};
    std::size_t backplate_points{0};
    std::size_t wrapped_text_lines{0};
    std::size_t notice_points{0};
    std::size_t dispatched_events{0};
    std::size_t blocked_commands{0};
};

class ScuiNativeRuntime {
public:
    explicit ScuiNativeRuntime(ScuiPanel panel, std::size_t rows_per_page = 4U);

    void set_font(std::shared_ptr<const font::Font> font) noexcept { font_ = std::move(font); }
    [[nodiscard]] std::shared_ptr<const font::Font> font_snapshot() const noexcept { return font_; }
    [[nodiscard]] bool external_font_active() const noexcept { return static_cast<bool>(font_); }

    [[nodiscard]] bool valid() const noexcept { return panel_.valid(); }
    [[nodiscard]] bool open() const noexcept { return open_; }
    [[nodiscard]] const ScuiPanel& panel() const noexcept { return panel_; }
    [[nodiscard]] const ScuiNativeLayout& layout() const noexcept { return layout_; }
    [[nodiscard]] std::size_t current_page() const noexcept { return current_page_; }
    [[nodiscard]] std::string_view focused_control_id() const noexcept;
    [[nodiscard]] ScuiNativeRuntimeStats stats() const noexcept;

    void set_open(bool open) noexcept;
    void toggle_open() noexcept { set_open(!open_); }

    bool register_command(std::string command_id);
    [[nodiscard]] bool command_allowed(std::string_view command_id) const noexcept;

    bool handle_key(ScuiNativeKey key);
    bool handle_pointer_move(float normalized_x, float normalized_y) noexcept;
    bool handle_pointer_activate(float normalized_x, float normalized_y);
    bool handle_wheel(float delta);

    bool set_number(std::string_view binding, double value);
    bool set_boolean(std::string_view binding, bool value);
    bool set_string(std::string_view binding, std::string value);
    bool set_choices(std::string_view control_id, std::vector<std::string> choices,
                     std::optional<std::string> selected = std::nullopt);
    void show_notice(ScuiNativeNoticeKind kind, std::string message,
                     float current_time_seconds, float duration_seconds = 1.8F);
    void clear_notice() noexcept;

    [[nodiscard]] std::optional<double> number(std::string_view binding) const noexcept;
    [[nodiscard]] std::optional<bool> boolean(std::string_view binding) const noexcept;
    [[nodiscard]] std::optional<std::string> string(std::string_view binding) const;
    [[nodiscard]] std::string display_value(const ScuiControl& control) const;
    [[nodiscard]] std::map<std::string, std::string, std::less<>> state_json() const;
    void apply_state_json(const std::map<std::string, std::string, std::less<>>& values);

    [[nodiscard]] std::vector<render::PointGpu> build_points(
        float time_seconds, const ArPose& pose) const;
    [[nodiscard]] std::vector<ScuiPanelEvent> take_events();

private:
    using Value = std::variant<std::monostate, bool, double, std::string>;

    [[nodiscard]] const ScuiControl* focused_control() const noexcept;
    [[nodiscard]] const ScuiNativeRow* row_for_control(std::string_view control_id) const noexcept;
    [[nodiscard]] const ScuiNativeRow* row_at_pointer(float normalized_y) const noexcept;
    [[nodiscard]] std::optional<std::size_t> focus_index_for(std::string_view control_id) const noexcept;
    [[nodiscard]] Value value_for_binding(std::string_view binding) const;
    [[nodiscard]] static Value parse_value(std::string_view raw);

    bool move_focus(int direction);
    bool move_page(int direction);
    bool focus_control(std::string_view control_id);
    bool activate_control(const ScuiControl& control, int direction, bool pointer_activation,
                          std::optional<float> normalized_x = std::nullopt);
    bool emit_event(const ScuiControl& control, std::string payload_json);
    void normalize_focus() noexcept;
    void sync_page_to_focus() noexcept;

    ScuiPanel panel_;
    std::shared_ptr<const font::Font> font_;
    ScuiNativeLayout layout_;
    ScuiNativeCommandRegistry command_registry_;
    std::map<std::string, Value, std::less<>> values_;
    std::vector<ScuiPanelEvent> events_;
    std::size_t rows_per_page_{4U};
    std::size_t current_page_{0U};
    std::size_t focus_index_{0U};
    std::uint64_t transaction_serial_{0U};
    std::size_t dispatched_events_{0U};
    std::size_t blocked_commands_{0U};
    float pointer_x_{0.5F};
    float pointer_y_{0.5F};
    bool pointer_visible_{false};
    bool open_{false};
    mutable std::size_t last_generated_points_{0U};
    mutable std::size_t last_backplate_points_{0U};
    mutable std::size_t last_wrapped_text_lines_{0U};
    mutable std::size_t last_notice_points_{0U};
    ScuiNativeNoticeKind notice_kind_{ScuiNativeNoticeKind::info};
    std::string notice_message_;
    float notice_started_seconds_{0.0F};
    float notice_duration_seconds_{0.0F};
    float notice_until_seconds_{0.0F};
};

}  // namespace signalcloud::ui
