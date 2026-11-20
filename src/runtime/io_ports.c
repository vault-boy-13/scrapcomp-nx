/* Guest port I/O device routing; never execute host privileged instructions.
 * Behavior reference for the reached MCPX GPIO output:
 * https://github.com/xemu-project/xemu/blob/711b416840c2a528cb989621b6456a72bd02d768/hw/xbox/acpi_xbox.c
 * This is an independent, bounded model, not copied xemu source.
 */
#include <stdint.h>
#include <stdio.h>

extern void recomp_unimpl(const char *instruction, uint32_t va);
static volatile uint8_t gpio_output;
static unsigned gpio_writes;
static unsigned gpio_reads;

uint32_t recomp_port_in(uint32_t port, uint32_t width, uint32_t va)
{
    /* Match xemu's limited field-sense model: successive reads alternate
     * bit 5, other input bits zero. This is bring-up behavior, not an encoder
     * with scanout-timed interlaced fields. Input is separate from output.
     * Guest execution lock serializes port accesses. */
    if (port == 0x80C0 && width == 1) {
        uint32_t value = (++gpio_reads & 1u) << 5;
        if (gpio_reads <= 8)
            fprintf(stderr, "[IO] GPIO input port=%04X value=%02X guest=%08X\n",
                    port, value, va);
        return value;
    }
    fprintf(stderr, "[IO] unsupported IN port=%04X width=%u guest=%08X\n", port, width, va);
    recomp_unimpl("unsupported guest port IN", va);
    return 0; /* strict host diagnostic terminates above */
}

void recomp_port_out(uint32_t port, uint32_t value, uint32_t width, uint32_t va)
{
    /* GPIO output control at PM base 0x8000 + 0xC0. The current GPU model
     * has no physical TV encoder pins to drive; retain the output latch.
     * Field-sense reads and other GPIO/PCI ports need separate models. */
    if (port == 0x80C0 && width == 1) {
        gpio_output = (uint8_t)value;
        if (gpio_writes++ < 8)
            fprintf(stderr, "[IO] GPIO output port=%04X value=%02X guest=%08X\n",
                    port, gpio_output, va);
        return;
    }
    fprintf(stderr, "[IO] unsupported OUT port=%04X width=%u value=%08X guest=%08X\n",
            port, width, value, va);
    recomp_unimpl("unsupported guest port OUT", va);
}
