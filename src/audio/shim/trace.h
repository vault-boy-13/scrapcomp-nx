/* QEMU trace collection is disabled; decoder failures/asserts remain enabled. */
#pragma once
#define TRACE_DSP56K_EXECUTE_INSTRUCTION_DISASM 0
#define trace_event_get_state(event) 0
#define trace_dsp56k_execute_instruction(...) ((void)0)
#define trace_dsp56k_execute_instruction_disasm(...) ((void)0)
