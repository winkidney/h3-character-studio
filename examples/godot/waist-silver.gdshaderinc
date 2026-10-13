// Optional addition after polished-silver.gdshaderinc. All default controls are off.
// response_atlas.b covers reviewed waist silver only; keep it linear/nearest.
uniform sampler2D response_atlas : filter_nearest, repeat_disable;
uniform float waist_emphasis : hint_range(0.0, 1.0) = 0.0;

float waist_response(vec2 coord, float metal_mask) {
    return texture(response_atlas, coord).b * clamp(metal_mask, 0.0, 1.0) * waist_emphasis;
}
float waist_silver_roughness(float roughness, float amount) {
    return mix(roughness, 0.18, amount);
}
vec3 waist_silver_reflectance(vec3 albedo, float amount) {
    return mix(albedo, vec3(0.80, 0.82, 0.85), amount * 0.80);
}
