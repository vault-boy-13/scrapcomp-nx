/* Mesa/EGL probe. The triangle is generated with gl_VertexID (no assets). */
#include <switch.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <glad/glad.h>
#include <stdio.h>
#include <sys/stat.h>

int main(void)
{
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (!eglInitialize(display, NULL, NULL) || !eglBindAPI(EGL_OPENGL_API)) return 1;
    EGLConfig config;
    EGLint count;
    const EGLint attributes[] = {EGL_RENDERABLE_TYPE,EGL_OPENGL_BIT,EGL_SURFACE_TYPE,EGL_WINDOW_BIT,
        EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
    if (!eglChooseConfig(display, attributes, &config, 1, &count) || count != 1) return 2;
    const EGLint context_attributes[] = {EGL_CONTEXT_MAJOR_VERSION_KHR,3,EGL_CONTEXT_MINOR_VERSION_KHR,3,
        EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR,EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR,EGL_NONE};
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    EGLSurface surface = eglCreateWindowSurface(display, config, nwindowGetDefault(), NULL);
    if (!eglMakeCurrent(display, surface, surface, context)) return 3;
    if (!gladLoadGLLoader((GLADloadproc)eglGetProcAddress)) return 5;
    const char *vertex = "#version 330 core\n"
        "out vec3 c;void main(){vec2 p[3]=vec2[3](vec2(0,.75),vec2(-.75,-.65),vec2(.75,-.65));"
        "vec3 colors[3]=vec3[3](vec3(1,.2,.1),vec3(.2,1,.1),vec3(.1,.3,1));"
        "gl_Position=vec4(p[gl_VertexID],0,1);c=colors[gl_VertexID];}";
    const char *fragment = "#version 330 core\nin vec3 c;out vec4 o;void main(){o=vec4(c,1);}";
    GLuint vs = glCreateShader(GL_VERTEX_SHADER), fs = glCreateShader(GL_FRAGMENT_SHADER);
    glShaderSource(vs, 1, &vertex, NULL); glCompileShader(vs);
    glShaderSource(fs, 1, &fragment, NULL); glCompileShader(fs);
    GLuint program = glCreateProgram();
    glAttachShader(program, vs); glAttachShader(program, fs); glLinkProgram(program);
    GLint linked = 0;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (!linked) return 4;
    GLuint vao;
    glGenVertexArrays(1, &vao); glBindVertexArray(vao); glUseProgram(program);
    glViewport(0, 0, 1280, 720);
    mkdir("sdmc:/switch", 0777);
    mkdir("sdmc:/switch/scrapland-workspace", 0777);
    FILE *log = fopen("sdmc:/switch/scrapland-workspace/gl-probe.log", "w");
    if (log) { fprintf(log,"GL %s, shader link PASS\n",glGetString(GL_VERSION)); fflush(log); }
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad; padInitializeDefault(&pad);
    if (log) { fputs("pad initialized; entering applet loop\n", log); fflush(log); }
    unsigned frames = 0;
    while (appletMainLoop()) {
        if (!frames && log) { fputs("frame 0: loop entered\n", log); fflush(log); }
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        glClearColor(.03f,.08f,.13f,1); glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLES,0,3);
        if (!frames && log) { fputs("frame 0: swapping buffers\n", log); fflush(log); }
        if (!eglSwapBuffers(display,surface)) break;
        if (!frames && log) { fputs("frame 0: swap returned\n", log); fflush(log); }
        if (++frames == 60 && log) { fprintf(log,"presented 60 frames, GL error %x\n",glGetError()); fflush(log); }
    }
    if (log) { fprintf(log,"applet loop ended after %u frames\n",frames); fflush(log); }
    if (log) fclose(log);
    glDeleteVertexArrays(1,&vao); glDeleteProgram(program); glDeleteShader(vs); glDeleteShader(fs);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroySurface(display,surface); eglDestroyContext(display,context); eglTerminate(display);
    return 0;
}
