// Persistent, privately owned headless worker. Requests use atomic files in a private directory.
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.lang.InsufficientBytesException;
import ghidra.program.model.lang.UnknownInstructionException;
import ghidra.program.model.lang.UnknownContextException;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.io.ByteArrayInputStream;

public class RomAsmServer extends GhidraScript {
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
    @Override public void run() throws Exception {
        Path dir = Paths.get(getScriptArgs()[0]);
        Files.writeString(dir.resolve("ready"), "ready", StandardCharsets.UTF_8);
        while (!monitor.isCancelled()) {
            Path request = dir.resolve("request");
            if (!Files.exists(request)) { Thread.sleep(10); continue; }
            if (Files.size(request) > 131300) throw new IllegalArgumentException("request too large");
            String[] fields = Files.readString(request, StandardCharsets.UTF_8).split("\n", -1);
            Files.delete(request);
            if (fields[0].equals("close")) return;
            String id = fields[0];
            try {
                if (fields.length != 7 || !id.matches("[0-9]+")) throw new IllegalArgumentException("bad request");
                long base = Long.parseUnsignedLong(fields[1], 16);
                if (!fields[1].matches("[0-9a-f]{1,8}") || (base & 1) != 0 ||
                    fields[2].length() == 0 || fields[2].length() > 131072 ||
                    (fields[2].length() & 1) != 0 || !fields[2].matches("[0-9a-f]+") ||
                    base + fields[2].length() / 2L > 0x100000000L ||
                    !fields[3].matches("[0-9]{1,5}") ||
                    !(fields[4].equals("true") || fields[4].equals("false")))
                    throw new IllegalArgumentException("bad bounded request");
                byte[] data = java.util.HexFormat.of().parseHex(fields[2]);
                int limit = Integer.parseInt(fields[3]);
                boolean scan = Boolean.parseBoolean(fields[4]);
                if (!fields[6].equals("end") || !java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(data)).equals(fields[5]) || data.length == 0 || limit < 0 || limit > 32768) throw new IllegalArgumentException("bad request fields");
                int tx = currentProgram.startTransaction("reset image");
                try {
                    for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                        Address oldStart = block.getStart(), oldEnd = block.getEnd();
                        currentProgram.getMemory().removeBlock(block, monitor);
                        for (ghidra.program.model.lang.Register register : currentProgram.getProgramContext().getRegistersWithValues())
                            currentProgram.getProgramContext().remove(oldStart, oldEnd, register);
                    }
                    Address start = toAddr(base);
                    currentProgram.getMemory().createInitializedBlock("image", start, new ByteArrayInputStream(data), data.length, monitor, false);
                    currentProgram.endTransaction(tx, true);
                } catch (Exception e) { currentProgram.endTransaction(tx, false); throw e; }
                Address start = toAddr(base);
                int length = data.length;
                Address end = start.add(length - 1L);
                int decodeTx = currentProgram.startTransaction("decode");
                String result;
                try { result = decode(start, end, length, limit, scan); currentProgram.endTransaction(decodeTx, true); }
                catch (Exception e) { currentProgram.endTransaction(decodeTx, false); throw e; }
                writeAtomic(dir, "response", id + "\n" + result);
            } catch (Exception e) { writeAtomic(dir, "response", id + "\nERROR " + e.toString()); }
        }
    }
    private void writeAtomic(Path dir, String name, String content) throws Exception {
        Path temp = dir.resolve(name + ".tmp");
        Files.writeString(temp, content, StandardCharsets.UTF_8);
        Files.move(temp, dir.resolve(name), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }
    private String decode(Address start, Address end, int length, int limit, boolean scan) throws Exception {
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
        return out.toString();
    }
}
