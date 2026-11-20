"""Native execution of actual DMA translation routines on colliding guest arenas."""
from pathlib import Path
import subprocess
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
SDK=ROOT/'runtime/xboxrecomp'

def function(text,signature):
    start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]+'\n'

def main():
    out=ROOT/'build/tests/dma-alias';out.mkdir(parents=True,exist_ok=True)
    sources={name:(SDK/name).read_text(encoding='utf-8') for name in
             ['src/kernel/xbox_devbus.c','src/kernel/xbox_memory_layout.c','src/kernel/kernel_memory.c',
              'src/apu/apu_shim.h','src/kernel/nv2a_pb_exec.c','src/usb/ohci.c']}
    bus=sources['src/kernel/xbox_devbus.c']
    registry=bus[bus.index('#define XBOX_DMA_PHYSICAL_PAGES'):bus.index('/* Device interrupt lines')]
    layout=sources['src/kernel/xbox_memory_layout.c']
    mapping=layout[layout.index('static SRWLOCK g_dma_page_lock'):layout.index('static int contig_insert')]
    prelude='''#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define XBOX_CONTIG_BASE 0x80000000u
#define XBOX_CONTIG_SIZE 0x04000000u
#define OHCI_CONTIG_BASE XBOX_CONTIG_BASE
typedef uint64_t hwaddr;
static volatile uint32_t g_contig_phys_lo=0x00480000,g_contig_phys_hi=0x04000000;
static uint32_t allocated,next_physical=0x03000000;
static uint32_t g_xbox_image_hi=0x00472000;
static uint8_t *g_apu_ram_ptr;
static uint32_t xbox_ContiguousAlloc(uint32_t size,uint32_t alignment) {
 if(size!=4096 || alignment!=4096)abort();
 uint32_t p=next_physical;next_physical+=4096;allocated++;return XBOX_CONTIG_BASE+p;
}
static int surface_hits_image(uint32_t a,uint32_t n){(void)n;return a>=0x10000 && a<0x480000;}
'''
    routines=registry+mapping+function(bus,'int xbox_ContiguousIsPhysical(')
    routines+=function(sources['src/kernel/kernel_memory.c'],'ULONG_PTR __stdcall xbox_MmGetPhysicalAddress(')
    routines+=function(sources['src/apu/apu_shim.h'],'static inline uint8_t *apu_phys(')
    routines+=function(sources['src/kernel/nv2a_pb_exec.c'],'static uint32_t dma_resolve(')
    routines+=function(sources['src/usb/ohci.c'],'static uint32_t bus_to_va(')
    baseline=(ROOT/'references/nfsu2-sw/xboxrecomp/src/apu/apu_shim.h').read_text(encoding='utf-8')
    routines+=function(baseline,'static inline uint8_t *apu_phys(').replace('apu_phys(','baseline_apu_phys(')
    fixture='''
static DWORD WINAPI worker(void *unused) {
 (void)unused;
 for(unsigned round=0;round<20;round++)for(unsigned p=0;p<128;p++) {
   uint32_t va=0x02000000+p*4096+37;
   uint32_t phys=(uint32_t)xbox_MmGetPhysicalAddress((PVOID)(uintptr_t)va);
   if(xbox_BusMappedVirtual(phys)!=va || bus_to_va(phys)!=va || dma_resolve(phys)!=va)return 1;
 }
 return 0;
}
int main(void) {
 if(xbox_MmGetPhysicalAddress((PVOID)(uintptr_t)0x002B78AC)!=0x002B78AC || allocated)return 13;
 g_apu_ram_ptr=VirtualAlloc(NULL,0x90000000ull,MEM_RESERVE,PAGE_NOACCESS);if(!g_apu_ram_ptr)return 2;
 const uint32_t va=0x0197D000;
 if(!VirtualAlloc(g_apu_ram_ptr+va,4096,MEM_COMMIT,PAGE_READWRITE) ||
    !VirtualAlloc(g_apu_ram_ptr+XBOX_CONTIG_BASE+va,4096,MEM_COMMIT,PAGE_READWRITE))return 3;
 for(unsigned i=0;i<4096;i++) {g_apu_ram_ptr[va+i]=(uint8_t)(i*7);g_apu_ram_ptr[XBOX_CONTIG_BASE+va+i]=(uint8_t)~(i*7);}
 uint32_t phys=(uint32_t)xbox_MmGetPhysicalAddress((PVOID)(uintptr_t)va);
 if(phys==va || phys>=0x04000000 || (phys&4095))return 4;
 unsigned old_wrong=0;
 for(unsigned i=0;i<4096;i++) {
   uint32_t address=va+i;
   if(xbox_MmGetPhysicalAddress((PVOID)(uintptr_t)address)!=phys+i)return 5;
   if(apu_phys(phys+i)!=g_apu_ram_ptr+address || *apu_phys(phys+i)!=(uint8_t)(i*7))return 6;
   if(dma_resolve(phys+i)!=address || bus_to_va(phys+i)!=address)return 7;
   if(*baseline_apu_phys(va+i)!=(uint8_t)(i*7))old_wrong++;
 }
 if(old_wrong!=4096)return 8;
 /* A real contiguous VA keeps its separate bus address and native bytes. */
 if(xbox_MmGetPhysicalAddress((PVOID)(uintptr_t)(XBOX_CONTIG_BASE+va))!=va ||
    apu_phys(va)!=g_apu_ram_ptr+XBOX_CONTIG_BASE+va)return 9;
 HANDLE threads[4];for(unsigned i=0;i<4;i++)threads[i]=CreateThread(NULL,0,worker,NULL,0,NULL);
 if(WaitForMultipleObjects(4,threads,TRUE,10000)!=WAIT_OBJECT_0)return 10;
 for(unsigned i=0;i<4;i++){DWORD code=99;if(!GetExitCodeThread(threads[i],&code)||code)return 11;CloseHandle(threads[i]);}
 if(allocated!=129)return 12;
 printf("PASS: 4096 coherent byte addresses, 4096 baseline corruptions, APU/NV2A/OHCI routes, 10240 concurrent lookups, 129 unique pages\\n");
 VirtualFree(g_apu_ram_ptr,0,MEM_RELEASE);return 0;
}
'''
    source=out/'test.c';source.write_text(prelude+routines+fixture,encoding='utf-8')
    paths=ws.paths();env=ws.vs_environment(paths);exe=out/'test.exe'
    ws.run([paths['host_compiler'],'/nologo','/O2',source,'/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='dma-alias-build',env=env)
    ws.run([exe],name='dma-alias-execution',env=env)
    ws.write_json(out/'manifest.json',{'scope':'Actual extracted DMA translation routines, sparse native guest arenas and real threads',
        'sources':{k:ws.digest(SDK/k) for k in sources},'fixture_sha256':ws.digest(source),
        'executable_sha256':ws.digest(exe),'passed':True})

if __name__=='__main__':main()
