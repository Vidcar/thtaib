// Allocation planning stays in the pinned llama.cpp / mtmd libraries.
// This adapter only mirrors server preprocessing and serializes their results.
#include "arg.h"
#include "planner-pin.h"
#include "common.h"
#include "fit.h"
#include "log.h"
#include "speculative.h"
#include "llama.h"
#include "llama-ext.h"
#include "mtmd.h"
#include "ggml-backend-impl.h"
#include "json.hpp"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::ordered_json;
constexpr int protocol = 1;
constexpr int supported_build = 11045;
constexpr const char * supported_commit = "2b1847030";

struct allocation {
    uint64_t weights = 0;
    uint64_t context = 0;
    uint64_t compute = 0;
    uint64_t projector = 0;
    uint64_t speculation = 0;
};

// b11045 mtmd's no_alloc skips tensor reads but still asks the backends for
// weight/compute buffers. Keep its native graph/placement calculations and
// substitute metadata-only buffers within this isolated measurement. The
// original alignment, tensor allocation size and operation support callbacks
// remain native and unchanged. No tensor evaluation or data access is allowed.
class projector_allocation_guard {
    using allocator = ggml_backend_buffer_t (*)(ggml_backend_buffer_type_t, size_t);
    std::vector<std::pair<ggml_backend_buffer_type_t, allocator>> original;

    static ggml_backend_buffer_t metadata_buffer(ggml_backend_buffer_type_t buft, size_t size) {
        ggml_backend_buffer_i iface{};
        iface.get_base = [](ggml_backend_buffer_t) -> void * {
            return reinterpret_cast<void *>(uintptr_t(0x10000000));
        };
        iface.clear = [](ggml_backend_buffer_t, uint8_t) {};
        iface.set_tensor = [](ggml_backend_buffer_t, ggml_tensor *, const void *, size_t, size_t) {
            throw std::runtime_error("The allocation preview cannot write tensor data.");
        };
        iface.get_tensor = [](ggml_backend_buffer_t, const ggml_tensor *, void *, size_t, size_t) {
            throw std::runtime_error("The allocation preview cannot read tensor data.");
        };
        return ggml_backend_buffer_init(buft, iface, nullptr, size);
    }

    void replace(ggml_backend_buffer_type_t buft) {
        if (!buft || std::any_of(original.begin(), original.end(),
                [buft](const auto & entry) { return entry.first == buft; })) {
            return;
        }
        original.emplace_back(buft, buft->iface.alloc_buffer);
        buft->iface.alloc_buffer = metadata_buffer;
    }

public:
    projector_allocation_guard() {
        for (size_t index = 0; index < ggml_backend_dev_count(); ++index) {
            const auto dev = ggml_backend_dev_get(index);
            replace(ggml_backend_dev_buffer_type(dev));
            replace(ggml_backend_dev_host_buffer_type(dev));
        }
    }

    ~projector_allocation_guard() {
        for (const auto & [buft, allocate] : original) {
            buft->iface.alloc_buffer = allocate;
        }
    }
};

static std::string device_id(ggml_backend_dev_t dev) {
    if (!dev || ggml_backend_dev_type(dev) == GGML_BACKEND_DEVICE_TYPE_CPU) {
        return "Host";
    }
    return ggml_backend_dev_name(dev);
}

static void add_breakdown(std::map<std::string, allocation> & rows,
                          llama_context * ctx, bool draft, bool shared_weights) {
    for (const auto & [buft, memory] : llama_get_memory_breakdown(ctx)) {
        const auto dev = ggml_backend_buft_is_host(buft) ? nullptr : ggml_backend_buft_get_device(buft);
        auto & row = rows[device_id(dev)];
        const auto weights = shared_weights ? 0 : memory.model;
        row.weights += weights;
        row.context += memory.context;
        row.compute += memory.compute;
        if (draft) {
            row.speculation += weights + memory.context + memory.compute;
        }
    }
}

static void server_preprocess(common_params & params) {
    // tools/server/server.cpp: non-router worker preprocessing.
    if (params.embedding && params.n_batch > params.n_ubatch) {
        params.n_batch = params.n_ubatch;
    }
    if (params.n_parallel < 0) {
        params.n_parallel = 4;
        params.kv_unified = true;
    }
    if (params.n_parallel < 1) {
        throw std::runtime_error("The server requires at least one request slot.");
    }
    if (params.kv_unified_per_slot > 0 && params.n_ctx == 0 &&
            static_cast<uint32_t>(params.fit_params_min_ctx) != UINT32_MAX) {
        const auto capacity = uint64_t(params.n_parallel) * params.kv_unified_per_slot;
        if (capacity > INT32_MAX) {
            throw std::runtime_error("The requested context pool exceeds native capacity.");
        }
        params.n_ctx = static_cast<int32_t>(capacity);
    }
    // tools/server/server-context.cpp: server_output_limits.
    if (params.embedding || (params.pooling_type != LLAMA_POOLING_TYPE_UNSPECIFIED &&
                            params.pooling_type != LLAMA_POOLING_TYPE_NONE)) {
        params.n_outputs_max = params.n_batch;
        params.n_outputs_max_per_seq = 1;
    } else {
        const auto limits = common_speculative_get_output_limits(
                params.n_batch, params.n_parallel, common_speculative_n_max(&params.speculative));
        params.n_outputs_max = std::max<int32_t>(1, limits.total);
        params.n_outputs_max_per_seq = std::max<int32_t>(1, limits.per_seq);
    }
}

static json version() {
    return {{"protocol", protocol}, {"native_build", supported_build},
            {"native_commit", supported_commit}, {"native_fingerprint", WB_NATIVE_FINGERPRINT},
            {"adapter", "workbench-memory-planner"}};
}

static json plan(common_params & params) {
    server_preprocess(params);
    // All contexts are constructed in native no_alloc mode: no tensors, KV
    // buffers or compute buffers are allocated, and no inference is executed.
    params.no_alloc = true;
    auto mparams = common_model_params_to_llama(params);
    mparams.load_mode = LLAMA_LOAD_MODE_NONE;
    auto cparams = common_context_params_to_llama(params);
    const bool has_draft = params.speculative.has_dft();
    const bool mtp = std::find(params.speculative.types.begin(), params.speculative.types.end(),
            COMMON_SPECULATIVE_TYPE_DRAFT_MTP) != params.speculative.types.end();
    const bool has_spec = has_draft || mtp;
    auto draft_params = common_base_params_to_speculative(params);
    auto draft_mparams = common_model_params_to_llama(draft_params);
    draft_mparams.no_alloc = true;
    draft_mparams.load_mode = LLAMA_LOAD_MODE_NONE;
    auto draft_cparams = common_context_params_to_llama(draft_params);
    draft_cparams.n_rs_seq = 0;
    if (mtp) {
        draft_cparams.ctx_type = LLAMA_CONTEXT_TYPE_MTP;
    }
    common_fit_extra_model extra{draft_params.model.path.c_str(), &draft_mparams, &draft_cparams, !has_draft};
    json reasons = json::array();
    json components = {{"target", "pending"}, {"projector", "not_selected"}, {"speculation", "not_selected"}};
    std::map<std::string, allocation> rows;
    rows["Host"] = {};

    // Native target fitting already includes draft/MTP. Projector allocation
    // is independent of the text context; reserve its measured bytes on the
    // exact devices so native fitting evaluates the complete chosen load.
    std::map<ggml_backend_dev_t, size_t> projector_memory;
    if (!params.mmproj.path.empty()) {
        auto projector_params = mtmd_context_params_default();
        projector_params.use_gpu = params.mmproj_use_gpu;
        projector_params.device = params.mmproj_device;
        projector_params.print_timings = false;
        projector_params.n_threads = params.cpuparams.n_threads;
        projector_params.flash_attn_type = params.flash_attn_type;
        // mtmd warmup only reserves its native compute graph; it does not
        // evaluate image tensors. This is also the worker's normal load policy.
        projector_params.warmup = true;
        projector_params.image_min_tokens = params.image_min_tokens;
        projector_params.image_max_tokens = params.image_max_tokens;
        projector_params.batch_max_tokens = params.mtmd_batch_max_tokens;
        {
            projector_allocation_guard guard;
            projector_memory = mtmd_get_memory_usage(params.mmproj.path.c_str(), projector_params);
        }
        components["projector"] = projector_memory.empty() ? "unavailable" : "measured";
        if (projector_memory.empty()) {
            reasons.push_back("The native projector allocation could not be measured.");
        }
        for (const auto & [dev, bytes] : projector_memory) {
            rows[device_id(dev)].projector += bytes;
        }
    }
    auto margins = params.fit_params_target;
    // fit indexes the main model's native device order, not global backend IDs.
    if (params.fit_params && !projector_memory.empty()) {
        std::vector<ggml_backend_dev_t> devices;
        uint32_t layers = 0, context = 0, experts = 0;
        common_get_device_memory_data(params.model.path.c_str(), &mparams, &cparams,
                devices, layers, context, experts, GGML_LOG_LEVEL_ERROR);
        for (size_t index = 0; index < devices.size(); ++index) {
            const auto found = projector_memory.find(devices[index]);
            if (found != projector_memory.end()) {
                margins[index] += found->second;
            }
        }
    }
    std::string fit_status = "disabled";
    if (params.fit_params) {
        const auto status = common_fit_params(params.model.path.c_str(), &mparams, &cparams,
                params.tensor_split, params.tensor_buft_overrides.data(), margins.data(),
                params.fit_params_min_ctx, has_spec ? &extra : nullptr, GGML_LOG_LEVEL_ERROR);
        fit_status = status == COMMON_PARAMS_FIT_STATUS_SUCCESS ? "success" :
                     status == COMMON_PARAMS_FIT_STATUS_FAILURE ? "insufficient_memory" : "error";
        if (status == COMMON_PARAMS_FIT_STATUS_ERROR) {
            throw std::runtime_error("Native fitting could not evaluate this model.");
        }
    }

    using model_ptr = std::unique_ptr<llama_model, decltype(&llama_model_free)>;
    using context_ptr = std::unique_ptr<llama_context, decltype(&llama_free)>;
    model_ptr model(llama_model_load_from_file(params.model.path.c_str(), mparams), llama_model_free);
    if (!model) {
        throw std::runtime_error("Native target metadata and allocation planning failed.");
    }
    context_ptr context(llama_init_from_model(model.get(), cparams), llama_free);
    if (!context) {
        throw std::runtime_error("Native cache and model-state planning failed for these settings.");
    }
    add_breakdown(rows, context.get(), false, false);
    components["target"] = "measured";
    if (has_spec) {
        try {
            draft_cparams.n_ctx = llama_n_ctx(context.get());
            draft_cparams.ctx_other = context.get();
            model_ptr draft_model(nullptr, llama_model_free);
            if (has_draft) {
                draft_model.reset(llama_model_load_from_file(draft_params.model.path.c_str(), draft_mparams));
                if (!draft_model) {
                    throw std::runtime_error("Draft metadata and allocation planning failed.");
                }
            }
            context_ptr draft_context(llama_init_from_model(
                    has_draft ? draft_model.get() : model.get(), draft_cparams), llama_free);
            if (!draft_context) {
                throw std::runtime_error("Draft/MTP cache and compute planning failed.");
            }
            add_breakdown(rows, draft_context.get(), true, !has_draft);
            components["speculation"] = "measured";
        } catch (const std::exception &) {
            components["speculation"] = "unavailable";
            reasons.push_back("The selected draft/MTP allocation could not be measured; totals are partial.");
        }
    }

    json devices = json::array();
    for (const auto & [id, row] : rows) {
        auto dev = id == "Host" ? ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_CPU) : ggml_backend_dev_by_name(id.c_str());
        size_t free = 0, total = 0;
        if (dev) {
            ggml_backend_dev_memory(dev, &free, &total);
        }
        const bool projector_known = components["projector"] != "unavailable";
        const bool speculation_known = components["speculation"] != "unavailable";
        const auto known_total = row.weights + row.context + row.compute + row.projector;
        devices.push_back({{"id", id}, {"weights_bytes", row.weights}, {"kv_bytes", row.context},
                {"runtime_overhead_bytes", row.compute},
                {"projector_bytes", projector_known ? json(row.projector) : json(nullptr)},
                {"speculation_bytes", speculation_known ? json(row.speculation) : json(nullptr)},
                {"known_total_bytes", known_total},
                {"total_bytes", projector_known && speculation_known ? json(known_total) : json(nullptr)},
                {"available_bytes", total ? json(free) : json(nullptr)},
                {"capacity_bytes", total ? json(total) : json(nullptr)}});
    }
    const auto training_context = llama_model_n_ctx_train(model.get());
    auto slot_context = std::min<uint32_t>(llama_n_ctx_seq(context.get()), training_context);
    if (params.kv_unified_per_slot > 0) {
        slot_context = std::min(slot_context, static_cast<uint32_t>(params.kv_unified_per_slot));
    }
    json evaluated = {{"ctx_size", llama_n_ctx(context.get())}, {"n_gpu_layers", mparams.n_gpu_layers},
            {"parallel", params.n_parallel}, {"kv_unified", params.kv_unified},
            {"batch_size", params.n_batch}, {"ubatch_size", params.n_ubatch}};
    json split = json::array();
    for (size_t index = 0; index < llama_max_devices(); ++index) {
        split.push_back(params.tensor_split[index]);
    }
    json overrides = json::array();
    if (mparams.tensor_buft_overrides) {
        for (size_t index = 0; index < llama_max_tensor_buft_overrides() &&
                mparams.tensor_buft_overrides[index].pattern; ++index) {
            const auto & override = mparams.tensor_buft_overrides[index];
            overrides.push_back({{"pattern", override.pattern}, {"buffer", ggml_backend_buft_name(override.buft)}});
        }
    }
    auto output = version();
    output["completeness"] = reasons.empty() ? "complete" : "partial";
    output["components"] = components;
    output["unknown_reasons"] = reasons;
    output["fit_status"] = fit_status;
    output["devices"] = devices;
    output["evaluated_startup"] = evaluated;
    output["placement"] = {{"tensor_split", split}, {"tensor_overrides", overrides}};
    output["effective_context"] = llama_n_ctx(context.get());
    output["effective_context_per_slot"] = slot_context;
    output["effective_parallel"] = params.n_parallel;
    output["kv_unified"] = params.kv_unified;
    output["context_maximum"] = training_context;
    output["output_limits"] = {{"total", params.n_outputs_max}, {"per_slot", params.n_outputs_max_per_seq}};
    output["dynamic_overhead_bytes"] = nullptr;
    return output;
}

int main(int argc, char ** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--workbench-version") {
            std::cout << version().dump() << '\n';
            return 0;
        }
        common_init();
        common_params params;
        if (!common_params_parse(argc, argv, params, LLAMA_EXAMPLE_SERVER)) {
            throw std::runtime_error("The native server parser rejected the requested settings.");
        }
        if (params.model.path.empty() || !params.model.url.empty() || !params.model.hf_repo.empty() ||
                !params.model.docker_repo.empty()) {
            throw std::runtime_error("Memory planning accepts installed local artifacts only.");
        }
        common_log_set_verbosity_thold(LOG_LEVEL_ERROR);
        llama_backend_init();
        std::cout << plan(params).dump() << '\n';
        common_log_flush(common_log_main());
        llama_backend_free();
        return 0;
    } catch (const std::exception &) {
        // Paths and model-card text stay out of user-facing errors.
        auto error = version();
        error["completeness"] = "unavailable";
        error["error"] = "Native allocation planning is unavailable for this model and settings.";
        std::cout << error.dump() << '\n';
        return 2;
    }
}
