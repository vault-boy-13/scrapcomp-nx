/* Synthetic GPU verification of the actual NV2A fragment generator. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include "gl_api.h"
#include "gl_psh.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
int nv2a_shader_vk;

static GLuint shader(GLenum type,const char *source)
{
    GLuint s=glCreateShader(type);GLint ok=0;char log[2048];
    glShaderSource(s,1,&source,NULL);glCompileShader(s);glGetShaderiv(s,GL_COMPILE_STATUS,&ok);
    if(!ok) {glGetShaderInfoLog(s,sizeof log,NULL,log);fprintf(stderr,"shader: %s\n",log);exit(2);}
    return s;
}
static int cell(double coordinate)
{
    int value=(int)floor(coordinate*16.0);return value<0?0:value>15?15:value;
}
int main(void)
{
    SDL_SetMainReady();if(SDL_Init(SDL_INIT_VIDEO)) return 2;
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK,SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,3);SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,3);
    SDL_Window *window=SDL_CreateWindow("Bump fixture",0,0,16,16,SDL_WINDOW_OPENGL|SDL_WINDOW_HIDDEN);
    SDL_GLContext context=window?SDL_GL_CreateContext(window):NULL;
    if(!context || nv2a_gl_load(SDL_GL_GetProcAddress)) {fprintf(stderr,"%s\n",SDL_GetError());return 2;}
    const char *vs="#version 330 core\n"
        "uniform vec4 coords[4]; out vec4 vD0,vD1,vT0,vT1,vT2,vT3; out float vFog;\n"
        "void main(){ vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2); gl_Position=vec4(p*2.0-1.0,0,1);"
        "vD0=vD1=vec4(0);vFog=0;vT0=coords[0];vT1=coords[1];vT2=coords[2];vT3=coords[3];}\n";
    GLuint vertex=shader(GL_VERTEX_SHADER,vs),vao,target,fbo,tex[4];
    glGenVertexArrays(1,&vao);glBindVertexArray(vao);
    glGenTextures(1,&target);glBindTexture(GL_TEXTURE_2D,target);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,1,1,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
    glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,target,0);
    if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE) return 3;
    unsigned char image[16*16*4];
    for(unsigned y=0;y<16;y++) for(unsigned x=0;x<16;x++) {
        unsigned at=(y*16+x)*4;image[at]=(unsigned char)(x*16);image[at+1]=(unsigned char)(y*16);
        image[at+2]=17;image[at+3]=255;
    }
    glGenTextures(4,tex);
    for(unsigned i=0;i<4;i++) {
        glActiveTexture(GL_TEXTURE0+i);glBindTexture(GL_TEXTURE_2D,tex[i]);
        glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,16,16,0,GL_RGBA,GL_UNSIGNED_BYTE,image);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,0x812F);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,0x812F);
    }
    glViewport(0,0,1,1);unsigned cases=0;
    const unsigned bytes[]={0,1,63,127,128,129,192,255};
    for(unsigned stage=1;stage<4;stage++) for(unsigned source=0;source<stage;source++)
    for(unsigned mode=6;mode<=7;mode++) {
        Nv2aPshKey key={0};char fragment[65536];
        for(unsigned i=0;i<4;i++) key.shader_program|=(i==stage?mode:4)<<(i*5);
        if(stage>1) key.other_input=source<<(stage==2?16:20);
        key.final0=8+stage;key.final1=(0x18+stage)<<8;
        if(nv2a_gl_psh(&key,fragment,sizeof fragment)<0) return 4;
        GLuint fs=shader(GL_FRAGMENT_SHADER,fragment),program=glCreateProgram();GLint ok=0;
        glAttachShader(program,vertex);glAttachShader(program,fs);glLinkProgram(program);
        glGetProgramiv(program,GL_LINK_STATUS,&ok);if(!ok) return 5;glUseProgram(program);
        for(unsigned i=0;i<4;i++) {char name[8];snprintf(name,sizeof name,"t%u",i);glUniform1i(glGetUniformLocation(program,name),i);}
        glUniform1i(glGetUniformLocation(program,"u_alpha_func"),0x207);
        for(unsigned matrix=0;matrix<2;matrix++) for(unsigned scaled=0;scaled<2;scaled++)
        for(unsigned b=0;b<8;b++) for(unsigned g=0;g<8;g++) {
            float coords[4][4]={{0}},matrices[4][4]={{0}},lum[4][2]={{0}},scale[4][2];
            for(unsigned i=0;i<4;i++) {coords[i][0]=.483f;coords[i][1]=.517f;coords[i][3]=1;scale[i][0]=scale[i][1]=1;}
            coords[source][0]=.25f;coords[source][1]=bytes[g]/255.0f;coords[source][2]=bytes[b]/255.0f;
            if(matrix) {matrices[stage][0]=.25f;matrices[stage][1]=.125f;matrices[stage][2]=-.1875f;matrices[stage][3]=.3125f;}
            lum[stage][0]=1;lum[stage][1]=.5f;
            if(scaled) {scale[stage][0]=.75f;scale[stage][1]=1.25f;}
            glUniform4fv(glGetUniformLocation(program,"coords"),4,&coords[0][0]);
            glUniform4fv(glGetUniformLocation(program,"u_bump"),4,&matrices[0][0]);
            glUniform2fv(glGetUniformLocation(program,"u_bump_lum"),4,&lum[0][0]);
            glUniform2fv(glGetUniformLocation(program,"u_tscale"),4,&scale[0][0]);
            glDrawArrays(GL_TRIANGLES,0,3);unsigned char pixel[4];
            glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
            double ds=(bytes[b]<128?(double)bytes[b]:(double)bytes[b]-256)/127;
            double dt=(bytes[g]<128?(double)bytes[g]:(double)bytes[g]-256)/127;
            double u=(coords[stage][0]+matrices[stage][0]*ds+matrices[stage][2]*dt)*scale[stage][0];
            double v=(coords[stage][1]+matrices[stage][1]*ds+matrices[stage][3]*dt)*scale[stage][1];
            double gain=mode==7?.75:1;
            const int expected[]={(int)floor(cell(u)*16*gain+.5),(int)floor(cell(v)*16*gain+.5),(int)floor(17*gain+.5),(int)floor(255*gain+.5)};
            for(unsigned c=0;c<4;c++) if(abs((int)pixel[c]-expected[c])>1) {
                fprintf(stderr,"FAIL stage%u source%u mode%u matrix%u scale%u B%u G%u lane%u actual%u expected%d\n",
                    stage,source,mode,matrix,scaled,bytes[b],bytes[g],c,pixel[c],expected[c]);return 6;
            }
            if(glGetError()!=GL_NO_ERROR) return 7;++cases;
        }
        glUseProgram(0);glDeleteProgram(program);glDeleteShader(fs);
    }
    printf("PASS: %u GPU pixel checks: signed-byte boundaries, all input stages, matrix cross-terms, luminance and coordinate scale\n",cases);
    glDeleteShader(vertex);glDeleteTextures(4,tex);glDeleteTextures(1,&target);glDeleteFramebuffers(1,&fbo);
    SDL_GL_DeleteContext(context);SDL_DestroyWindow(window);SDL_Quit();return 0;
}
