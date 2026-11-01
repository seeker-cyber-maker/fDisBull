// Decode a bounded, imported raw SH-2 image, stopping at the first unknown.
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.lang.InsufficientBytesException;
import ghidra.program.model.lang.UnknownInstructionException;
import ghidra.program.model.lang.UnknownContextException;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Instruction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public class RomAsm extends GhidraScript {
    private static String quote(String value) {
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 32) b.append(String.format("\\u%04x", (int)c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address start = toAddr(Long.parseUnsignedLong(args[1], 16));
        int length = Integer.parseInt(args[2]);
        int limit = Integer.parseInt(args[3]);
        Address end = start.add(length - 1L);
        boolean scan = Boolean.parseBoolean(args[4]);
        long started = System.nanoTime();
        StringBuilder out = new StringBuilder("{\"instructions\":[\n");
        PseudoDisassembler pseudo = scan ? new PseudoDisassembler(currentProgram) : null;
        int offset = 0, count = 0, attempted = 0;
        while (offset + 2 <= length && (scan ? attempted : count) < limit && !monitor.isCancelled()) {
            attempted++;
            Address address = start.add(offset);
            Instruction ins = null;
            if (scan) {
                byte[] word = new byte[2];
                currentProgram.getMemory().getBytes(address, word);
                try {
                    ins = pseudo.disassemble(address, word);
                } catch (InsufficientBytesException | UnknownInstructionException | UnknownContextException e) {
                    // A failed candidate is an unknown word, not a stopping condition.
                }
            } else {
                ins = currentProgram.getListing().getInstructionAt(address);
            }
            if (!scan && ins == null) {
                AddressSet restricted = new AddressSet(address, end);
                DisassembleCommand cmd = new DisassembleCommand(address, restricted, false);
                cmd.applyTo(currentProgram, monitor);
                ins = currentProgram.getListing().getInstructionAt(address);
            }
            if (ins == null || ins.getLength() != 2 || offset + ins.getLength() > length) {
                if (!scan) break;
                offset += 2;
                continue;
            }
            byte[] bytes = ins.getBytes();
            StringBuilder hex = new StringBuilder();
            for (byte b : bytes) hex.append(String.format("%02x", b & 255));
            StringBuilder operands = new StringBuilder();
            String separator = ins.getSeparator(0);
            if (separator != null) operands.append(separator);
            for (int i = 0; i < ins.getNumOperands(); i++) {
                operands.append(ins.getDefaultOperandRepresentation(i));
                separator = ins.getSeparator(i + 1);
                if (separator != null) operands.append(separator);
            }
            if (count > 0) out.append(",\n");
            out.append("{\"address\":").append(address.getOffset())
               .append(",\"size\":").append(ins.getLength())
               .append(",\"bytes\":").append(quote(hex.toString()))
               .append(",\"mnemonic\":").append(quote(ins.getMnemonicString()))
               .append(",\"operands\":").append(quote(operands.toString())).append("}");
            offset += ins.getLength();
            count++;
        }
        // Cancellation is missing evidence, never an ordinary undecodable word.
        monitor.checkCancelled();
        double seconds = (System.nanoTime() - started) / 1_000_000_000.0;
        out.append("\n],\"decode_seconds\":").append(seconds).append("}\n");
        Files.write(Paths.get(args[0]), out.toString().getBytes(StandardCharsets.UTF_8));
    }
}
