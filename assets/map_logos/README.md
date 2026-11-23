# Optional company map logos

Place authorized PNG artwork here using the exact company icon token from the
active map dataset, e.g. `acc.png`. Tokens may contain only letters, digits,
underscores and hyphens (maximum 80 characters). Missing artwork falls back to
the company nameplate. No logos are downloaded or fabricated by the renderer.
Assets are loaded once per scene revision, cached and bounded to 128 entries.

Building footprints may be supplied by `map_scene_polygons` entries as
`[points, colour, z_index, "building", height_m]`. Legacy three-field area
records remain supported. Current TruckLib map exports do not provide these
building footprints. Company positions are never converted into invented
buildings. Height shading is a display effect; route/control geometry does not
use it. The default camera is heading-up perspective. A separate 2D overview remains available.
