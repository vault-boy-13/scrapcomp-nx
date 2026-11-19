#version 460
layout(location=0) out vec3 color;
void main() {
    const vec2 p[3] = vec2[3](vec2(0.0,0.75),vec2(-0.75,-0.65),vec2(0.75,-0.65));
    const vec3 c[3] = vec3[3](vec3(1,0.2,0.1),vec3(0.2,1,0.1),vec3(0.1,0.3,1));
    gl_Position=vec4(p[gl_VertexID],0,1);
    color=c[gl_VertexID];
}
