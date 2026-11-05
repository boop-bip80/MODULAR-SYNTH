/*
 * Test-only stand-in for the SMALL Rack surface used by the nine original
 * modules. This is not the Rack SDK and must never be shipped with a plugin.
 * A passing smoke test proves compilation/process flow against these types,
 * not Cardinal/Rack ABI compatibility or a runnable plugin.
 */
#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <initializer_list>
#include <memory>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>

// Macro8's serializer invokes a small Jansson-like set of operations.
// They are deliberately in-memory test doubles with no wire-format promises.
using json_int_t = long long;
struct json_t {
    enum class Kind { Object, Array, String, Integer, Real, Null } kind;
    std::unordered_map<std::string, std::unique_ptr<json_t>> fields;
    std::vector<std::unique_ptr<json_t>> elements;
    std::string text;
    double number = 0.0;
    explicit json_t(Kind type) : kind(type) {}
};

inline json_t* json_object() { return new json_t(json_t::Kind::Object); }
inline json_t* json_array() { return new json_t(json_t::Kind::Array); }
inline json_t* json_null() { return new json_t(json_t::Kind::Null); }
inline json_t* json_real(double value) {
    auto* node = new json_t(json_t::Kind::Real);
    node->number = value;
    return node;
}
inline json_t* json_integer(json_int_t value) {
    auto* node = new json_t(json_t::Kind::Integer);
    node->number = static_cast<double>(value);
    return node;
}
inline json_t* json_string(const char* value) {
    auto* node = new json_t(json_t::Kind::String);
    node->text = value ? value : "";
    return node;
}
inline int json_object_set_new(json_t* object, const char* key, json_t* value) {
    if (!object || object->kind != json_t::Kind::Object || !key || !value)
        return -1;
    object->fields[key].reset(value);
    return 0;
}
inline json_t* json_object_get(const json_t* object, const char* key) {
    if (!object || object->kind != json_t::Kind::Object || !key)
        return nullptr;
    const auto found = object->fields.find(key);
    return found == object->fields.end() ? nullptr : found->second.get();
}
inline int json_array_append_new(json_t* array, json_t* value) {
    if (!array || array->kind != json_t::Kind::Array || !value)
        return -1;
    array->elements.emplace_back(value);
    return 0;
}
inline json_t* json_array_get(const json_t* array, std::size_t index) {
    if (!array || array->kind != json_t::Kind::Array || index >= array->elements.size())
        return nullptr;
    return array->elements[index].get();
}
inline std::size_t json_array_size(const json_t* array) {
    return array && array->kind == json_t::Kind::Array ? array->elements.size() : 0;
}
inline bool json_is_object(const json_t* node) { return node && node->kind == json_t::Kind::Object; }
inline bool json_is_array(const json_t* node) { return node && node->kind == json_t::Kind::Array; }
inline bool json_is_string(const json_t* node) { return node && node->kind == json_t::Kind::String; }
inline bool json_is_integer(const json_t* node) { return node && node->kind == json_t::Kind::Integer; }
inline bool json_is_number(const json_t* node) {
    return node && (node->kind == json_t::Kind::Real || node->kind == json_t::Kind::Integer);
}
inline json_int_t json_integer_value(const json_t* node) {
    return json_is_integer(node) ? static_cast<json_int_t>(node->number) : 0;
}
inline double json_number_value(const json_t* node) { return json_is_number(node) ? node->number : 0.0; }
inline const char* json_string_value(const json_t* node) { return json_is_string(node) ? node->text.c_str() : nullptr; }

namespace rack {

struct ProcessArgs {
    double sampleRate = 48000.0;
    double sampleTime = 1.0 / 48000.0;
};
struct ResetEvent {};

struct Param {
    float value = 0.0f;
    float getValue() const { return value; }
    void setValue(float v) { value = v; }
};
struct ParamQuantity { bool snapEnabled = false; };

struct Port {
    int channels = 0;
    bool connected = false;
    std::array<float, 16> values{};
    int getChannels() const { return connected ? channels : 0; }
    bool isConnected() const { return connected; }
    // Keep the test double usable with Cardinal's production GNU C++11 mode.
    void setChannels(int n) { channels = std::min(16, std::max(0, n)); connected = true; }
    void setVoltage(float value, int channel = 0) {
        if (channel >= 0 && channel < 16)
            values[static_cast<std::size_t>(channel)] = value;
    }
    float getVoltage(int channel = 0) const {
        if (channel < 0 || channel >= 16 || !connected || channels <= 0)
            return 0.0f;
        return values[static_cast<std::size_t>(channel < channels ? channel : 0)];
    }
    float getNormalPolyVoltage(float normal, int channel) const {
        return connected && channels > 0 ? getVoltage(channel) : normal;
    }
};
struct Light {
    float brightness = 0.0f;
    void setBrightness(float value) { brightness = value; }
};

struct Module {
    std::vector<Param> params;
    std::vector<ParamQuantity> paramQuantities;
    std::vector<Port> inputs;
    std::vector<Port> outputs;
    std::vector<Light> lights;
    virtual ~Module() = default;
    void config(int nParams, int nInputs, int nOutputs, int nLights) {
        params.resize(nParams);
        paramQuantities.resize(nParams);
        inputs.resize(nInputs);
        outputs.resize(nOutputs);
        lights.resize(nLights);
    }
    void configParam(int id, float, float, float initial, const std::string&,
                     const std::string& = "", float = 0.0f, float = 1.0f) {
        params.at(static_cast<std::size_t>(id)).value = initial;
    }
    void configSwitch(int id, float minValue, float maxValue, float initial,
                      const std::string& label, std::initializer_list<std::string>) {
        configParam(id, minValue, maxValue, initial, label);
    }
    void configButton(int id, const std::string& name) { configParam(id, 0, 1, 0, name); }
    void configInput(int, const std::string&) {}
    void configOutput(int, const std::string&) {}
    void configLight(int, const std::string&) {}
    ParamQuantity* getParamQuantity(int id) { return &paramQuantities.at(static_cast<std::size_t>(id)); }
    virtual void onReset() {}
    virtual void onReset(const ResetEvent&) { onReset(); }
    virtual void process(const ProcessArgs&) = 0;
    virtual json_t* dataToJson() { return nullptr; }
    virtual void dataFromJson(json_t*) {}
};

struct ModuleWidget {
    Module* module = nullptr;
    virtual ~ModuleWidget() = default;
    void setModule(Module* m) { module = m; }
};
struct Plugin {};
struct Model {};
template <class M, class W> Model* createModel(const char*) {
    static_assert(std::is_base_of<Module, M>::value, "Expected Rack module");
    static_assert(std::is_base_of<ModuleWidget, W>::value, "Expected Rack widget");
    static Model model;
    return &model;
}
namespace dsp {
struct SchmittTrigger {
    bool high = false;
    void reset() { high = false; }
    bool process(float value) {
        if (high) {
            if (value <= 0.1f) high = false;
            return false;
        }
        if (value >= 1.0f) { high = true; return true; }
        return false;
    }
};
}
} // namespace rack
