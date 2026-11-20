/* Known-value GPU checks of the production NV097 lighting shader/uniform packer. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include "gl_api.h"
#include "gl_vsh.h"
#include "gl_lighting.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>

static uint32_t regs[2048];
static GLuint program;
static unsigned cases;
static float pos[4]={0,0,0,1},normal[4]={0,0,1,0};
static const float diffuse[4]={.6f,.4f,.2f,.7f},specular[4]={.1f,.2f,.3f,.4f};
static void floats(unsigned method,const float *v,unsigned n) {memcpy(regs+method/4,v,n*4);}
static void xyz(unsigned method,float x,float y,float z) {float a[3]={x,y,z};floats(method,a,3);}
static void scalar(unsigned method,float x) {floats(method,&x,1);}
static GLuint compile(GLenum stage,const char **src,int count)
{
    GLuint s=glCreateShader(stage);GLint ok;char error[4096];
    glShaderSource(s,count,src,NULL);glCompileShader(s);glGetShaderiv(s,GL_COMPILE_STATUS,&ok);
    if(!ok) {glGetShaderInfoLog(s,sizeof error,NULL,error);fprintf(stderr,"%s\n",error);exit(2);}return s;
}
static void reset(void)
{
    memset(regs,0,sizeof regs);regs[0x314/4]=1;
    xyz(0xA10,.1f,.2f,.3f);scalar(0x3B4,.375f);
    for(unsigned i=0;i<4;i++) scalar(0x480+i*20,1);
    for(unsigned i=0;i<3;i++) scalar(0x580+i*20,1);
    scalar(0xA5C,1);normal[0]=normal[1]=0;normal[2]=1;
    pos[0]=pos[1]=pos[2]=0;
    xyz(0x9E0,0,0,1);
}
static void light(unsigned kind)
{
    regs[0x3BC/4]=kind;
    xyz(0x100C,.2f,.1f,.05f);xyz(0x1034,0,0,1);xyz(0x1028,0,0,1);
    xyz(0x105C,0,0,4);xyz(0x1068,1,.25f,0);scalar(0x1024,100);
    xyz(0x1040,0,0,1);scalar(0x1058,1);
}
static void check(const char *name,int enabled,const double d[4],const double s[4])
{
    float uniforms[NV2A_FFP_ROWS][4];nv2a_gl_ffp_uniforms(regs,enabled,uniforms);
    glUniform4fv(glGetUniformLocation(program,"u_ffp"),NV2A_FFP_ROWS,&uniforms[0][0]);
    glUniform4fv(glGetUniformLocation(program,"position"),1,pos);
    glUniform4fv(glGetUniformLocation(program,"normalIn"),1,normal);
    glUniform4fv(glGetUniformLocation(program,"diffuseIn"),1,diffuse);
    glUniform4fv(glGetUniformLocation(program,"specularIn"),1,specular);
    for(int which=0;which<2;which++) {
        glUniform1i(glGetUniformLocation(program,"which"),which);glDrawArrays(GL_TRIANGLES,0,3);
        float actual[4];glReadPixels(0,0,1,1,GL_RGBA,GL_FLOAT,actual);
        const double *expected=which?s:d;
        for(int c=0;c<4;c++) if(!isfinite(actual[c]) || fabs(actual[c]-expected[c])>3e-5) {
            fprintf(stderr,"FAIL %s output%d lane%d actual%.9g expected%.9g\n",name,which,c,actual[c],expected[c]);exit(6);
        }
        if(glGetError()!=GL_NO_ERROR) exit(7);
        cases++;
    }
}
int main(void)
{
    SDL_SetMainReady();if(SDL_Init(SDL_INIT_VIDEO)) return 2;
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK,SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,3);SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,3);
    SDL_Window *w=SDL_CreateWindow("FFP fixture",0,0,16,16,SDL_WINDOW_OPENGL|SDL_WINDOW_HIDDEN);
    SDL_GLContext context=w?SDL_GL_CreateContext(w):NULL;
    if(!context || nv2a_gl_load(SDL_GL_GetProcAddress)) return 2;
    const char *vs[]={"#version 330 core\n",
#ifdef BASELINE_NO_LIGHTING
        "void nv2a_ffp_colors(vec4 p,vec4 n,vec4 d,vec4 s,out vec4 a,out vec4 b){a=d;b=s;}\n",
#else
        nv2a_gl_vsh_lighting(),
#endif
        "uniform vec4 position,normalIn,diffuseIn,specularIn;out vec4 d0,d1;\n"
        "void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.0-1.0,0,1);"
        "nv2a_ffp_colors(position,normalIn,diffuseIn,specularIn,d0,d1);}\n"};
    const char *fs[]={"#version 330 core\nin vec4 d0,d1;uniform int which;out vec4 color;void main(){color=which==0?d0:d1;}"};
    GLuint v=compile(GL_VERTEX_SHADER,vs,3),f=compile(GL_FRAGMENT_SHADER,fs,1),vao,tex,fbo;
    program=glCreateProgram();glAttachShader(program,v);glAttachShader(program,f);glLinkProgram(program);
    GLint ok;glGetProgramiv(program,GL_LINK_STATUS,&ok);if(!ok) return 3;glUseProgram(program);
    glGenVertexArrays(1,&vao);glBindVertexArray(vao);
    glGenTextures(1,&tex);glBindTexture(GL_TEXTURE_2D,tex);
    glTexImage2D(GL_TEXTURE_2D,0,0x8814,1,1,0,GL_RGBA,GL_FLOAT,NULL);
    glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,tex,0);
    if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE) return 4;glViewport(0,0,1,1);
    const double zero[4]={0,0,0,1},ambient[4]={.1,.2,.3,.375},lit[4]={.3,.3,.35,.375};
    const double rawd[4]={.6,.4,.2,.7},raws[4]={.1,.2,.3,.4};
    reset();check("unlit passthrough",0,rawd,raws);
    check("scene ambient",1,ambient,zero);
    light(1);check("directional",1,lit,zero);
    normal[2]=-1;check("back normal stays unlit",1,ambient,zero);normal[2]=1;
    scalar(0x5A8,.5f);const double half[4]={.2,.25,.325,.375};check("inverse normal unnormalized",1,half,zero);
    regs[0x3A4/4]=1;check("inverse normal normalized",1,lit,zero);
    reset();light(2);const double point[4]={.2,.25,.325,.375};check("point attenuation",1,point,zero);
    scalar(0x1024,3.99f);check("point outside range",1,ambient,zero);scalar(0x1024,4);check("inclusive range",1,point,zero);
    light(3);
    for(unsigned i=0;i<=8;i++) {double gain=i/8.0;scalar(0x1058,(float)gain);
        double expected[4]={.1+.1*gain,.2+.05*gain,.3+.025*gain,.375};check("spot cone",1,expected,zero);}
    scalar(0x1058,-.1f);check("spot outside cone",1,ambient,zero);
    scalar(0x1058,.5f);xyz(0x1040,0,-.5f,1.5f);
    const double rational[4]={.14,.22,.31,.375};check("rational spot coefficients",1,rational,zero);
    reset();light(1);regs[0x3B8/4]=1;regs[0x294/4]=1;xyz(0x1018,.15f,.1f,.05f);
    const double shine[4]={.15,.1,.05,.4};check("separate specular",1,lit,shine);
    xyz(0x1028,.6f,0,.8f);xyz(0x9E0,-.2f,.5f,.5f);
    const double shine2[4]={.1,.0666666667,.0333333333,.4};check("rational specular coefficients",1,lit,shine2);
    regs[0x294/4]=0;const double merged[4]={.4,.3666666667,.3833333333,.375};check("merged specular",1,merged,raws);
    regs[0x3B8/4]=0;check("specular disabled",1,lit,zero);
    reset();light(1);regs[0x3B8/4]=1;regs[0x294/4]=0x10001;xyz(0x1018,.15f,.1f,.05f);xyz(0xA50,3,0,4);
    double hv=sqrt(.9),eyeShine[4]={.15*hv,.1*hv,.05*hv,.4};check("local eye",1,lit,eyeShine);
    reset();light(1);regs[0x298/4]=0x20;const double material[4]={.12,.22,.315,.4};check("specular color material diffuse",1,material,zero);
    reset();light(1);regs[0x298/4]=0x04;xyz(0x3A8,.05f,.06f,.07f);xyz(0x1000,.1f,.2f,.3f);
    const double ambientMaterial[4]={.39,.404,.424,.375};check("vertex ambient material",1,ambientMaterial,zero);
    reset();light(1);regs[0x298/4]=0x09;xyz(0x3A8,.05f,.06f,.07f);
    const double both[4]={.805,.512,.271,.375};check("vertex emission and ambient",1,both,zero);
    /* Compile the complete production fixed-function vertex entry as well. */
    const char *complete[]={nv2a_gl_vsh_prelude(),nv2a_gl_vsh_lighting(),nv2a_gl_vsh_fixed()};
    GLuint full=compile(GL_VERTEX_SHADER,complete,3);glDeleteShader(full);
    printf("PASS: %u float GPU outputs including cones, inverse normals, color material and specular\n",cases);
    SDL_GL_DeleteContext(context);SDL_DestroyWindow(w);SDL_Quit();return 0;
}
