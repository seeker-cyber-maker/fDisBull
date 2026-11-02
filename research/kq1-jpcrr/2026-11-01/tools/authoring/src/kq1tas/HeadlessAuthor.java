package kq1tas;

import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import javax.imageio.ImageIO;
import org.jpc.diskimages.DiskImage;
import org.jpc.diskimages.ImageLibrary;
import org.jpc.emulator.EventRecorder;
import org.jpc.emulator.PC;
import org.jpc.emulator.TraceTrap;
import org.jpc.emulator.VGADigitalOut;
import org.jpc.emulator.memory.PhysicalAddressSpace;
import org.jpc.emulator.pci.peripheral.VGACard;
import org.jpc.emulator.peripheral.Keyboard;
import org.jpc.emulator.processor.Processor;
import org.jpc.emulator.processor.Segment;
import org.jpc.jrsr.JRSRArchiveReader;
import org.jpc.jrsr.JRSRArchiveWriter;
import org.jpc.plugins.RAWDumper;
import org.jpc.pluginsbase.Plugin;
import org.jpc.pluginsbase.Plugins;

/** Authoring front end only: unchanged JPC-RR 11.2 executes and records all inputs. */
public final class HeadlessAuthor implements Plugin {
    private static final long MAX_ADVANCE_NS = 60_000_000_000L;
    private static final int MAX_READ = 0xA0000;
    private final Plugins manager;
    private final BufferedReader input;
    private final PrintStream replies;
    private PC.PCFullStatus status;
    private String loadedPath;
    private volatile boolean running;
    private volatile boolean shutdownRequested;

    private HeadlessAuthor(Plugins manager, InputStream input, PrintStream replies) {
        this.manager = manager;
        this.input = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8));
        this.replies = replies;
    }

    public static void main(String[] args) throws Exception {
        String library = null, capture = null;
        for (int i = 0; i < args.length; i++) {
            if ("--help".equals(args[i])) {
                System.out.println("HeadlessAuthor --library DIR [--capture NEW_JMD_PATH]\n"
                    + "Tab-separated commands on stdin; JSON replies on stdout. See README.md.");
                return;
            }
            if ("--library".equals(args[i]) && i + 1 < args.length) library = args[++i];
            else if ("--capture".equals(args[i]) && i + 1 < args.length) capture = args[++i];
            else throw new IllegalArgumentException("Unknown or incomplete argument: " + args[i]);
        }
        if (library == null) throw new IllegalArgumentException("--library is required");
        // Keep protocol stdout separate from any incidental stock-core logging.
        PrintStream protocol = System.out;
        System.setOut(System.err);
        System.setProperty("java.awt.headless", "true");
        DiskImage.setLibrary(new ImageLibrary(library));
        Plugins manager = new Plugins();
        if (capture != null) {
            Path path = newOutput(capture);
            if (path.toString().matches(".*[(),].*"))
                throw new IllegalArgumentException("Capture path cannot contain comma or parentheses");
            manager.registerPlugin(new RAWDumper(manager, "rawoutput=" + path));
        }
        HeadlessAuthor author = new HeadlessAuthor(manager, System.in, protocol);
        manager.registerPlugin(author);
    }

    public void main() {
        reply(map("ok", true, "event", "ready", "protocol", 1,
            "engine", "unchanged stock JPC-RR 11.2", "time_unit", "ns"));
        try {
            String line;
            while (!shutdownRequested && (line = input.readLine()) != null) {
                if (line.isEmpty()) continue;
                String[] args = line.split("\t", -1);
                try {
                    Map<String, Object> result = command(args);
                    result.put("command", args[0]);
                    result.put("ok", true);
                    reply(result);
                } catch (Exception e) {
                    reply(map("ok", false, "command", args[0], "error", e.getClass().getSimpleName(),
                        "message", String.valueOf(e.getMessage())));
                    e.printStackTrace(System.err);
                }
            }
        } catch (IOException e) {
            reply(map("ok", false, "error", "InputError", "message", e.toString()));
        } finally {
            pause();
            manager.shutdownEmulator();
        }
    }

    private Map<String, Object> command(String[] args) throws Exception {
        switch (args[0]) {
        case "info":
            requireCount(args, 1, 1);
            return info();
        case "load": {
            requireCount(args, 3, 3);
            boolean forceMovie;
            if (args[2].equals("movie")) forceMovie = true;
            else if (args[2].equals("state")) forceMovie = false;
            else throw new IllegalArgumentException("Load mode must be movie or state");
            PC.PCFullStatus next;
            try (JRSRArchiveReader reader = new JRSRArchiveReader(args[1])) {
                // Reuse no input events, but let stock code carry the rerecord
                // counter forward when reloading the same project.
                next = PC.loadSavestate(reader, false, forceMovie, status);
            }
            // loadSavestate leaves the stock event recorder in stopped/direct mode.
            status = next;
            loadedPath = Paths.get(args[1]).toAbsolutePath().normalize().toString();
            manager.reconnect(status.pc);
            Map<String, Object> result = info();
            result.put("load_mode", args[2]);
            return result;
        }
        case "run_until_ns":
            requireCount(args, 2, 3);
            return run(number(args[1]), false, args.length == 3 ? number(args[2]) : 30_000L);
        case "next_frame":
            requireCount(args, 1, 2);
            requirePC();
            return run(Math.addExact(status.pc.getTime(), 1_000_000_000L), true,
                args.length == 2 ? number(args[1]) : 30_000L);
        case "read": {
            requireCount(args, 3, 3);
            long address = number(args[1]);
            byte[] bytes = readMemory(address, checkedLength(args[2]));
            return map("address", address, "length", bytes.length, "hex", hex(bytes), "time_ns", status.pc.getTime());
        }
        case "dump_ram": {
            requireCount(args, 4, 4);
            long address = number(args[1]);
            byte[] bytes = readMemory(address, checkedLength(args[2]));
            Path path = newOutput(args[3]);
            Files.write(path, bytes, StandardOpenOption.CREATE_NEW);
            return map("path", path.toString(), "address", address, "length", bytes.length, "time_ns", status.pc.getTime());
        }
        case "registers":
            requireCount(args, 1, 1);
            return registers();
        case "snapshot":
            requireCount(args, 2, 2);
            return snapshot(args[1]);
        case "keyedge": {
            requireCount(args, 3, 3);
            requirePC();
            int code = checkedKey(args[1]);
            long earliest = number(args[2]);
            if (earliest < 0) throw new IllegalArgumentException("Negative timestamp");
            long sequence = status.events.getEventCount();
            status.events.addEvent(earliest, Keyboard.class, new String[]{"KEYEDGE", Integer.toString(code)});
            EventRecorder.ReturnEvent event = status.events.getEventBySequence(sequence);
            if (event == null) throw new IOException("Stock recorder did not append the event");
            return map("sequence", sequence, "code", code, "earliest_ns", earliest,
                "scheduled_ns", event.timestamp, "time_ns", status.pc.getTime(),
                "executed_pressed", keyboard().getKeyExecStatus((byte)code));
        }
        case "truncate_future": {
            requireCount(args, 1, 1);
            requirePC();
            long before = status.events.getEventCount();
            status.events.truncateEventStream();
            Map<String, Object> result = info();
            result.put("removed_events", before - status.events.getEventCount());
            return result;
        }
        case "events": {
            requireCount(args, 3, 3);
            requirePC();
            long first = number(args[1]);
            int count = checkedLength(args[2]);
            if (first < 0 || count > 10000) throw new IllegalArgumentException("Invalid event range; maximum count 10000");
            List<Object> events = new ArrayList<Object>();
            for (int i = 0; i < count; i++) {
                EventRecorder.ReturnEvent event = status.events.getEventBySequence(first + i);
                if (event == null) break;
                events.add(map("sequence", first + i, "time_ns", event.timestamp, "data", Arrays.asList(event.eventData)));
            }
            return map("events", events, "time_ns", status.pc.getTime());
        }
        case "save_movie":
        case "save_state": {
            requireCount(args, 2, 2);
            requirePC();
            Path path = newOutput(args[1]);
            boolean movie = args[0].equals("save_movie");
            JRSRArchiveWriter writer = new JRSRArchiveWriter(path.toString());
            try {
                PC.saveSavestate(writer, status, movie, false);
                writer.close();
            } catch (Exception e) {
                writer.rollback();
                throw e;
            }
            return map("path", path.toString(), "movie_only", movie, "time_ns", status.pc.getTime(),
                "last_input_ns", status.events.getLastEventTime());
        }
        case "header": {
            requireCount(args, 2, 50);
            requirePC();
            String key = args[1];
            if (!key.matches("[A-Z][A-Z0-9_-]*") || Arrays.asList("SYSTEM", "PROJECTID", "SAVESTATEID", "RERECORDS").contains(key))
                throw new IllegalArgumentException("Only extra metadata headers can be edited");
            List<String[]> headers = new ArrayList<String[]>();
            if (status.extraHeaders != null)
                for (String[] header : status.extraHeaders)
                    if (header.length == 0 || !header[0].equals(key)) headers.add(header);
            if (args.length > 2) headers.add(Arrays.copyOfRange(args, 1, args.length));
            status.extraHeaders = headers.toArray(new String[headers.size()][]);
            status.events.setHeaders(status.extraHeaders);
            return map("headers", Arrays.asList(status.extraHeaders));
        }
        case "quit":
            requireCount(args, 1, 1);
            shutdownRequested = true;
            return info();
        default:
            throw new IllegalArgumentException("Unknown command: " + args[0]);
        }
    }

    private Map<String, Object> run(long target, boolean frameBoundary, long hostBudgetMs) throws Exception {
        requirePC();
        long start = status.pc.getTime();
        if (target < start || target - start > MAX_ADVANCE_NS)
            throw new IllegalArgumentException("Target must be at or after current time and at most 60s ahead");
        if (hostBudgetMs < 1 || hostBudgetMs > 60_000)
            throw new IllegalArgumentException("Host budget must be 1..60000ms");
        long hostStart = System.nanoTime();
        long startFrame = vga().getFrameNumber();
        String reason = "target";
        TraceTrap trap = status.pc.getTraceTrap();
        if (target > start) {
            trap.setTrapFlags(frameBoundary ? TraceTrap.TRACE_STOP_VRETRACE_START : 0L);
            trap.setTrapTime(target);
            status.events.setPCRunStatus(true);
            manager.pcStarted();
            status.pc.start();
            running = true;
            try {
                while (!shutdownRequested) {
                    status.pc.execute();
                    if (status.pc.getHitTraceTrap()) {
                        if (status.pc.getAndClearTripleFaulted()) reason = "triple_fault";
                        else if (frameBoundary && vga().getFrameNumber() > startFrame) reason = "frame";
                        else reason = "target";
                        break;
                    }
                    if (status.pc.getTime() >= target) break;
                    if (System.nanoTime() - hostStart >= hostBudgetMs * 1_000_000L) {
                        reason = "host_budget";
                        break;
                    }
                }
            } finally {
                pause();
                trap.clearTrapTime();
                trap.setTrapFlags(0L);
            }
        }
        Map<String, Object> result = info();
        result.put("reason", shutdownRequested ? "shutdown" : reason);
        result.put("target_ns", target);
        result.put("start_ns", start);
        result.put("start_frame", startFrame);
        result.put("elapsed_host_ns", System.nanoTime() - hostStart);
        result.put("target_reached", status.pc.getTime() >= target);
        return result;
    }

    private void pause() {
        if (running && status != null) {
            status.pc.stop();
            status.events.setPCRunStatus(false);
            running = false;
            manager.pcStopped();
        }
    }

    private Map<String, Object> info() {
        if (status == null) return map("loaded", false);
        List<Integer> pressed = new ArrayList<Integer>();
        Keyboard keyboard = keyboard();
        for (int i = 1; i <= 223; i++) if (keyboard.getKeyExecStatus((byte)i)) pressed.add(i);
        return map("loaded", true, "loaded_path", loadedPath, "running", running,
            "time_ns", status.pc.getTime(), "frame", vga().getFrameNumber(),
            "width", vga().getOutputDevice().getWidth(), "height", vga().getOutputDevice().getHeight(),
            "event_count", status.events.getEventCount(), "next_event_sequence", status.events.getEventCurrentSequence(),
            "last_input_ns", status.events.getLastEventTime(), "pressed_keys", pressed);
    }

    private byte[] readMemory(long address, int length) {
        requirePC();
        // Device-memory reads are not necessarily passive (VGA planar reads change
        // latches). KQ1's DOS/AGI state is entirely in conventional RAM.
        if (address < 0 || address > MAX_READ || address + length > MAX_READ)
            throw new IllegalArgumentException("Inspection is restricted to passive conventional RAM below 0xA0000");
        PhysicalAddressSpace memory = (PhysicalAddressSpace)status.pc.getComponent(PhysicalAddressSpace.class);
        byte[] bytes = new byte[length];
        for (int i = 0; i < length; i++) bytes[i] = memory.getByte((int)(address + i));
        return bytes;
    }

    private Map<String, Object> registers() {
        requirePC();
        Processor p = (Processor)status.pc.getComponent(Processor.class);
        return map("time_ns", status.pc.getTime(), "eax", unsigned(p.eax), "ebx", unsigned(p.ebx),
            "ecx", unsigned(p.ecx), "edx", unsigned(p.edx), "esi", unsigned(p.esi), "edi", unsigned(p.edi),
            "esp", unsigned(p.esp), "ebp", unsigned(p.ebp), "eip", unsigned(p.eip),
            "cs", segment(p.cs), "ds", segment(p.ds), "ss", segment(p.ss), "es", segment(p.es),
            "instructions_executed", p.instructionsExecuted);
    }

    private static Object segment(Segment segment) {
        if (segment == null) return null;
        return map("selector", segment.getSelector(), "base", unsigned(segment.getBase()));
    }

    private Map<String, Object> snapshot(String filename) throws IOException {
        requirePC();
        VGADigitalOut display = vga().getOutputDevice();
        int width = display.getWidth(), height = display.getHeight();
        if (width <= 0 || height <= 0) throw new IOException("No completed VGA image yet");
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        image.setRGB(0, 0, width, height, display.getBuffer(), 0, width);
        Path path = newOutput(filename);
        try (OutputStream out = Files.newOutputStream(path, StandardOpenOption.CREATE_NEW)) {
            if (!ImageIO.write(image, "png", out)) throw new IOException("PNG encoder not available");
        }
        return map("path", path.toString(), "width", width, "height", height,
            "time_ns", status.pc.getTime(), "frame", vga().getFrameNumber());
    }

    private Keyboard keyboard() { return (Keyboard)status.pc.getComponent(Keyboard.class); }
    private VGACard vga() { return (VGACard)status.pc.getComponent(VGACard.class); }
    private void requirePC() { if (status == null) throw new IllegalStateException("Load a movie or state first"); }
    private static long unsigned(int value) { return value & 0xffffffffL; }
    private static long number(String value) {
        if (value.startsWith("0x") || value.startsWith("0X")) return Long.parseLong(value.substring(2), 16);
        return Long.parseLong(value, 10);
    }
    private static int checkedLength(String value) {
        long length = number(value);
        if (length < 0 || length > MAX_READ) throw new IllegalArgumentException("Length must be 0..655360");
        return (int)length;
    }
    private static int checkedKey(String value) {
        long code = number(value);
        if (!(code >= 1 && code <= 83 || code >= 85 && code <= 95 || code >= 129 && code <= 197 || code >= 199 && code <= 223))
            throw new IllegalArgumentException("Unsupported stock KEYEDGE scan code");
        return (int)code;
    }
    private static void requireCount(String[] args, int min, int max) {
        if (args.length < min || args.length > max) throw new IllegalArgumentException("Wrong number of fields");
    }
    private static Path newOutput(String filename) throws IOException {
        Path path = Paths.get(filename).toAbsolutePath().normalize();
        if (Files.exists(path)) throw new IOException("Refusing to overwrite existing file: " + path);
        if (path.getParent() != null) Files.createDirectories(path.getParent());
        return path;
    }
    private static String hex(byte[] bytes) {
        final char[] digits = "0123456789abcdef".toCharArray();
        char[] output = new char[bytes.length * 2];
        for (int i = 0; i < bytes.length; i++) { output[i*2] = digits[(bytes[i] & 255) >>> 4]; output[i*2+1] = digits[bytes[i] & 15]; }
        return new String(output);
    }
    private static Map<String, Object> map(Object... values) {
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        for (int i = 0; i < values.length; i += 2) result.put((String)values[i], values[i+1]);
        return result;
    }
    private void reply(Object value) { replies.println(json(value)); replies.flush(); }
    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map) {
            List<String> fields = new ArrayList<String>();
            for (Object entryObject : ((Map<?, ?>)value).entrySet()) {
                Map.Entry<?, ?> entry = (Map.Entry<?, ?>)entryObject;
                fields.add(json(entry.getKey().toString()) + ":" + json(entry.getValue()));
            }
            return "{" + String.join(",", fields) + "}";
        }
        if (value instanceof Iterable || value instanceof Object[]) {
            Iterable<?> items = value instanceof Iterable ? (Iterable<?>)value : Arrays.asList((Object[])value);
            List<String> fields = new ArrayList<String>();
            for (Object item : items) fields.add(json(item));
            return "[" + String.join(",", fields) + "]";
        }
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toString().toCharArray()) {
            switch (c) {
            case '\\': out.append("\\\\"); break;
            case '"': out.append("\\\""); break;
            case '\n': out.append("\\n"); break;
            case '\r': out.append("\\r"); break;
            case '\t': out.append("\\t"); break;
            default: if (c < 32) out.append(String.format("\\u%04x", (int)c)); else out.append(c);
            }
        }
        return out.append('"').toString();
    }

    public boolean systemShutdown() { shutdownRequested = true; return !running; }
    public void reconnect(PC pc) { }
    public void pcStarting() { }
    public void pcStopping() { }
}
