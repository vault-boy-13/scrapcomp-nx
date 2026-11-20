"""Native USB report checks for guest-only scripted sticks and buttons."""
from pathlib import Path
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / 'build/tests/scripted-input'
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'scripted_input.c'
    usb = ROOT / 'runtime/xboxrecomp/src/usb/usb_gamepad.c'
    source.write_text(r'''
#include <windows.h>
#include <assert.h>
static unsigned long tick;
static unsigned long fixture_clock(void) { return tick; }
#define GetTickCount fixture_clock
#include "USB_SOURCE"
#undef GetTickCount
static int connected;
DWORD xbox_InputGetState(DWORD port, XBOX_INPUT_STATE *state) {
    (void)port;
    memset(state,0,sizeof *state);
    state->Gamepad.sThumbLX=1234;
    state->Gamepad.sThumbLY=-4321;
    return connected ? 0 : 1;
}
DWORD xbox_InputSetState(DWORD port,const XBOX_VIBRATION *v) { (void)port;(void)v;return 0; }
int xbox_FramebufferKeyDown(int vk) { (void)vk;return 0; }
static int axis(const uint8_t *p) { return (int16_t)(p[0]|(p[1]<<8)); }
int main(void) {
    const char *tokens[]={"lsleft","lsright","lsdown","lsup","rsleft","rsright","rsdown","rsup"};
    unsigned cases=0;
    _putenv_s("RECOMP_PAD_PRESS","");
    for(connected=0;connected<=1;connected++) for(unsigned mask=0;mask<256;mask++) {
        char script[256]="100:start+a";
        for(unsigned b=0;b<8;b++) if(mask&(1u<<b)) { strcat(script,"+");strcat(script,tokens[b]); }
        strcat(script,":200");_putenv_s("RECOMP_PAD_SCRIPT",script);
        s_script_count[0]=-1;s_script_t0=1000;tick=1100;
        uint8_t packet[24];memset(packet,0xA5,sizeof packet);
        assert(usb_gamepad_report(0,packet,20)==20);
        assert(packet[0]==0&&packet[1]==20&&packet[2]==0x10&&packet[3]==0&&packet[4]==255);
        for(unsigned a=0;a<4;a++) {
            unsigned pair=(mask>>(2*a))&3;
            int expected=pair?((pair&2?24000:0)-(pair&1?24000:0)):
                (connected?(a==0?1234:a==1?-4321:0):0);
            assert(axis(packet+12+a*2)==expected);
        }
        for(unsigned i=20;i<24;i++) assert(packet[i]==0xA5);
        tick=1300;assert(usb_gamepad_report(0,packet,20)==20);
        assert(packet[2]==0&&packet[4]==0);
        assert(axis(packet+12)==(connected?1234:0));
        assert(axis(packet+14)==(connected?-4321:0));
        cases++;
    }
    _putenv_s("RECOMP_PAD2_SCRIPT","100:rsup:200");
    s_script_count[1]=-1;s_script_t0=0;tick=1000;
    uint8_t packet[20];assert(usb_gamepad_report(1,packet,20)==20);
    assert(s_script_t0==0&&axis(packet+18)==0);
    s_script_t0=1000;tick=1100;assert(usb_gamepad_report(1,packet,20)==20);
    assert(axis(packet+18)==24000);
    puts("PASS: 512 stick direction combinations, buttons, host preservation, expiry, report bounds and shared second-pad clock");
    return cases==512?0:1;
}
'''.replace('USB_SOURCE', usb.as_posix()), encoding='utf-8', newline='\n')
    paths = ws.paths()
    env = ws.vs_environment(paths)
    exe = directory / 'scripted_input.exe'
    ws.run([paths['host_compiler'], '/nologo', '/Od', '/we4013',
            '/I'+str(ROOT/'runtime/xboxrecomp/src'), source,
            '/Fe'+str(exe), '/Fo'+str(directory)+'\\'], name='scripted-input-build', env=env)
    ws.run([exe], name='scripted-input', env=env)
    ws.write_json(directory/'manifest.json', {
        'scope': 'Native synthetic USB packets; no game/OS input or hardware',
        'usb_source_sha256': ws.digest(usb), 'fixture_sha256': ws.digest(source),
        'executable_sha256': ws.digest(exe), 'passed': True})


if __name__ == '__main__':
    main()
