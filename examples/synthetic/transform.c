/* Disassembly fixture only; fDisBull never executes this file. */
int transform(int value) {
    if (value == 0) return 42;
    return value * 3 + 7;
}
int main(void) { return transform(9); }
