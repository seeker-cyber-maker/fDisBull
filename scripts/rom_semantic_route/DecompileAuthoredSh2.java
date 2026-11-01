import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.data.*;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.*;
public class DecompileAuthoredSh2 extends GhidraScript {
 public void run() throws Exception {
  Address a=toAddr(0x06010000L); disassemble(a);
  Function f=createFunction(a,"authored");
  f.setCallingConvention("__stdcall");
  f.setReturnType(UnsignedIntegerDataType.dataType, SourceType.USER_DEFINED);
  f.replaceParameters(Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS, true, SourceType.USER_DEFINED, new ParameterImpl("value",UnsignedIntegerDataType.dataType,currentProgram));
  println("PARAM_STORAGE=" + f.getParameter(0).getVariableStorage() + " RETURN_STORAGE=" + f.getReturn().getVariableStorage());
  DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
  DecompileResults r=d.decompileFunction(f,30,monitor);
  if(!r.decompileCompleted()) throw new Exception(r.getErrorMessage());
  Files.writeString(Path.of(getScriptArgs()[0]),r.getDecompiledFunction().getC()); d.dispose();
 }
}
