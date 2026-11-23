#include <algorithm>
#include <cmath>
#include <cstdint>

namespace {
constexpr std::uint32_t max_tracks = 80 * 4 * 8;
constexpr std::uint32_t max_samples = 33;
constexpr std::uint32_t max_edges = 512;
constexpr double step = 0.25;

bool finite(const double* values, std::uint32_t count) {
    return std::all_of(values, values + count, [](double value) {
        return std::isfinite(value);
    });
}
}

// Input poses are contiguous XYZYaw tracks. A negative parallel limit requests
// AABB admission only. Output has one row per admitted segment, in input order,
// with one bit per route edge, in route order. A negative return invalidates
// the entire batch. The caller owns all buffers and supplies their dimensions.
extern "C" __declspec(dllexport) std::int32_t crossing_pairs_v2(
    const double* poses, std::uint32_t pose_count,
    const std::uint32_t* samples, const double* parallel_limits, std::uint32_t track_count,
    const double* bounds, const double* edges, std::uint32_t edge_count,
    std::uint32_t* row_ids, std::uint64_t* masks, std::uint32_t row_capacity,
    std::uint32_t* completed_poses) {
    if (track_count == 0 || track_count > max_tracks || pose_count > max_tracks * max_samples ||
        edge_count > max_edges || pose_count < track_count || row_capacity != pose_count - track_count ||
        !finite(poses, pose_count * 4) || !finite(parallel_limits, track_count) ||
        !finite(bounds, edge_count * 4) || !finite(edges, edge_count * 10)) {
        return -1;
    }

    std::uint32_t expected = 0;
    for (std::uint32_t track = 0; track < track_count; ++track) {
        const auto length = samples[track];
        if (length < 2 || length > max_samples ||
            (parallel_limits[track] < 0.0 && parallel_limits[track] != -1.0)) {
            return -1;
        }
        expected += length;
    }
    if (expected != pose_count) {
        return -1;
    }
    if (edge_count == 0) {
        *completed_poses = expected;
        return 0;
    }

    double xmin = bounds[0], xmax = bounds[1], zmin = bounds[2], zmax = bounds[3];
    for (std::uint32_t edge = 0; edge < edge_count; ++edge) {
        const auto box = bounds + edge * 4;
        if (box[0] > box[1] || box[2] > box[3] || edges[edge * 10 + 7] <= 0.0) {
            return -1;
        }
        xmin = std::min(xmin, box[0]);
        xmax = std::max(xmax, box[1]);
        zmin = std::min(zmin, box[2]);
        zmax = std::max(zmax, box[3]);
    }

    const auto words = (edge_count + 63) / 64;
    std::uint32_t offset = 0, written = 0;
    for (std::uint32_t track = 0; track < track_count; ++track) {
        const auto limit = parallel_limits[track];
        for (std::uint32_t sample = 0; sample + 1 < samples[track]; ++sample) {
            const auto row = offset + sample;
            const auto pose = poses + row * 4;
            const double x = pose[0], z = pose[2];
            const double vx = (pose[4] - x) / step, vz = (pose[6] - z) / step;
            const double ex = x + vx * step, ez = z + vz * step;
            if (!std::isfinite(ex) || !std::isfinite(ez)) {
                return -1;
            }
            const double left = std::min(x, ex), right = std::max(x, ex);
            const double near = std::min(z, ez), far = std::max(z, ez);
            if (left > xmax || right < xmin || near > zmax || far < zmin) {
                continue;
            }
            std::uint64_t hits[max_edges / 64]{};
            bool admitted = false;
            for (std::uint32_t edge = 0; edge < edge_count; ++edge) {
                const auto box = bounds + edge * 4;
                if (left > box[1] || right < box[0] || near > box[3] || far < box[2]) {
                    continue;
                }
                if (limit >= 0.0) {
                    const auto line = edges + edge * 10;
                    const double denominator = vx * line[5] - vz * line[3];
                    const double alignment = std::abs(denominator) * line[7];
                    if (!std::isfinite(alignment) || (denominator == 0.0 && limit == 0.0)) {
                        return -1;
                    }
                    if (alignment < limit) {
                        continue;
                    }
                    const double ox = line[0] - x, oz = line[2] - z;
                    const double time = (ox * line[5] - oz * line[3]) / denominator;
                    const double along = (ox * vz - oz * vx) / denominator;
                    if (!std::isfinite(time) || !std::isfinite(along)) {
                        return -1;
                    }
                    if (time < 0.0 || time > step || along < 0.0 || along > 1.0) {
                        continue;
                    }
                }
                hits[edge / 64] |= std::uint64_t{1} << (edge % 64);
                admitted = true;
            }
            if (admitted) {
                row_ids[written] = row;
                std::copy_n(hits, words, masks + written * words);
                ++written;
            }
        }
        offset += samples[track];
    }
    *completed_poses = offset;
    return static_cast<std::int32_t>(written);
}
