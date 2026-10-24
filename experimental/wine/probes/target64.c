#include <windows.h>
#include <stdio.h>

/* Self-authored fixture: the controller must change 7 to 41 at our INT3. */
__declspec(dllexport) volatile LONG fdisbull_probe_counter = 7;

__attribute__((noinline)) static void probe_site(void)
{
    __asm__ __volatile__("int3\n\tmovl $0x12345678, %%eax\n\tnop" ::: "eax");
    InterlockedIncrement(&fdisbull_probe_counter);
}

int main(void)
{
    (void)GetTickCount64();
    probe_site();
    printf("FDISBULL_PE_COUNTER=%ld\n", fdisbull_probe_counter);
    return fdisbull_probe_counter == 42 ? 0 : 9;
}
