"""Check HDD save paths and guest links using the actual native path layer."""
from pathlib import Path
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / 'build/tests/save-paths'
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'save_paths.c'
    runtime = ROOT / 'runtime/xboxrecomp/src/kernel/kernel_path.c'
    source.write_text(r'''
#include <assert.h>
#include <windows.h>
static BOOL fixture_mkdir(LPCWSTR name,LPSECURITY_ATTRIBUTES security) {
    (void)name;(void)security;return TRUE;
}
#define CreateDirectoryW fixture_mkdir
#include "PATH_SOURCE"
#undef CreateDirectoryW
void xbox_log(int level,const char *subsystem,const char *fmt,...) {
    (void)level;(void)subsystem;(void)fmt;
}
const char *xbox_LookupSymbolicLink(const char *link) {
    if(!strcmp(link,"\\??\\U:")) return "\\Device\\Harddisk0\\Partition1\\UDATA\\454c0001";
    if(!strcmp(link,"\\??\\T:")) return "\\Device\\Harddisk0\\Partition1\\TDATA\\454c0001";
    if(!strcmp(link,"\\??\\Z:")) return "\\Device\\Harddisk0\\Partition1\\";
    return NULL;
}
static void check(const char *guest,const wchar_t *expected) {
    wchar_t actual[MAX_PATH];
    assert(xbox_translate_path(guest,actual,MAX_PATH));
    if(wcscmp(actual,expected)) {
        fwprintf(stderr,L"Mismatch: %S -> %ls, expected %ls\n",guest,actual,expected);abort();
    }
}
int main(void) {
    /* Only path translation is tested: no disk-image creation or game data. */
    wcscpy_s(s_game_dir,MAX_PATH,L"C:\\disc-input");
    wcscpy_s(s_save_dir,MAX_PATH,L"C:\\diagnostic-saves");s_initialized=TRUE;
    check("\\Device\\Harddisk0\\Partition1\\UDATA\\454c0001\\slot\\Config.dat",
          L"C:\\diagnostic-saves\\UserData\\454c0001\\slot\\Config.dat");
    check("\\Device\\Harddisk0\\Partition1\\UDATA",L"C:\\diagnostic-saves\\UserData");
    check("\\Device\\Harddisk0\\Partition1\\UDATA\\",L"C:\\diagnostic-saves\\UserData");
    check("\\device\\harddisk0\\partition1\\udata\\slot",L"C:\\diagnostic-saves\\UserData\\slot");
    check("\\Device\\Harddisk0\\Partition1\\TDATA\\title\\cache.dat",
          L"C:\\diagnostic-saves\\TitleData\\title\\cache.dat");
    check("U:\\slot\\Save0.sav",L"C:\\diagnostic-saves\\UserData\\454c0001\\slot\\Save0.sav");
    check("\\??\\T:\\settings.dat",L"C:\\diagnostic-saves\\TitleData\\454c0001\\settings.dat");
    check("D:\\Data.packed",L"C:\\disc-input\\Data.packed");
    check("\\Device\\CdRom0\\Video\\Enlight.xmv",L"C:\\disc-input\\Video\\Enlight.xmv");
    check("Z:\\Data.packed",L"C:\\disc-input\\Data.packed");
    check("\\Device\\Harddisk0\\Partition1\\UDATA2\\asset",L"C:\\disc-input\\UDATA2\\asset");
    assert(!match_rule("\\Device\\Harddisk0\\Partition30\\asset","\\Device\\Harddisk0\\Partition3"));
    puts("PASS: native HDD UDATA/TDATA, directory roots, guest symbolic links, case, disc paths and sibling boundaries");
    return 0;
}
'''.replace('PATH_SOURCE', runtime.as_posix()), encoding='utf-8', newline='\n')
    paths = ws.paths()
    env = ws.vs_environment(paths)
    exe = directory/'save_paths.exe'
    ws.run([paths['host_compiler'], '/nologo', '/Od', '/we4013',
            '/I'+str(ROOT/'runtime/xboxrecomp/src'), source,
            '/Fe'+str(exe), '/Fo'+str(directory)+'\\', '/link', 'shell32.lib'],
           name='save-paths-build', env=env)
    ws.run([exe], name='save-paths', env=env)
    ws.write_json(directory/'manifest.json', {
        'scope': 'Native synthetic path translations; no game inputs',
        'path_layer_sha256': ws.digest(runtime), 'fixture_sha256': ws.digest(source),
        'executable_sha256': ws.digest(exe), 'passed': True})


if __name__ == '__main__':
    main()
