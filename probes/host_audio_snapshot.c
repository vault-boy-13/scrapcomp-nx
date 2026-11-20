/* Read-only, bounded source-buffer snapshots from an explicitly owned host PID.
 * No process suspension: pages may reflect different instants of a live refill. */
#include <windows.h>
#include <dbghelp.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "apu_state.h"

static HANDLE process;
static uint64_t ram;
static uint64_t bus_page_map;
static uint32_t phys_lo,phys_hi;
static int read_memory(uint64_t address,void *out,size_t size)
{
    SIZE_T got=0;
    return ReadProcessMemory(process,(void *)(uintptr_t)address,out,size,&got) && got==size;
}
static uint64_t symbol_address(const char *name)
{
    char storage[sizeof(SYMBOL_INFO)+MAX_SYM_NAME]={0};SYMBOL_INFO *s=(SYMBOL_INFO *)storage;
    s->SizeOfStruct=sizeof *s;s->MaxNameLen=MAX_SYM_NAME;
    return SymFromName(process,name,s)?s->Address:0;
}
static uint64_t pointer_symbol(const char *name)
{
    uint64_t address=symbol_address(name),value=0;
    if(!address || !read_memory(address,&value,sizeof value)) return 0;
    return value;
}
static int read_physical(uint32_t address,void *out,size_t size)
{
    uint32_t p=address&0x03FFFFFF;
    uint32_t mapped=0;
    if(bus_page_map && !read_memory(bus_page_map+(p/4096)*4,&mapped,4)) return 0;
    if(mapped) return read_memory(ram+mapped+(p&4095u),out,size);
    uint64_t va=(p>=phys_lo && p<phys_hi)?0x80000000ull+p:p;
    return read_memory(ram+va,out,size);
}
int main(int argc,char **argv)
{
    if(argc!=6) {fprintf(stderr,"usage: snapshot PID expected_exe pdb_directory voice_hex output_prefix\n");return 2;}
    DWORD pid=strtoul(argv[1],NULL,10);unsigned voice=strtoul(argv[4],NULL,16);
    if(!pid || pid==GetCurrentProcessId() || voice>=256) return 2;
    process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,pid);if(!process) return 3;
    char actual[32768];DWORD length=sizeof actual;
    if(!QueryFullProcessImageNameA(process,0,actual,&length) || _stricmp(actual,argv[2])) return 4;
    SymSetOptions(SYMOPT_DEFERRED_LOADS|SYMOPT_UNDNAME);
    if(!SymInitialize(process,argv[3],TRUE)) return 5;
    uint64_t state=pointer_symbol("g_state");ram=pointer_symbol("g_apu_ram_ptr");
    bus_page_map=symbol_address("g_bus_page_va");
    phys_lo=(uint32_t)pointer_symbol("g_contig_phys_lo");
    phys_hi=(uint32_t)pointer_symbol("g_contig_phys_hi");
    uint32_t sge,voices,words[32];
    if(!state || !ram || phys_hi<=phys_lo ||
       !read_memory(state+offsetof(MCPXAPUState,regs)+NV_PAPU_VPSGEADDR*4,&sge,4) ||
       !read_memory(state+offsetof(MCPXAPUState,regs)+NV_PAPU_VPVADDR*4,&voices,4) ||
       !read_physical(voices+voice*NV_PAVS_SIZE,words,sizeof words)) return 6;
    uint32_t fmt=words[NV_PAVS_VOICE_CFG_FMT/4],ba=words[NV_PAVS_VOICE_CUR_PSL_START/4]&0xFFFFFF;
    uint32_t ebo=words[NV_PAVS_VOICE_PAR_NEXT/4]&0xFFFFFF;
    unsigned container=(fmt&NV_PAVS_VOICE_CFG_FMT_CONTAINER_SIZE)>>30;
    unsigned spb=1+((fmt&NV_PAVS_VOICE_CFG_FMT_SAMPLES_PER_BLOCK)>>16);
    const unsigned sizes[]={1,2,0,4};
    unsigned block=sizes[container]*spb;
    uint64_t bytes=(uint64_t)(ebo+1)*block;
    if(!fmt || (fmt&NV_PAVS_VOICE_CFG_FMT_DATA_TYPE) || !block || bytes>2*1024*1024 || !bytes) return 7;
    unsigned char *data=malloc((size_t)bytes),*low=malloc((size_t)bytes);if(!data || !low) return 8;
    struct {uint32_t linear,page,bytes;} pages[514];unsigned page_count=0;
    for(uint64_t at=0;at<bytes;) {
        uint32_t linear=ba+(uint32_t)at,page;
        unsigned chunk=4096-(linear&4095);if(chunk>bytes-at)chunk=(unsigned)(bytes-at);
        if(!read_physical(sge+(linear/4096)*8,&page,4) || !read_physical(page+(linear&4095),data+at,chunk)) return 9;
        if(!read_memory(ram+((page+(linear&4095))&0x03FFFFFF),low+at,chunk)) return 9;
        if(page_count>=514)return 9;
        pages[page_count].linear=linear;pages[page_count].page=page;pages[page_count++].bytes=chunk;
        at+=chunk;
    }
    char path[32768];snprintf(path,sizeof path,"%s.pcm",argv[5]);FILE *f=fopen(path,"wb");
    if(!f || fwrite(data,1,(size_t)bytes,f)!=(size_t)bytes) return 10;fclose(f);free(data);
    snprintf(path,sizeof path,"%s-low.pcm",argv[5]);f=fopen(path,"wb");
    if(!f || fwrite(low,1,(size_t)bytes,f)!=(size_t)bytes) return 10;fclose(f);free(low);
    snprintf(path,sizeof path,"%s.json",argv[5]);f=fopen(path,"wb");if(!f)return 10;
    fprintf(f,"{\"pid\":%lu,\"voice\":%u,\"format\":%u,\"ba\":%u,\"ebo\":%u,\"cbo\":%u,\"sge_base\":%u,\"voice_base\":%u,\"container_bytes\":%u,\"samples_per_block\":%u,\"bytes\":%llu,\"coherent_snapshot\":false,\"physical_lo\":%u,\"physical_hi\":%u,\"pages\":[",
            pid,voice,fmt,ba,ebo,words[NV_PAVS_VOICE_PAR_OFFSET/4]&0xFFFFFF,sge,voices,sizes[container],spb,bytes,phys_lo,phys_hi);
    for(unsigned i=0;i<page_count;i++) fprintf(f,"%s{\"linear\":%u,\"physical\":%u,\"bytes\":%u}",i?",":"",pages[i].linear,pages[i].page,pages[i].bytes);
    fprintf(f,"],\"contiguous_blocks\":[");
    unsigned count=0;uint64_t count_address=symbol_address("g_contig_count"),block_address=symbol_address("g_contig_blocks");
    struct Block {uint32_t addr,size;uint8_t free,pad[3];} *blocks=NULL;
    if(count_address && block_address && read_memory(count_address,&count,4) && count<=16384) {
        blocks=malloc(count*sizeof *blocks);
        if(blocks && read_memory(block_address,blocks,count*sizeof *blocks)) {
            int emitted=0;
            for(unsigned j=0;j<count;j++) for(unsigned i=0;i<page_count;i++) {
                uint64_t va=0x80000000ull+(pages[i].page&0x03FFFFFF);
                if(va>=blocks[j].addr && va<(uint64_t)blocks[j].addr+blocks[j].size) {
                    fprintf(f,"%s{\"va\":%u,\"size\":%u,\"free\":%u}",emitted++?",":"",blocks[j].addr,blocks[j].size,blocks[j].free);break;
                }
            }
        }
    }
    free(blocks);fprintf(f,"]}\n");
    fclose(f);SymCleanup(process);CloseHandle(process);printf("saved voice%02X %llu source bytes\n",voice,bytes);return 0;
}
