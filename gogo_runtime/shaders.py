"""Screen-space edge smoothing for Go Go 3D."""

SCREEN_VERTEX = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;
void main() {
    uv = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

EDGE_SMOOTH = """
#version 150
uniform sampler2D scene;
uniform vec2 viewport_size;
uniform float smoothing_strength;
in vec2 uv;
out vec4 p3d_FragColor;

float luminance(vec3 rgb) {
    return dot(rgb, vec3(0.299, 0.587, 0.114));
}

vec3 fetch(vec2 pos, vec2 maximum, vec2 pixel) {
    return texture(scene, clamp(pos, pixel * 0.5, maximum - pixel * 0.5)).rgb;
}

void main() {
    vec2 pixel = 1.0 / vec2(textureSize(scene, 0));
    vec2 maximum = min(vec2(1.0), viewport_size * pixel);
    vec2 pos = uv * maximum;
    vec3 center = fetch(pos, maximum, pixel);
    float nw = luminance(fetch(pos + pixel * vec2(-1,  1), maximum, pixel));
    float ne = luminance(fetch(pos + pixel * vec2( 1,  1), maximum, pixel));
    float sw = luminance(fetch(pos + pixel * vec2(-1, -1), maximum, pixel));
    float se = luminance(fetch(pos + pixel * vec2( 1, -1), maximum, pixel));
    float middle = luminance(center);
    float lo = min(middle, min(min(nw, ne), min(sw, se)));
    float hi = max(middle, max(max(nw, ne), max(sw, se)));
    if (hi - lo < max(0.036, hi * 0.12)) {
        p3d_FragColor = vec4(center, 1.0);
        return;
    }

    vec2 direction = vec2(sw+se-nw-ne, nw+sw-ne-se);
    float regularizer = max(0.008, (nw+ne+sw+se) * 0.03125);
    float influence = 1.0 / (min(abs(direction.x), abs(direction.y)) + regularizer);
    vec2 along = clamp(direction * influence, -6.0, 6.0) * pixel;
    vec3 inner = (fetch(pos - along / 6.0, maximum, pixel) + fetch(pos + along / 6.0, maximum, pixel)) * 0.5;
    vec3 outer = inner * 0.5 + (fetch(pos - along * 0.5, maximum, pixel) +
                                fetch(pos + along * 0.5, maximum, pixel)) * 0.25;
    vec3 resolved = luminance(outer) < lo || luminance(outer) > hi ? inner : outer;
    p3d_FragColor = vec4(mix(center, resolved, smoothing_strength), 1.0);
}
"""
