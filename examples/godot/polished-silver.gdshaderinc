// Include at shader scope. Call after the ordinary ROUGHNESS/METALLIC/SPECULAR
// assignments in fragment(). Color and vector normals are left untouched.
uniform float polished_silver : hint_range(0.0, 1.0) = 0.0;
uniform float polished_roughness : hint_range(0.08, 0.5) = 0.12;

vec3 polished_silver_brdf(float metal_mask, float roughness, float metallic, float specular) {
    float amount = clamp(metal_mask, 0.0, 1.0) * polished_silver;
    return mix(vec3(roughness, metallic, specular),
               vec3(polished_roughness, 0.95, 1.0), amount);
}
