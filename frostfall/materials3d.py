"""Surface programs for the ice, water, and sculpted pieces."""

VERTEX = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform vec4 p3d_ColorScale;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec3 world;
out vec3 normal;
out vec4 pigment;
void main() {
    world = (p3d_ModelMatrix * p3d_Vertex).xyz;
    normal = mat3(transpose(inverse(p3d_ModelMatrix))) * p3d_Normal;
    pigment = p3d_Color * p3d_ColorScale;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

SURFACE = """
#version 150
uniform vec3 eye;
uniform int material_kind;
uniform vec4 frost_tint;
uniform vec4 cap_tint;
uniform float scene_time;
in vec3 world;
in vec3 normal;
in vec4 pigment;
out vec4 p3d_FragColor;

float hash(vec2 v) {
    return fract(sin(dot(v, vec2(126.1, 311.7))) * 41758.6);
}

float noise(vec2 v) {
    vec2 i = floor(v);
    vec2 f = fract(v);
    f = f*f*(3.0-2.0*f);
    return mix(mix(hash(i), hash(i+vec2(1,0)), f.x),
               mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), f.x), f.y);
}

void main() {
    vec3 n = normalize(normal);
    vec3 primary = normalize(vec3(-0.64, -0.44, 0.92));
    vec3 kicker = normalize(vec3(0.56, 0.73, 0.52));
    vec3 view = normalize(eye - world);
    float diffuse = max(dot(n, primary), 0.0);
    float back = max(dot(n, kicker), 0.0);
    float rim = pow(1.0 - max(dot(n, view), 0.0), 2.3);
    float gloss = pow(max(dot(n, normalize(primary + view)), 0.0), material_kind == 1 ? 34.0 : 24.0);
    vec3 base = pigment.rgb;

    if (material_kind == 1) {
        float fine = noise(world.xy * 48.0);
        float coarse = noise(world.xy * 8.0);
        float drift = noise(world.xy * 3.0 + 0.24 * vec2(coarse, fine));
        float vein = 1.0 - smoothstep(0.008, 0.027, abs(drift - 0.42));
        float grain = 0.96 + 0.025 * coarse + fine * 0.014;
        base *= grain;
        base += vec3(0.04, 0.108, 0.13) * vein * max(0.12, n.z * 0.79);
        base = mix(base, frost_tint.rgb, frost_tint.a);
        base *= vec3(0.84, 0.91, 1.0) + vec3(0.21, 0.20, 0.13) * diffuse;
        base += vec3(0.36, 0.69, 0.87) * (0.08 * rim + 0.104 * gloss);
        base += vec3(0.15, 0.31, 0.37) * pow(back, 7.0) * 0.21;
        float caustic = pow(max(0.0,sin(world.x*12.0+sin(world.y*9.0+scene_time*.55)) *
                                      sin(world.y*11.0+scene_time*.45)),5.0);
        base += vec3(.06,.15,.18)*caustic*(1.0-max(0.0,n.z))*.23;
    } else if (material_kind == 2) {
        float flatness = max(0.0, n.z);
        float cloud = noise(world.xy*6.7);
        float grain = noise(world.xy*39.0 + world.z*.7);
        float frost = smoothstep(.44,.89,cloud*.8 + grain*.2);
        float layer = pow(max(0.0,sin(world.z*97.0 + 3.5*noise(world.xy*8.3))),7.0);
        float crystal = pow(grain,7.0);
        base = mix(base, cap_tint.rgb, cap_tint.a * flatness);
        base *= .84 + .17*diffuse + .14*cloud;
        base += vec3(.13,.21,.24)*frost*flatness;
        base += vec3(.11,.26,.34)*layer*(1.0-flatness)*.46;
        base += vec3(.27,.42,.49)*crystal*.23;
        base += vec3(.04,.16,.20)*(rim + gloss)*.62;
        base = mix(base, frost_tint.rgb, frost_tint.a);
    } else if (material_kind == 3) {
        base *= .64 + .36*diffuse + .12*back;
        base += vec3(.19,.12,.054)*rim;
        base += vec3(.38,.25,.11)*pow(gloss,.69);
    } else {
        base = base * (0.47 + 0.50 * diffuse + 0.13 * back);
        base += vec3(0.28, 0.49, 0.66) * rim * (0.11 + 0.23 * back);
        base += vec3(0.96, 0.93, 0.84) * gloss * 0.17;
    }
    p3d_FragColor = vec4(clamp(base, 0.0, 1.0), pigment.a);
}
"""

WATER = """
#version 150
uniform float tide_time;
uniform vec4 ripple0;
uniform vec4 ripple1;
uniform vec4 ripple2;
uniform vec4 ripple3;
uniform vec4 pressure;
in vec3 world;
out vec4 p3d_FragColor;

float bell(float x) { return exp(-x*x); }

float wake(vec4 ripple,vec2 p,float t) {
    float age=t-ripple.z;
    if(age<0.0 || age>2.7) return 0.0;
    vec2 radial = p - ripple.xy;
    float dist = length(radial) + sin(radial.x*8.0)*sin(radial.y*5.0)*.019;
    float front = dist - age*1.65;
    float crest = bell(front*12.0);
    float echo = bell((front+.21)*15.0);
    float trough = bell((front+.105)*17.0);
    return (crest + .44*echo - .25*trough)*exp(-age*1.47)*ripple.w;
}

void main() {
    vec2 p = world.xy;
    float t = tide_time;
    float phase = p.x*1.7 + sin(p.y*1.85 + t*0.34) * 0.77;
    float wave = phase + p.y*2.65 - t*.84;
    float chop = p.x*3.45 - p.y*3.2 + t*.67 + sin(p.y*1.3)*.71;
    float swell = sin(wave);
    float cross_swell = sin(chop);
    float ripplet = p.y*11.0 + p.x*2.1 + swell*1.9 + cross_swell*.6 - t*1.35;
    float fine = sin(ripplet) + .22*sin(p.x*10.3-p.y*3.6+t*.86+cross_swell*1.3);
    float ripple = pow(clamp(fine, 0.0, 1.0), 6.0) * (.25 + .75 * smoothstep(-.7,.93,swell));
    vec2 slope = cos(wave)*vec2(.071,.114) + cos(chop)*vec2(.053,-.039) +
                 cos(ripplet)*vec2(.016,.064);
    vec3 n = normalize(vec3(-slope, 1.0));
    float sheen = pow(max(dot(n, normalize(vec3(-.31,-.16,1.0))),0.0),24.0);
    float glints = smoothstep(.79,.99,sheen) * smoothstep(.50,1.11,fine);
    float lagoon = exp(-0.031 * dot(p + vec2(0.7, 0.55), p + vec2(0.7, 0.55)));
    float sidelight = bell(.2145*(p.x-5.1-.34*p.y)) * bell(.1342*(p.y-2.2));
    float polar = bell(.1483*(p.x+6.8-.62*p.y)) * smoothstep(-4.0, 9.5, p.y);
    float aurora_line = p.y - 0.54*p.x - 3.7 + sin(p.x*.69 + t*.18)*.49;
    float aurora = bell(.5657*aurora_line) * (.54 + swell*.13 + ripple*.31);
    float dawn = bell(.1732*(p.x-9.1)) * bell(.155*(p.y-8.2));
    vec3 base = mix(vec3(0.025, 0.058, 0.139), vec3(0.033, 0.194, 0.263), lagoon);
    base += sidelight * vec3(0.035, 0.15, 0.146) + polar * vec3(0.129, 0.061, 0.182);
    base += aurora * vec3(0.081, 0.205, 0.182) + dawn * vec3(0.21, 0.102, 0.122);
    base += vec3(0.021, 0.046, 0.062) * (swell * 0.35 + cross_swell * 0.24);
    base += vec3(0.074, 0.185, 0.217) * ripple * (.23 + sidelight*.26 + lagoon*.16);
    float reflection = pow(max(swell * 0.55 + 0.45 * cross_swell, 0.0), 4.0);
    base += (sidelight*.5 + .34) * reflection * vec3(.03,.073,.094);
    base += glints * vec3(.095,.175,.19) * (.58 + .37 * sidelight);
    float edge = abs(abs(p.x) - 5.45 + .21*sin(p.y*3.0)) + .1*cross_swell;
    float foam = (1.0-smoothstep(.03,.25,edge)) * smoothstep(.08,.98,fine*.68 + swell*.35);
    base += vec3(.055,.157,.172)*foam;
    float d = length(p-pressure.xy);
    float tremor = pow(max(0.0, sin(d*21.0 - pressure.w*12.0)), 5.0);
    base += vec3(.14,.26,.25)*tremor*exp(-d*d*1.17)*pressure.z;
    float wakes=wake(ripple0,p,t)+wake(ripple1,p,t)+wake(ripple2,p,t)+wake(ripple3,p,t);
    base += vec3(.115,.281,.32)*wakes;
    p3d_FragColor = vec4(max(base,0.0), 1.0);
}
"""

SHADOW = """
#version 150
uniform vec3 shadow_center;
uniform float spread;
in vec3 world;
out vec4 p3d_FragColor;

void main() {
    vec2 p = (world.xy - shadow_center.xy) / spread;
    float alpha = exp(-6.5 * dot(p, p)) * 0.34;
    p3d_FragColor = vec4(0.012, 0.057, 0.083, alpha);
}
"""

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
