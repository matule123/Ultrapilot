# Display-only native building silhouettes

The local `promods-2.84/buildings.sqlite` layer contains 153,555 navigation
prisms extracted from native structural model k-DOP bounds in 1,319 actual
game sectors. Heights and positions come from the game; these are simplified
silhouettes, not full textured meshes or exact concave roof outlines.

The indexed database is queried read-only by the UI on a background worker.
The dataset key AND the 24-character runtime dataset fingerprint must match.
Switching maps discards old results. Missing/mismatched data returns an empty
visual layer; it never changes road geometry, route authority or controls.
Only the nearest bounded set is loaded. This is not a full scenery export:
buildings embedded inside prefab meshes and panorama groups may be absent.

The database is a locally generated runtime asset and is excluded from Git.
The existing assets packaging includes it in a local application build.
Regenerate after changes to the map, game version, or relevant mod sources.
